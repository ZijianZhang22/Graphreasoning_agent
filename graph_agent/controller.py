from __future__ import annotations
from dataclasses import dataclass

@dataclass
class ControlDecision:
    level: str
    solvers: int
    use_critic: bool
    force_strong_check: bool

class TaxonomyGuidedController:
    """
    Main proposed difference from vanilla AdaMAST:
    learned failures do not only generate reflection; they allocate inference compute.
    """
    def decide(self, risk: float) -> ControlDecision:
        if risk < 0.25:
            return ControlDecision("low", 1, False, False)
        if risk < 0.60:
            return ControlDecision("medium", 2, False, False)
        return ControlDecision("high", 2, True, True)
