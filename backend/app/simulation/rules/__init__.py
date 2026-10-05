"""Domain rules. Each module exposes step(ctx, st) and reads parameters only from the frozen input
(evidence, assumptions, prior registry). No rule contains a hidden probability constant."""


class SimulationBlocked(RuntimeError):
    """A required dimension became unresolvable at runtime (e.g. a disabled fallback prior). Never silently continue."""
