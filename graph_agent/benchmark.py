from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import networkx as nx


@dataclass
class Example:
    example_id: str
    task: str
    graph: nx.Graph
    source: int
    target: int
    question: str
    gold: Any


def _locate_folder(root: Path, task: str, difficulty: str) -> Path:
    candidates = [
        root / "NLGraph" / task / "graph" / difficulty / "standard",
        root / "NLgraph" / task / "graph" / difficulty / "standard",
    ]
    for folder in candidates:
        if folder.exists() and any(folder.glob("graph*.txt")):
            return folder

    matches = [
        p.parent for p in root.rglob("graph0.txt")
        if task.lower() in str(p).lower()
        and difficulty.lower() in str(p).lower()
        and "standard" in str(p).lower()
    ]
    if matches:
        return matches[0]
    raise FileNotFoundError(
        f"Could not locate NLGraph task={task}, difficulty={difficulty} under {root}"
    )


def parse_connectivity_file(path: Path) -> list[Example]:
    rows = [[int(x) for x in line.split()] for line in path.read_text().splitlines() if line.strip()]
    n, m, q = rows[0]
    edges = rows[1:1 + m]
    queries = rows[1 + m:1 + m + 2 * q]
    g = nx.Graph()
    g.add_nodes_from(range(n))
    g.add_edges_from(edges)
    edge_text = " ".join(f"({u},{v})" for u, v in g.edges())

    out = []
    for i, pair in enumerate(queries):
        s, t = pair[:2]
        out.append(Example(
            example_id=f"{path.stem}-q{i}",
            task="connectivity",
            graph=g.copy(),
            source=s,
            target=t,
            question=(
                "Determine whether there is a path between the two queried nodes. "
                "The graph is undirected.\n"
                f"Graph: {edge_text}\n"
                f"Q: Is there a path between node {s} and node {t}?"
            ),
            gold=nx.has_path(g, s, t),
        ))
    return out


def parse_shortest_path_file(path: Path) -> list[Example]:
    rows = [[int(x) for x in line.split()] for line in path.read_text().splitlines() if line.strip()]
    n, m = rows[0]
    edges = rows[1:1 + m]
    s, t = rows[1 + m][:2]

    g = nx.Graph()
    g.add_nodes_from(range(n))
    for u, v, w in edges:
        g.add_edge(u, v, weight=w)

    edge_lines = "\n".join(
        f"edge {u}-{v} with weight {w}" for u, v, w in edges
    )
    shortest_weight = nx.shortest_path_length(g, source=s, target=t, weight="weight")
    gold_path = nx.shortest_path(g, source=s, target=t, weight="weight")

    return [Example(
        example_id=path.stem,
        task="shortest_path",
        graph=g,
        source=s,
        target=t,
        question=(
            f"In an undirected weighted graph, nodes are numbered 0 to {n-1}.\n"
            f"Edges:\n{edge_lines}\n"
            f"Q: Give a shortest path from node {s} to node {t}."
        ),
        gold={"path": gold_path, "total_weight": shortest_weight},
    )]


def load_examples(nlgraph_root, difficulty="hard", limit=100, task="shortest_path"):
    root = Path(nlgraph_root)
    folder = _locate_folder(root, task, difficulty)
    print(f"[benchmark] task={task} difficulty={difficulty} folder={folder}")

    graph_files = sorted(
        folder.glob("graph*.txt"),
        key=lambda p: int(p.stem.replace("graph", "")),
    )

    examples = []
    for fp in graph_files:
        if task == "connectivity":
            examples.extend(parse_connectivity_file(fp))
        elif task == "shortest_path":
            examples.extend(parse_shortest_path_file(fp))
        else:
            raise ValueError(f"Unsupported task: {task}")
        if len(examples) >= limit:
            break

    if not examples:
        raise RuntimeError(f"No examples loaded from {folder}")
    return examples[:limit]
