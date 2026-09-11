from __future__ import annotations
import json
from pathlib import Path

from .verifier import parse_candidate, verify
from .taxonomy import LearnedTaxonomy
from .controller import TaxonomyGuidedController
from .llm import Usage

BASE_PROMPT = """You solve undirected graph connectivity.
Return ONLY JSON:
{\"answer\":\"yes\"|\"no\",\"path\":[integer node ids]}
For yes, provide a valid source-to-target path. For no, use [].
"""

class Metrics:
    def __init__(self):
        self.usage = Usage()
        self.repairs = 0
        self.critics = 0

    def add(self, u):
        self.usage.add(u)

class AdaptiveGraphAgent:
    def __init__(self, llm, run_dir, use_taxonomy=True):
        self.llm = llm
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.taxonomy = LearnedTaxonomy(self.run_dir / "taxonomy.json")
        self.controller = TaxonomyGuidedController()
        self.use_taxonomy = use_taxonomy
        self.metrics = Metrics()

    def _prompt(self, ex):
        prompt = BASE_PROMPT
        if self.use_taxonomy:
            patches = self.taxonomy.relevant_patches(ex, top_k=2)
            if patches:
                prompt += "\nKnown recurring failure precautions:\n"
                for p in patches:
                    prompt += f"- [{p.code}] {p.repair_hint}\n"
        return prompt

    def _call(self, system, user):
        r = self.llm.complete(system, user, max_tokens=240)
        self.metrics.add(r.usage)
        return parse_candidate(r.text)

    def run_one(self, ex):
        risk = self.taxonomy.risk(ex) if self.use_taxonomy else 0.0
        decision = self.controller.decide(risk)

        c1 = self._call(self._prompt(ex), ex.question)
        v1 = verify(ex, c1)
        final, final_v = c1, v1

        second = None
        if (not v1.ok) or decision.solvers >= 2:
            repair_context = (
                f"\nPrevious candidate: {c1.raw}\n"
                f"Verifier signal: {v1.code} - {v1.feedback}\n"
                "Solve independently and correct any issue."
            )
            second = self._call(self._prompt(ex), ex.question + repair_context)
            v2 = verify(ex, second)

            if v2.ok:
                final, final_v = second, v2
            elif v1.ok:
                final, final_v = c1, v1

        if decision.use_critic and second is not None:
            self.metrics.critics += 1
            critic_prompt = f"""Task:
{ex.question}

Candidate A:
{c1.raw}

Candidate B:
{second.raw}

Return only the candidate that is more defensible, in exactly the same JSON schema.
"""
            cc = self._call(
                "You are a graph verification critic. Check endpoints and every claimed edge.",
                critic_prompt,
            )
            vc = verify(ex, cc)
            if vc.ok:
                final, final_v = cc, vc

        first_failure = None if v1.ok else v1.code
        if not v1.ok:
            self.metrics.repairs += 1

        if self.use_taxonomy:
            self.taxonomy.observe(ex, first_failure)

        row = {
            "example_id": ex.example_id,
            "gold": ex.gold,
            "risk_before": risk,
            "compute_level": decision.level,
            "first_try_ok": v1.ok,
            "first_failure": first_failure,
            "final_ok": final_v.ok,
            "llm_calls_cumulative": self.metrics.usage.calls,
        }
        with (self.run_dir / "traces.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        return row
