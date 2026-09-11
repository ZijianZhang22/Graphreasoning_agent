from __future__ import annotations
import json
from pathlib import Path

from .verifier import parse_candidate, verify
from .taxonomy import LearnedTaxonomy
from .controller import TaxonomyGuidedController
from .llm import Usage

CONNECTIVITY_PROMPT = """You solve undirected graph connectivity.
Return ONLY JSON:
{\"answer\":\"yes\"|\"no\",\"path\":[integer node ids]}
For yes, provide a valid source-to-target path. For no, use [].
"""

SHORTEST_PATH_PROMPT = """You solve weighted undirected shortest-path problems.
Return ONLY JSON:
{\"path\":[integer node ids],\"total_weight\":number}
The path must start at the requested source and end at the requested target.
Minimize TOTAL EDGE WEIGHT, not hop count. Validate every consecutive edge and sum weights exactly.
"""


class Metrics:
    def __init__(self):
        self.usage = Usage()
        self.repairs = 0
        self.critics = 0

    def add(self, u):
        self.usage.add(u)


class AdaptiveGraphAgent:
    """
    V4 experiment:
      taxonomy -> retrieve failure-specific prompt patches
      -> primary solver
      -> deterministic executable verifier
      -> second solver only if this query fails
      -> critic only if the second attempt also fails

    This keeps inference cheap while allowing cross-query failure knowledge to
    improve the first attempt on harder graph tasks.
    """

    def __init__(self, llm, run_dir, use_taxonomy=True):
        self.llm = llm
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.taxonomy = LearnedTaxonomy(self.run_dir / "taxonomy.json")
        self.controller = TaxonomyGuidedController()
        self.use_taxonomy = use_taxonomy
        self.metrics = Metrics()

    def _base_prompt(self, ex):
        if ex.task == "shortest_path":
            return SHORTEST_PATH_PROMPT
        return CONNECTIVITY_PROMPT

    def _prompt(self, ex):
        prompt = self._base_prompt(ex)
        if self.use_taxonomy:
            patches = self.taxonomy.relevant_patches(ex, top_k=3)
            if patches:
                prompt += "\nRecurring failure precautions learned from prior queries:\n"
                for p in patches:
                    prompt += f"- [{p.code}] {p.repair_hint}\n"
        return prompt

    def _call(self, system, user):
        r = self.llm.complete(system, user, max_tokens=320)
        self.metrics.add(r.usage)
        return parse_candidate(r.text)

    def run_one(self, ex):
        decision = self.controller.decide()
        prompt = self._prompt(ex)

        c1 = self._call(prompt, ex.question)
        v1 = verify(ex, c1)
        final, final_v = c1, v1

        second = None
        second_v = None
        used_second = False
        used_critic = False

        if (not v1.ok) and decision.allow_second_solver:
            self.metrics.repairs += 1
            used_second = True
            repair_context = f"""

PREVIOUS CANDIDATE:
{c1.raw}

CURRENT VERIFIER FAILURE:
{v1.code}: {v1.feedback}

Repair the answer from scratch. Follow the graph weights exactly and validate the result.
Return ONLY the required JSON object.
"""
            second = self._call(prompt, ex.question + repair_context)
            second_v = verify(ex, second)
            final, final_v = second, second_v

        if (
            used_second
            and second is not None
            and second_v is not None
            and (not second_v.ok)
            and decision.allow_critic
        ):
            self.metrics.critics += 1
            used_critic = True
            critic_prompt = f"""TASK:
{ex.question}

CANDIDATE A:
{c1.raw}
Verifier A: {v1.code} - {v1.feedback}

CANDIDATE B:
{second.raw}
Verifier B: {second_v.code} - {second_v.feedback}

Both attempts failed executable verification. Re-solve carefully.
For weighted shortest path, use Dijkstra-style cumulative-cost reasoning.
Return ONLY the task's JSON schema.
"""
            cc = self._call(
                "You are a graph-reasoning critic and final repair agent.",
                critic_prompt,
            )
            vc = verify(ex, cc)
            final, final_v = cc, vc

        first_failure = None if v1.ok else v1.code
        if self.use_taxonomy:
            self.taxonomy.observe(ex, first_failure)

        row = {
            "example_id": ex.example_id,
            "task": ex.task,
            "gold": ex.gold,
            "compute_level": decision.level,
            "first_try_ok": v1.ok,
            "first_failure": first_failure,
            "used_second_solver": used_second,
            "used_critic": used_critic,
            "final_ok": final_v.ok,
            "llm_calls_cumulative": self.metrics.usage.calls,
        }
        with (self.run_dir / "traces.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        return row
