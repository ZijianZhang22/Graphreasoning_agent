from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import networkx as nx

@dataclass
class Example:
    example_id: str
    graph: nx.Graph
    source: int
    target: int
    question: str
    gold: bool

def parse_nlgraph_connectivity_file(path):
    path = Path(path)
    rows = [[int(x) for x in line.split()] for line in path.read_text().splitlines() if line.strip()]
    n, m, q = rows[0]
    edges = rows[1:1+m]
    queries = rows[1+m:1+m+2*q]
    g = nx.Graph()
    g.add_nodes_from(range(n))
    g.add_edges_from(edges)

    edge_text = " ".join(f"({u},{v})" for u, v in g.edges())
    out = []
    for i, pair in enumerate(queries):
        s, t = pair[:2]
        out.append(Example(
            example_id=f"{path.stem}-q{i}",
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

def load_examples(nlgraph_root, difficulty="easy", limit=30):
    folder = Path(nlgraph_root) / "NLGraph" / "connectivity" / "graph" / difficulty / "standard"
    if not folder.exists():
        raise FileNotFoundError(f"Cannot find {folder}")
    files = sorted(folder.glob("graph*.txt"),
                   key=lambda p: int(p.stem.replace("graph", "")))
    examples = []
    for fp in files:
        examples.extend(parse_nlgraph_connectivity_file(fp))
        if len(examples) >= limit:
            break
    return examples[:limit]
