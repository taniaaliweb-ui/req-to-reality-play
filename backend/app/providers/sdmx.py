"""Generic SDMX-CSV ("csvfilewithlabels") parser. Used by ILOSTAT and by file imports of other
official SDMX services (e.g. UAE FCSC .Stat). Values keep full precision as Decimal; blank values
are reported as missing, never filled."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.providers.base import ProviderError

# Columns that are attributes/metadata rather than classification dimensions.
NON_DIM = {"STRUCTURE", "STRUCTURE_ID", "STRUCTURE_NAME", "ACTION", "REF_AREA", "FREQ", "MEASURE", "TIME_PERIOD", "OBS_VALUE",
           "OBS_STATUS", "UNIT_MEASURE_TYPE", "UNIT_MEASURE", "UNIT_MULT", "SOURCE", "NOTE_SOURCE", "NOTE_INDICATOR", "NOTE_CLASSIF",
           "DECIMALS", "UPPER_BOUND", "LOWER_BOUND", "INDICATOR"}


@dataclass
class SdmxRecord:
    dataflow: str
    dataflow_name: str
    ref_area: str
    ref_area_label: str
    freq: str
    measure: str
    measure_label: str
    period: str
    value: Decimal | None
    dims: dict[str, dict] = field(default_factory=dict)  # {"SEX": {"code": "SEX_T", "label": "Total"}}
    attrs: dict[str, str] = field(default_factory=dict)  # OBS_STATUS, UNIT_MEASURE, SOURCE, NOTE_* ...
    raw: dict = field(default_factory=dict)

    @property
    def year(self) -> int | None:
        head = self.period[:4]
        return int(head) if head.isdigit() else None

    @property
    def dim_key(self) -> str:
        return ".".join(d["code"] for d in self.dims.values()) or "_"


def parse_csv(text: str) -> list[SdmxRecord]:
    if not text.strip():
        return []
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return []
    if "OBS_VALUE" not in header or "TIME_PERIOD" not in header or "REF_AREA" not in header:
        raise ProviderError("malformed", "SDMX-CSV is missing REF_AREA / TIME_PERIOD / OBS_VALUE columns")
    # In csvfilewithlabels every coded column is followed by its human label column.
    codes: list[tuple[str, int, int | None]] = []
    i = 0
    while i < len(header):
        name = header[i]
        label_idx = i + 1 if i + 1 < len(header) and header[i + 1] and not header[i + 1].isupper() else None
        codes.append((name, i, label_idx))
        i += 2 if label_idx is not None else 1
    out: list[SdmxRecord] = []
    for row in reader:
        if not row or len(row) < len(header) - 2:
            continue
        get = {n: (row[ci] if ci < len(row) else "", row[li] if li is not None and li < len(row) else "") for n, ci, li in codes}
        v = get["OBS_VALUE"][0].strip()
        try:
            value = Decimal(v) if v else None
        except InvalidOperation as e:
            raise ProviderError("malformed", f"Non-numeric OBS_VALUE {v!r}") from e
        flow = get.get("STRUCTURE_ID", ("", ""))
        dims = {n: {"code": c, "label": lab} for n, (c, lab) in get.items() if n not in NON_DIM and c}
        attrs = {n: c for n, (c, _l) in get.items() if n in NON_DIM and n not in ("REF_AREA", "FREQ", "MEASURE", "TIME_PERIOD", "OBS_VALUE")}
        attrs["UNIT_MEASURE_LABEL"] = get.get("UNIT_MEASURE", ("", ""))[1]
        out.append(SdmxRecord(
            dataflow=flow[0].split(":")[-1].split("(")[0], dataflow_name=flow[1] or get.get("STRUCTURE_NAME", ("", ""))[0],
            ref_area=get["REF_AREA"][0], ref_area_label=get["REF_AREA"][1], freq=get.get("FREQ", ("", ""))[0],
            measure=get.get("MEASURE", get.get("INDICATOR", ("", "")))[0], measure_label=get.get("MEASURE", get.get("INDICATOR", ("", "")))[1],
            period=get["TIME_PERIOD"][0], value=value, dims=dims, attrs=attrs,
            raw={header[k]: row[k] for k in range(min(len(header), len(row))) if row[k] != ""},
        ))
    return out
