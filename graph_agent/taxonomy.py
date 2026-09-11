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
    "FORMAT_ERROR": "Return only the required JSON schema.",
    "MISSING_WITNESS": "If answering yes, explicitly construct a source-to-target witness path.",
    "WRONG_ENDPOINTS": "Check that the witness starts at the source and ends at the target.",
    "NON_EDGE_IN_PATH": "Validate every consecutive edge in the witness before returning it.",
    "WRONG_CONNECTIVITY": "Run an explicit BFS/DFS instead of guessing from local adjacency."
}

class LearnedTaxonomy:
    """
    AdaMAST-inspired lightweight taxonomy learner for the first experiment.

    This is deliberately simpler than the full AdaMAST generation/refinement
    pipeline: it learns failure frequencies and reusable repair policies from
    traces, then turns them into a risk score and prompt patches.
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
        density = 0.0 if n < 2 else 2*m/(n*(n-1))
        bucket = "small" if n <= 10 else "medium" if n <= 30 else "large"
        dens = "sparse" if density < 0.15 else "dense"
        return f"{bucket}:{dens}"

    def observe(self, ex, failure_code):
        self.total += 1
        sig = self.signature(ex)
        if failure_code and failure_code != "PASS":
            self.counts[failure_code] += 1
            self.by_signature[sig][failure_code] += 1
        self._rebuild()
        self._save()

    def _rebuild(self):
        rules = {}
        denom = max(self.total, 1)
        for code, count in self.counts.items():
            rules[code] = FailureRule(
                code=code,
                count=count,
                repair_hint=DEFAULT_HINTS.get(code, "Re-check this failure mode explicitly."),
                risk=count/denom,
            )
        self.rules = rules

    def relevant_patches(self, ex, top_k=2):
        sig = self.signature(ex)
        local = self.by_signature.get(sig, Counter())
        ranked = []
        for code, count in local.most_common():
            if code in self.rules:
                ranked.append(self.rules[code])
        if not ranked:
            ranked = sorted(self.rules.values(), key=lambda r: r.count, reverse=True)
        return ranked[:top_k]

    def risk(self, ex):
        sig = self.signature(ex)
        local = self.by_signature.get(sig, Counter())
        seen = sum(local.values())
        return min(1.0, seen / max(3, self.total * 0.25))

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
