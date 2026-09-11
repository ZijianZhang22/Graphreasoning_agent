from __future__ import annotations
import ast
import json
import re
from dataclasses import dataclass
from typing import Optional
import networkx as nx

from .verifier import Candidate, VerifyResult, verify


@dataclass
class SymbolicResult:
    ok: bool
    code: str
    feedback: str
    candidate: Optional[Candidate]
    raw_code: str


ALLOWED_NX_CALLS = {
    "shortest_path",
    "shortest_path_length",
    "has_path",
}


def extract_code(text: str) -> str:
    raw = text.strip()
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", raw, flags=re.S | re.I)
    if blocks:
        return blocks[0].strip()
    return raw


def _validate_ast(code: str) -> tuple[bool, str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    allowed_nodes = (
        ast.Module,
        ast.Assign,
        ast.Name,
        ast.Store,
        ast.Load,
        ast.Dict,
        ast.List,
        ast.Tuple,
        ast.Constant,
        ast.Call,
        ast.Attribute,
        ast.keyword,
        ast.Expr,
        ast.UnaryOp,
        ast.USub,
    )

    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            return False, f"Disallowed syntax: {type(node).__name__}"
        if isinstance(node, ast.Name):
            if node.id not in {"RESULT", "G", "SOURCE", "TARGET", "nx"}:
                return False, f"Disallowed name: {node.id}"
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Attribute):
                return False, "Only networkx function calls are allowed."
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "nx":
                return False, "Only nx.<function>(...) calls are allowed."
            if node.func.attr not in ALLOWED_NX_CALLS:
                return False, f"Disallowed networkx call: nx.{node.func.attr}"

    assigned_result = any(
        isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "RESULT" for t in node.targets)
        for node in tree.body
    )
    if not assigned_result:
        return False, "Code must assign a final dictionary to RESULT."
    return True, "OK"


def _static_failure_code(code: str, task: str) -> Optional[tuple[str, str]]:
    if task == "shortest_path":
        if "nx.shortest_path(" in code and 'weight="weight"' not in code and "weight='weight'" not in code:
            return (
                "MISSING_WEIGHT_ARG",
                "Weighted shortest path must pass weight='weight' to nx.shortest_path.",
            )
        if "nx.shortest_path_length(" in code and 'weight="weight"' not in code and "weight='weight'" not in code:
            return (
                "MISSING_WEIGHT_ARG",
                "Weighted shortest path length must pass weight='weight'.",
            )
    return None


def execute_symbolic_code(ex, text: str) -> SymbolicResult:
    code = extract_code(text)

    ok, msg = _validate_ast(code)
    if not ok:
        return SymbolicResult(False, "UNSAFE_OR_INVALID_CODE", msg, None, code)

    static_failure = _static_failure_code(code, ex.task)
    if static_failure:
        return SymbolicResult(False, static_failure[0], static_failure[1], None, code)

    env = {
        "__builtins__": {},
        "nx": nx,
        "G": ex.graph.copy(),
        "SOURCE": ex.source,
        "TARGET": ex.target,
    }

    try:
        exec(compile(code, "<generated_graph_code>", "exec"), env, env)
    except Exception as e:
        return SymbolicResult(False, "EXECUTION_ERROR", f"{type(e).__name__}: {e}", None, code)

    result = env.get("RESULT")
    if not isinstance(result, dict):
        return SymbolicResult(False, "BAD_RESULT", "RESULT must be a dictionary.", None, code)

    try:
        if ex.task == "shortest_path":
            candidate = Candidate(
                answer=None,
                path=[int(x) for x in result.get("path", [])],
                total_weight=float(result["total_weight"]) if result.get("total_weight") is not None else None,
                raw=json.dumps(result),
            )
        elif ex.task == "connectivity":
            answer = result.get("answer")
            if isinstance(answer, str):
                answer = answer.lower() in {"yes", "true"}
            candidate = Candidate(
                answer=bool(answer) if answer is not None else None,
                path=[int(x) for x in result.get("path", [])],
                total_weight=None,
                raw=json.dumps(result),
            )
        else:
            return SymbolicResult(False, "UNSUPPORTED_TASK", ex.task, None, code)
    except Exception as e:
        return SymbolicResult(False, "BAD_RESULT", f"Could not parse RESULT: {e}", None, code)

    vr: VerifyResult = verify(ex, candidate)
    return SymbolicResult(vr.ok, vr.code, vr.feedback, candidate, code)
