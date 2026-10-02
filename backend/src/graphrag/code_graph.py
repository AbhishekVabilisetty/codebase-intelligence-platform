"""Build and traverse a lightweight, serialisable code knowledge graph."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Set, Tuple

from src.models import CodeEntity


def _file_node(path: str) -> str:
    return f"file:{path}"


def _entity_node(entity: CodeEntity) -> str:
    """Names collide across files, so symbols have stable, location-based IDs."""
    return f"entity:{entity.file_path}:{entity.line_number}:{entity.type}:{entity.name}"


def build_code_graph(entities: Iterable[CodeEntity]) -> Dict[str, Any]:
    """Create file-to-symbol and resolved symbol-usage edges."""
    entities = list(entities)
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, str]] = []
    by_name: Dict[str, List[str]] = defaultdict(list)

    for entity in entities:
        file_id, entity_id = _file_node(entity.file_path), _entity_node(entity)
        nodes.setdefault(file_id, {"id": file_id, "kind": "file", "file_path": entity.file_path})
        nodes[entity_id] = {"id": entity_id, "kind": "entity", "name": entity.name,
                            "entity_type": entity.type, "file_path": entity.file_path,
                            "line_number": entity.line_number}
        edges.append({"source": file_id, "target": entity_id, "type": "DEFINES"})
        if entity.type != "import":
            by_name[entity.name].append(entity_id)

    seen: Set[Tuple[str, str, str]] = {(e["source"], e["target"], e["type"]) for e in edges}
    for entity in entities:
        source = _entity_node(entity)
        for dependency in entity.dependencies:
            for target in by_name.get(dependency, []):
                key = (source, target, "USES")
                if target != source and key not in seen:
                    edges.append({"source": source, "target": target, "type": "USES"})
                    seen.add(key)
    return {"version": 1, "nodes": list(nodes.values()), "edges": edges}


class CodeGraphRetriever:
    """Expand semantic-search seeds through bounded dependency neighbours."""
    def __init__(self, graph: Dict[str, Any]):
        self.nodes = {node["id"]: node for node in graph.get("nodes", []) if node.get("id")}
        self.neighbours: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for edge in graph.get("edges", []):
            source, target = edge.get("source"), edge.get("target")
            if source in self.nodes and target in self.nodes:
                relation = edge.get("type", "RELATED")
                self.neighbours[source].append((target, relation))
                self.neighbours[target].append((source, relation))

    def expand(self, seed_chunks: List[Dict[str, Any]], max_hops: int = 2, max_entities: int = 12) -> List[Dict[str, Any]]:
        seed_ids = self._seed_nodes(seed_chunks)
        queue = deque((node_id, 0, []) for node_id in seed_ids)
        visited, results = set(seed_ids), []
        while queue and len(results) < max_entities:
            node_id, depth, relations = queue.popleft()
            node = self.nodes[node_id]
            if depth and node.get("kind") == "entity":
                results.append({"file_path": node["file_path"], "name": node.get("name", ""),
                                "line_number": node.get("line_number"), "hops": depth,
                                "relations": relations})
            if depth >= max_hops:
                continue
            for neighbour, relation in self.neighbours[node_id]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append((neighbour, depth + 1, relations + [relation]))
        return results

    def _seed_nodes(self, chunks: List[Dict[str, Any]]) -> List[str]:
        seeds = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            file_path, name = metadata.get("file_path"), metadata.get("name")
            for node_id, node in self.nodes.items():
                if node.get("file_path") != file_path:
                    continue
                if node.get("kind") == "file" or (name and node.get("name") == name):
                    seeds.append(node_id)
        return list(dict.fromkeys(seeds))
