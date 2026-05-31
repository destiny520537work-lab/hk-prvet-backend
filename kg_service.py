"""
KG service — clean interface over NetworkX graph.

External callers only use:
    kg = KGService()
    kg.get_graph_data()       -> {nodes, edges, riskPaths}
    kg.find_risk_paths(id)    -> list of paths

To migrate to Neo4j: replace _build_graph() internals,
keep public methods identical.
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from kg_data import KG_EDGES, KG_NODES, KG_RISK_PATHS


class KGService:
    def __init__(self) -> None:
        self._G: nx.DiGraph = nx.DiGraph()
        self._nodes = KG_NODES
        self._edges = KG_EDGES
        self._risk_paths = KG_RISK_PATHS
        self._build_graph()

    def _build_graph(self) -> None:
        for node in self._nodes:
            self._G.add_node(node["id"], **node)
        for edge in self._edges:
            self._G.add_edge(edge["source"], edge["target"], **edge)

    def get_graph_data(self) -> dict[str, Any]:
        """Return nodes, edges, and pre-computed risk paths for frontend rendering."""
        return {
            "nodes": self._nodes,
            "edges": self._edges,
            "riskPaths": self._risk_paths,
        }

    def find_risk_paths(self, company_id: str, max_hops: int = 3) -> list[dict]:
        """Find all paths from company_id to high-risk nodes (within max_hops)."""
        if company_id not in self._G:
            return []

        high_risk_nodes = [
            n for n, d in self._G.nodes(data=True)
            if d.get("risk") == "high" and n != company_id
        ]

        found: list[dict] = []
        for target in high_risk_nodes:
            try:
                path = nx.shortest_path(self._G, company_id, target)
                if len(path) - 1 <= max_hops:
                    node_labels = [
                        self._G.nodes[n].get("label", n) for n in path
                    ]
                    found.append({
                        "path_ids": path,
                        "path_labels": node_labels,
                        "target_risk": self._G.nodes[target].get("risk"),
                        "hops": len(path) - 1,
                    })
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                pass

        return found

    def get_node(self, node_id: str) -> dict | None:
        if node_id not in self._G:
            return None
        return dict(self._G.nodes[node_id])


# Module-level singleton — initialized once at import time
_kg: KGService | None = None


def get_kg() -> KGService:
    global _kg
    if _kg is None:
        _kg = KGService()
    return _kg
