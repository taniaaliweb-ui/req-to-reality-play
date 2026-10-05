"""Deterministic randomness. One independent stream per (seed, year, domain) so that:
- the same input + seed always reproduces the same life (also after a backend restart),
- a branch resumed at year Y with the same seed reproduces its parent unless an override changes state,
- adding a rule to one domain does not shift the draws of another domain."""
from __future__ import annotations

import hashlib
import random


def stream(seed: int, year: int, domain: str) -> random.Random:
    h = hashlib.sha256(f"{seed}:{year}:{domain}".encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def derive_seed(master_seed: int, index: int) -> int:
    """Seed for Monte Carlo member `index` (0-based), derived from the master seed."""
    h = hashlib.sha256(f"mc:{master_seed}:{index}".encode()).digest()
    return int.from_bytes(h[:4], "big") & 0x7FFFFFFF
