"""
[V13.0] J.A.R.V.I.S. Environment Semantic Graph
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Replaces the flat WorldStateModel with a true dynamic Graph.
Nodes: Apps, Windows, Entities, Workflows, Goals
Edges: related_to, depends_on, likely_next, belongs_to_workflow
All cognition uses this graph for reasoning.
"""
import logging
import time
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

logger = logging.getLogger("JARVIS.EnvironmentGraph")

@dataclass
class GraphNode:
    id: str
    type: str  # "app", "window", "entity", "workflow", "goal", "ui_component"
    label: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    activity_score: float = 1.0

@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    relation_type: str  # "related_to", "belongs_to", "likely_next", "caused_by"
    weight: float = 1.0
    last_updated: float = field(default_factory=time.time)


class EnvironmentGraph:
    """
    [V13.0] Central Semantic Graph of the User's Environment
    """
    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        
        # Fast lookups
        self._adj_list: Dict[str, Dict[str, List[GraphEdge]]] = defaultdict(lambda: defaultdict(list))
        
        self.active_window_id: Optional[str] = None
        self.active_app_id: Optional[str] = None
        self.last_update = time.time()
        self.last_user_action = time.time()

    # ── GRAPH OPERATIONS ──

    def add_node(self, node_type: str, label: str, attributes: Dict[str, Any] = None) -> GraphNode:
        """Adds or updates a node, returning the node object."""
        # Generate deterministic ID for some types to prevent duplicates
        if node_type in ("app", "window"):
            node_id = hashlib.md5(f"{node_type}_{label}".encode()).hexdigest()[:12]
        else:
            node_id = f"{node_type[:3]}_{hashlib.md5(f'{label}_{time.time()}'.encode()).hexdigest()[:8]}"
            
        if node_id in self.nodes:
            self.nodes[node_id].last_seen = time.time()
            self.nodes[node_id].activity_score += 1.0
            if attributes:
                self.nodes[node_id].attributes.update(attributes)
            return self.nodes[node_id]
            
        node = GraphNode(id=node_id, type=node_type, label=label, attributes=attributes or {})
        self.nodes[node_id] = node
        return node

    def add_edge(self, source_id: str, target_id: str, relation: str, weight: float = 1.0):
        """Adds or updates a directed edge."""
        if source_id not in self.nodes or target_id not in self.nodes:
            return
            
        # Check if edge exists
        existing = None
        for edge in self._adj_list[source_id][target_id]:
            if edge.relation_type == relation:
                existing = edge
                break
                
        if existing:
            existing.weight = min(1.0, existing.weight + weight * 0.1)
            existing.last_updated = time.time()
        else:
            edge = GraphEdge(source_id, target_id, relation, weight)
            self.edges.append(edge)
            self._adj_list[source_id][target_id].append(edge)
            # Bi-directional tracking for undirected traversal
            if relation in ("related_to", "belongs_to"):
                self._adj_list[target_id][source_id].append(
                    GraphEdge(target_id, source_id, relation, weight)
                )

    def get_related_nodes(self, node_id: str, threshold: float = 0.0) -> List[str]:
        """Gets all node IDs related to the given node_id."""
        related = []
        for target, edges in self._adj_list.get(node_id, {}).items():
            if any(e.weight >= threshold for e in edges):
                related.append(target)
        return related

    def get_edge_weight(self, source_id: str, target_id: str) -> float:
        edges = self._adj_list.get(source_id, {}).get(target_id, [])
        if not edges: return 0.0
        return max(e.weight for e in edges)

    # ── SEMANTIC STATE UPDATES ──

    async def update_state(self, updates: Dict[str, Any]):
        """Translates raw state updates into graph operations."""
        now = time.time()
        self.last_update = now
        
        # 1. Update Active App & Window
        if "active_window" in updates:
            win_title = updates["active_window"]
            app_name = updates.get("active_app_name", self._extract_app(win_title))
            
            app_node = self.add_node("app", app_name)
            win_node = self.add_node("window", win_title, {"app": app_name})
            
            self.add_edge(win_node.id, app_node.id, "belongs_to")
            
            # Workflow transition logic
            if self.active_window_id and self.active_window_id != win_node.id:
                # User switched windows -> likely next relation
                self.add_edge(self.active_window_id, win_node.id, "likely_next", 0.5)
                # If they switch back and forth, they are highly related
                self.add_edge(self.active_window_id, win_node.id, "related_to", 0.2)
                
            self.active_window_id = win_node.id
            self.active_app_id = app_node.id
            self.last_user_action = now

        # 2. Update Visual Entities (Semantic UI Cognition)
        if "visual_entities" in updates:
            self._update_ui_hierarchy(updates["visual_entities"])

        # Decay graph
        self._decay_graph()
        
        if self.event_bus:
            await self.event_bus.emit("WORLD_STATE_UPDATED", self.get_situation_assessment(), sender="EnvironmentGraph")

    def _update_ui_hierarchy(self, entities: List[Dict[str, Any]]):
        """Builds a UI hierarchy graph instead of a flat list."""
        if not self.active_window_id: return
        
        current_ui_nodes = []
        for ed in entities:
            ui_node = self.add_node("ui_component", ed.get("label", "unnamed"), ed)
            self.add_edge(ui_node.id, self.active_window_id, "belongs_to", 1.0)
            current_ui_nodes.append(ui_node)
            
        # Optional: hierarchical spatial relations (e.g. Button A is inside Container B)
        # This requires bbox containment logic, omitted for brevity but implied.

    def _extract_app(self, title: str) -> str:
        if not title: return "Unknown"
        for sep in [" - ", " — ", " | "]:
            if sep in title: return title.split(sep)[-1].strip()
        return title.strip()

    def _decay_graph(self):
        """Graph activity decays over time. Old/unused nodes are pruned."""
        now = time.time()
        to_delete_nodes = []
        
        for nid, node in self.nodes.items():
            age = now - node.last_seen
            if age > 60: # 1 min
                node.activity_score *= 0.95
                
            if age > 3600 and node.activity_score < 0.1: # 1 hr inactive
                to_delete_nodes.append(nid)

        if len(self.nodes) - len(to_delete_nodes) > 50:
            remaining = [n for nid, n in self.nodes.items() if nid not in to_delete_nodes]
            remaining.sort(key=lambda x: (x.activity_score, x.last_seen))
            to_delete_nodes.extend(n.id for n in remaining[:-50])
                
        for nid in to_delete_nodes:
            self._remove_node(nid)

    def _remove_node(self, node_id: str):
        if node_id in self.nodes:
            del self.nodes[node_id]
        # Remove edges
        self.edges = [e for e in self.edges if e.source_id != node_id and e.target_id != node_id]
        if node_id in self._adj_list:
            del self._adj_list[node_id]
        for target, edges in self._adj_list.items():
            if node_id in edges:
                del edges[node_id]

    # ── QUERIES FOR COGNITIVE ENGINE ──

    def get_situation_assessment(self) -> Dict[str, Any]:
        """Returns a snapshot of the active subgraph."""
        now = time.time()
        idle = now - self.last_user_action
        
        active_app = self.nodes.get(self.active_app_id) if self.active_app_id else None
        active_win = self.nodes.get(self.active_window_id) if self.active_window_id else None
        
        # Get active subgraph (nodes related to current app)
        subgraph = []
        if self.active_app_id:
            related = self.get_related_nodes(self.active_app_id, threshold=0.3)
            subgraph = [self.nodes[n].label for n in related if n in self.nodes and self.nodes[n].type == "app"]
        
        return {
            "user_activity": "idle" if idle > 300 else "active",
            "active_app": active_app.label if active_app else "Unknown",
            "active_window": active_win.label if active_win else "Unknown",
            "related_apps_in_context": subgraph,
            "total_nodes": len(self.nodes),
            "idle_seconds": idle
        }
        
    def get_active_app_name(self) -> str:
        app = self.nodes.get(self.active_app_id)
        return app.label if app else "Unknown"
        
    def get_active_window(self) -> str:
        win = self.nodes.get(self.active_window_id)
        return win.label if win else "Unknown"
