from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Tuple

from core.evidence_ledger import EvidenceLedgerSingleton


@dataclass
class Node:
    id: str
    label: str
    attrs: Dict[str, str]


class KnowledgeGraph:
    """Lightweight in-memory knowledge graph with audit logging.

    Supports adding nodes, edges (subject, predicate, object), and simple
    neighborhood queries. Designed for local testing and progressive
    enhancement into a persistent graph DB.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._nodes: Dict[str, Node] = {}
        self._edges: List[Tuple[str, str, str]] = []  # (subj, pred, obj)

    def add_node(self, node_id: str, label: str, attrs: Dict[str, str]) -> None:
        with self._lock:
            self._nodes[node_id] = Node(id=node_id, label=label, attrs=dict(attrs))
            EvidenceLedgerSingleton.append_entry(
                tenant_id="system",
                actor="knowledge_graph",
                action="add_node",
                payload={"node_id": node_id, "label": label},
            )

    def add_edge(self, subj: str, pred: str, obj: str) -> None:
        with self._lock:
            self._edges.append((subj, pred, obj))
            EvidenceLedgerSingleton.append_entry(
                tenant_id="system",
                actor="knowledge_graph",
                action="add_edge",
                payload={"subj": subj, "pred": pred, "obj": obj},
            )

    def neighbors(self, node_id: str) -> List[Tuple[str, str]]:
        with self._lock:
            out = [(pred, obj) for (subj, pred, obj) in self._edges if subj == node_id]
            return out

    def find_by_label(self, label: str) -> List[Node]:
        with self._lock:
            return [n for n in self._nodes.values() if n.label == label]


KnowledgeGraphSingleton = KnowledgeGraph()
