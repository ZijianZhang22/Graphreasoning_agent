from __future__ import annotations
import json, re
from dataclasses import dataclass
from typing import Optional
import networkx as nx

@dataclass
class Candidate:
    answer: Optional[bool]
    path: list[int]
    raw: str

@dataclass
class VerifyResult:
    ok: bool
    code: str
    feedback: str

def parse_candidate(text: str) -> Candidate:
    raw = text.strip()
    try:
        if "```" in raw:
            blocks = re.findall(r"```(?:json)?\s*(.*?)```", raw, flags=re.S | re.I)
            if blocks:
                raw = blocks[0].strip()
        if not raw.startswith("{"):
            m = re.search(r"\{.*\}", raw, flags=re.S)
            if m:
                raw = m.group(0)
        obj = json.loads(raw)
        a = obj.get("answer")
        if isinstance(a, str):
            a = a.strip().lower()
            answer = True if a in {"yes", "true"} else False if a in {"no", "false"} else None
        elif isinstance(a, bool):
            answer = a
        else:
            answer = None
        path = [int(x) for x in obj.get("path", [])]
        return Candidate(answer, path, text)
    except Exception:
        return Candidate(None, [], text)

def verify(ex, c: Candidate) -> VerifyResult:
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
        return VerifyResult(False, "WRONG_CONNECTIVITY",
                            "Decision disagrees with executable graph verification.")
    return VerifyResult(True, "PASS", "Verified.")
