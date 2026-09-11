from __future__ import annotations
import json, re
from dataclasses import dataclass
from typing import Optional, Any
import networkx as nx


@dataclass
class Candidate:
    answer: Optional[bool]
    path: list[int]
    total_weight: Optional[float]
    raw: str


@dataclass
class VerifyResult:
    ok: bool
    code: str
    feedback: str


def _extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if "```" in raw:
        blocks = re.findall(r"```(?:json)?\s*(.*?)```", raw, flags=re.S | re.I)
        if blocks:
            raw = blocks[0].strip()
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if m:
            raw = m.group(0)
    return json.loads(raw)


def parse_candidate(text: str) -> Candidate:
    try:
        obj = _extract_json(text)
        a = obj.get("answer")
        if isinstance(a, str):
            aa = a.strip().lower()
            answer = True if aa in {"yes", "true"} else False if aa in {"no", "false"} else None
        elif isinstance(a, bool):
            answer = a
        else:
            answer = None

        path = [int(x) for x in obj.get("path", [])]
        tw = obj.get("total_weight", None)
        total_weight = float(tw) if tw is not None else None
        return Candidate(answer, path, total_weight, text)
    except Exception:
        return Candidate(None, [], None, text)


def verify_connectivity(ex, c: Candidate) -> VerifyResult:
    if c.answer is None:
        return VerifyResult(False, "FORMAT_ERROR", "Output must be valid JSON with answer yes/no and path.")
    if c.answer:
        if not c.path:
            return VerifyResult(False, "MISSING_WITNESS", "Positive answer needs a path witness.")
        if c.path[0] != ex.source or c.path[-1] != ex.target:
            return VerifyResult(False, "WRONG_ENDPOINTS", "Path endpoints do not match the query.")
        for u, v in zip(c.path, c.path[1:]):
            if not ex.graph.has_edge(u, v):
                return VerifyResult(False, "NON_EDGE_IN_PATH", f"({u},{v}) is not an edge.")

    exact = nx.has_path(ex.graph, ex.source, ex.target)
    if c.answer != exact:
        return VerifyResult(False, "WRONG_CONNECTIVITY", "Decision disagrees with executable graph verification.")
    return VerifyResult(True, "PASS", "Verified.")


def verify_shortest_path(ex, c: Candidate) -> VerifyResult:
    if not c.path:
        return VerifyResult(False, "MISSING_PATH", "Return a non-empty path for the shortest-path task.")
    if c.path[0] != ex.source or c.path[-1] != ex.target:
        return VerifyResult(False, "WRONG_ENDPOINTS", "Shortest-path witness has wrong endpoints.")

    weight = 0.0
    for u, v in zip(c.path, c.path[1:]):
        if not ex.graph.has_edge(u, v):
            return VerifyResult(False, "NON_EDGE_IN_PATH", f"Shortest-path witness contains non-edge ({u},{v}).")
        weight += float(ex.graph[u][v]["weight"])

    optimum = float(nx.shortest_path_length(ex.graph, ex.source, ex.target, weight="weight"))
    if abs(weight - optimum) > 1e-9:
        return VerifyResult(
            False,
            "NON_OPTIMAL_PATH",
            f"The path is valid but its total weight {weight:g} is not the optimal weight. Re-run weighted shortest-path reasoning.",
        )

    if c.total_weight is None:
        return VerifyResult(False, "MISSING_WEIGHT", f"Path is optimal with weight {weight:g}, but total_weight is missing.")
    if abs(c.total_weight - optimum) > 1e-9:
        return VerifyResult(False, "WRONG_WEIGHT", "Reported total_weight does not equal the verified path weight.")

    return VerifyResult(True, "PASS", "Shortest path and total weight verified.")


def verify(ex, c: Candidate) -> VerifyResult:
    if ex.task == "connectivity":
        return verify_connectivity(ex, c)
    if ex.task == "shortest_path":
        return verify_shortest_path(ex, c)
    return VerifyResult(False, "UNSUPPORTED_TASK", f"Unsupported task: {ex.task}")
