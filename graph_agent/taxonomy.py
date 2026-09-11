from __future__ import annotations
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class FailureRule:
    code: str
    count: int
    repair_hint: str
    risk: float


DEFAULT_HINTS = {
    "FORMAT_ERROR": "Return only valid JSON in the task-specific schema.",
    "MISSING_WITNESS": "If answering yes, explicitly construct a source-to-target witness path.",
    "MISSING_PATH": "Always return a concrete source-to-target path for shortest-path tasks.",
    "WRONG_ENDPOINTS": "Check that the path starts at the requested source and ends at the requested target.",
    "NON_EDGE_IN_PATH": "Validate every consecutive edge in the path before returning it.",
    "WRONG_CONNECTIVITY": "Run an explicit BFS/DFS instead of guessing from local adjacency.",
    "NON_OPTIMAL_PATH": "For weighted shortest path, compare cumulative costs and use Dijkstra-style reasoning rather than minimizing hop count.",
    "MISSING_WEIGHT": "Report total_weight explicitly after summing all edge weights on the final path.",
    "WRONG_WEIGHT": "Recompute the sum of edge weights along the returned path and make total_weight match it exactly.",
}


class LearnedTaxonomy:
    """
    Lightweight cross-query failure learner inspired by AdaMAST.

    It stores recurring failure modes and retrieves the most relevant repair
    instructions for future examples. In this prototype the failure vocabulary
    comes from executable graph verifiers; the full AdaMAST runtime can later
    replace this class to induce/refine taxonomy entries automatically.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.counts = Counter()
        self.total = 0
        self.by_signature = defaultdict(Counter)
        self.rules = {}
        if self.path.exists():
            self._load()

    @staticmethod
    def signature(ex):
        n = ex.graph.number_of_nodes()
        m = ex.graph.number_of_edges()
        density = 0.0 if n < 2 else 2 * m / (n * (n - 1))
        size_bucket = "small" if n <= 10 else "medium" if n <= 30 else "large"
        dens_bucket = "sparse" if density < 0.15 else "dense"
        return f"{ex.task}:{size_bucket}:{dens_bucket}"

    def observe(self, ex, failure_code):
        self.total += 1
        sig = self.signature(ex)
        if failure_code and failure_code != "PASS":
            self.counts[failure_code] += 1
            self.by_signature[sig][failure_code] += 1
        self._rebuild()
        self._save()

    def _rebuild(self):
        denom = max(self.total, 1)
        self.rules = {
            code: FailureRule(
                code=code,
                count=count,
                repair_hint=DEFAULT_HINTS.get(code, "Re-check this failure mode explicitly."),
                risk=count / denom,
            )
            for code, count in self.counts.items()
        }

    def relevant_patches(self, ex, top_k=3):
        sig = self.signature(ex)
        local = self.by_signature.get(sig, Counter())
        ranked = [self.rules[code] for code, _ in local.most_common() if code in self.rules]
        if not ranked:
            ranked = sorted(self.rules.values(), key=lambda r: r.count, reverse=True)
        return ranked[:top_k]

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "total": self.total,
            "counts": dict(self.counts),
            "by_signature": {k: dict(v) for k, v in self.by_signature.items()},
            "rules": {k: asdict(v) for k, v in self.rules.items()},
        }
        self.path.write_text(json.dumps(payload, indent=2))

    def _load(self):
        obj = json.loads(self.path.read_text())
        self.total = obj.get("total", 0)
        self.counts = Counter(obj.get("counts", {}))
        self.by_signature = defaultdict(Counter)
        for k, v in obj.get("by_signature", {}).items():
            self.by_signature[k] = Counter(v)
        self._rebuild()
