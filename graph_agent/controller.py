from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ControlDecision:
    level: str
    allow_second_solver: bool
    allow_critic: bool


class TaxonomyGuidedController:
    """
    V3 controller.

    Historical taxonomy no longer triggers extra LLM calls by itself.
    Extra compute is current-query evidence driven:
      1) primary solver always runs once;
      2) second solver is allowed only after verifier failure;
      3) critic is allowed only if the second attempt also fails / remains unresolved.

    The learned taxonomy is used to adapt the primary prompt and repair strategy,
    not to eagerly spend more inference compute.
    """

    def decide(self) -> ControlDecision:
        return ControlDecision(
            level="verify_then_escalate",
            allow_second_solver=True,
            allow_critic=True,
        )
