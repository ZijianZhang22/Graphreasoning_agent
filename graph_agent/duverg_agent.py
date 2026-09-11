from __future__ import annotations
import json
from pathlib import Path

from .llm import Usage
from .taxonomy import LearnedTaxonomy
from .symbolic import execute_symbolic_code, SymbolicResult


CODER_A_PROMPT = """You are Coder A in a graph-reasoning system.
Generate ONLY Python code, no explanation.
The graph G, SOURCE, TARGET, and networkx as nx are already available.
Do not import anything. Do not define functions. Do not print.
Assign the final answer to RESULT.

For shortest_path:
RESULT = {"path": [...], "total_weight": number}
Use nx.shortest_path(..., weight='weight') and nx.shortest_path_length(..., weight='weight').

For connectivity:
RESULT = {"answer": true/false, "path": [...]}
Use nx.has_path and, when connected, nx.shortest_path.
Prefer concise canonical NetworkX implementations.
"""

CODER_B_PROMPT = """You are Coder B in a graph-reasoning system.
Generate ONLY Python code, no explanation.
The graph G, SOURCE, TARGET, and networkx as nx are already available.
Do not import anything. Do not define functions. Do not print.
Assign the final answer to RESULT.

For shortest_path:
RESULT = {"path": [...], "total_weight": number}
Explicitly preserve edge weights and pass weight='weight' to every weighted shortest-path call.

For connectivity:
RESULT = {"answer": true/false, "path": [...]}
Handle disconnected cases carefully.
Favor robust handling of edge cases and output-schema correctness.
"""

REPAIR_PROMPT = """You repair failed graph-analysis code.
Generate ONLY corrected Python code, no explanation.
The graph G, SOURCE, TARGET, and networkx as nx are already available.
Do not import anything. Do not define functions. Do not print.
Assign the final answer to RESULT.
"""


class Metrics:
    def __init__(self):
        self.usage = Usage()
        self.repairs = 0
        self.disagreements = 0
        self.both_failed = 0
        self.early_agreements = 0

    def add(self, usage):
        self.usage.add(usage)


class DuVerGLiteAgent:
    """
    DuVerG-lite symbolic path + cross-query taxonomy.

    Per query:
      Coder A -> generated program -> restricted execution -> executable verifier
      Coder B -> generated program -> restricted execution -> executable verifier
      agreement / one-sided success / targeted repair on failure

    Across queries:
      executable failure codes are stored in LearnedTaxonomy and injected into
      future coder prompts as concise failure-specific precautions.
    """

    def __init__(self, llm, run_dir, use_taxonomy=True, repair_budget=1):
        self.llm = llm
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.taxonomy = LearnedTaxonomy(self.run_dir / "taxonomy.json")
        self.use_taxonomy = use_taxonomy
        self.repair_budget = repair_budget
        self.metrics = Metrics()

    def _patches(self, ex) -> str:
        if not self.use_taxonomy:
            return ""
        patches = self.taxonomy.relevant_patches(ex, top_k=3)
        if not patches:
            return ""
        text = "\nLessons from previously verified failures:\n"
        for p in patches:
            text += f"- [{p.code}] {p.repair_hint}\n"
        return text

    def _call_code(self, system_prompt: str, ex, extra: str = ""):
        user = (
            f"TASK TYPE: {ex.task}\n"
            f"QUESTION:\n{ex.question}\n"
            f"SOURCE={ex.source}, TARGET={ex.target}\n"
            f"{extra}"
        )
        r = self.llm.complete(system_prompt, user, max_tokens=220)
        self.metrics.add(r.usage)
        return r.text

    @staticmethod
    def _same_answer(a: SymbolicResult, b: SymbolicResult) -> bool:
        if not (a.ok and b.ok and a.candidate and b.candidate):
            return False
        ca, cb = a.candidate, b.candidate
        if ca.path != cb.path:
            return False
        if ca.answer != cb.answer:
            return False
        if ca.total_weight is None and cb.total_weight is None:
            return True
        if ca.total_weight is None or cb.total_weight is None:
            return False
        return abs(ca.total_weight - cb.total_weight) < 1e-9

    def _repair(self, ex, failed: SymbolicResult, label: str) -> SymbolicResult:
        self.metrics.repairs += 1
        extra = f"""
The previous {label} program failed executable verification.
Failure code: {failed.code}
Feedback: {failed.feedback}
Previous code:
{failed.raw_code}

Correct exactly this failure and return a fresh program.
"""
        text = self._call_code(REPAIR_PROMPT + self._patches(ex), ex, extra)
        return execute_symbolic_code(ex, text)

    def run_one(self, ex):
        patches = self._patches(ex)

        text_a = self._call_code(CODER_A_PROMPT + patches, ex)
        a = execute_symbolic_code(ex, text_a)

        text_b = self._call_code(CODER_B_PROMPT + patches, ex)
        b = execute_symbolic_code(ex, text_b)

        initial_failure_codes = []
        if not a.ok:
            initial_failure_codes.append(a.code)
        if not b.ok:
            initial_failure_codes.append(b.code)

        final = None
        resolution = None

        if self._same_answer(a, b):
            self.metrics.early_agreements += 1
            final = a
            resolution = "agreement"
        elif a.ok and b.ok:
            # Both are executable and verified but differ in representation.
            # For shortest path there can be multiple equally optimal paths.
            self.metrics.disagreements += 1
            final = a
            resolution = "both_verified_different"
        elif a.ok and not b.ok:
            final = a
            resolution = "coder_a_only"
        elif b.ok and not a.ok:
            final = b
            resolution = "coder_b_only"
        else:
            self.metrics.both_failed += 1
            resolution = "both_failed"

            ra, rb = a, b
            for _ in range(self.repair_budget):
                if not ra.ok:
                    ra = self._repair(ex, ra, "Coder A")
                if ra.ok:
                    final = ra
                    resolution = "repair_a"
                    break

                if not rb.ok:
                    rb = self._repair(ex, rb, "Coder B")
                if rb.ok:
                    final = rb
                    resolution = "repair_b"
                    break

            if final is None:
                # Best-effort unresolved result; accuracy will be false.
                final = ra if ra.ok else rb

        # Cross-query learning is grounded only in executable failures.
        if self.use_taxonomy:
            if initial_failure_codes:
                for code in initial_failure_codes:
                    self.taxonomy.observe(ex, code)
            else:
                self.taxonomy.observe(ex, None)

        row = {
            "example_id": ex.example_id,
            "task": ex.task,
            "coder_a_ok": a.ok,
            "coder_a_failure": None if a.ok else a.code,
            "coder_b_ok": b.ok,
            "coder_b_failure": None if b.ok else b.code,
            "both_initial_ok": bool(a.ok and b.ok),
            "initial_agreement": self._same_answer(a, b),
            "resolution": resolution,
            "final_ok": bool(final is not None and final.ok),
            "llm_calls_cumulative": self.metrics.usage.calls,
        }

        with (self.run_dir / "traces.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        return row
