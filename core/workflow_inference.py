"""
[V13.0] J.A.R.V.I.S. Semantic Workflow Inference Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NO HARDCODED RULES. No `if "vscode" in title`.
This engine uses:
- Statistical transition matrices
- Temporal sequence modeling
- Context entity overlap
- Interaction density
to infer workflow phases, multi-app coordination, and continuations.
"""
import time
import math
import logging
from typing import Dict, List, Any, Optional
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger("JARVIS.WorkflowInference")

@dataclass
class WorkflowPhase:
    name: str
    start_time: float
    end_time: Optional[float] = None
    involved_nodes: set = field(default_factory=set)
    dominant_interaction: str = ""
    cohesion_score: float = 0.0

@dataclass
class ActiveWorkflow:
    id: str
    phases: List[WorkflowPhase] = field(default_factory=list)
    active_phase: Optional[WorkflowPhase] = None
    context_entities: set = field(default_factory=set)
    last_updated: float = field(default_factory=time.time)
    confidence: float = 0.0
    predicted_next_phase: str = ""

class WorkflowInferenceEngine:
    """
    Infers workflows based on temporal dynamics and semantic entity overlap.
    """
    def __init__(self, environment_graph):
        self.env_graph = environment_graph
        self.active_workflows: Dict[str, ActiveWorkflow] = {}
        
        # Statistical models (learned over time, NOT hardcoded)
        # Transition matrix: phase A -> phase B frequency
        self._transition_matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # App co-occurrence matrix: App A + App B in same session
        self._cooccurrence_matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        self._recent_events = []
        self._max_events = 200
        self._last_inference = 0.0
        
    def observe_transition(self, from_node: str, to_node: str, duration: float, context_overlap: float):
        """Record a semantic transition between environment nodes."""
        now = time.time()
        self._recent_events.append({
            "from": from_node, "to": to_node, "duration": duration,
            "overlap": context_overlap, "time": now
        })
        if len(self._recent_events) > self._max_events:
            self._recent_events.pop(0)
            
        # Update statistical co-occurrence and transition
        # [V13.1] Duration-weighted transitions to resist quick interruptions
        weight = 1.0 + math.log1p(max(0, duration))
        self._transition_matrix[from_node][to_node] += weight
        self._cooccurrence_matrix[from_node][to_node] += weight
        self._cooccurrence_matrix[to_node][from_node] += weight

    def infer_current_workflow(self) -> List[ActiveWorkflow]:
        """
        Calculates the probability of active workflows based on recent node activity,
        graph clustering, and interaction density.
        """
        now = time.time()
        
        # 1. Temporal Clustering: Find recent high-interaction nodes
        recent_nodes = set()
        interaction_density = defaultdict(float)
        
        for event in self._recent_events[-20:]: # Last 20 events
            age = now - event["time"]
            weight = math.exp(-age / 120.0) # Decay over 2 minutes
            interaction_density[event["from"]] += weight * event["duration"]
            interaction_density[event["to"]] += weight * event["duration"]
            recent_nodes.add(event["from"])
            recent_nodes.add(event["to"])
            
        if not recent_nodes:
            return []

        # 2. Graph Context Cohesion: Are these nodes connected in the Environment Graph?
        # We calculate a cohesion score based on edge weights in the environment graph
        clusters = self._find_semantic_clusters(recent_nodes)
        
        inferred = []
        for cluster in clusters:
            cohesion = self._calculate_cluster_cohesion(cluster)
            
            # Formulate workflow hypothesis
            wf_id = self._generate_cluster_signature(cluster)
            
            if wf_id in self.active_workflows:
                wf = self.active_workflows[wf_id]
                wf.last_updated = now
                wf.confidence = min(0.95, wf.confidence * 0.8 + cohesion * 0.2)
                wf.context_entities.update(cluster)
            else:
                wf = ActiveWorkflow(
                    id=wf_id,
                    context_entities=set(cluster),
                    confidence=cohesion,
                    last_updated=now
                )
                self.active_workflows[wf_id] = wf
            
            # Predict next phase based on historical transition matrix
            wf.predicted_next_phase = self._predict_next_node(cluster)
            inferred.append(wf)
            
        # Decay inactive workflows
        self._decay_workflows(now)
        
        # Return sorted by confidence
        return sorted(inferred, key=lambda w: w.confidence, reverse=True)

    def _find_semantic_clusters(self, nodes: set) -> List[set]:
        """
        Groups nodes that share strong semantic edges or context overlap,
        ignoring superficial differences.
        """
        # This is a lightweight graph clustering (like connected components but weighted)
        clusters = []
        unvisited = set(nodes)
        
        while unvisited:
            node = unvisited.pop()
            current_cluster = {node}
            
            # Expand cluster based on semantic environment graph edges (ignore 'likely_next' single transitions)
            neighbors = []
            for target, edges in self.env_graph._adj_list.get(node, {}).items():
                if any(e.relation_type in ("related_to", "belongs_to") and e.weight >= 0.2 for e in edges):
                    neighbors.append(target)
            for neighbor in neighbors:
                if neighbor in unvisited:
                    current_cluster.add(neighbor)
                    unvisited.remove(neighbor)
                    
            clusters.append(current_cluster)
            
        return clusters

    def _calculate_cluster_cohesion(self, cluster: set) -> float:
        """Calculates how tightly coupled the nodes in a cluster are."""
        if len(cluster) <= 1:
            return 0.3 # Low cohesion for single node
            
        edges_found = 0
        total_possible = len(cluster) * (len(cluster) - 1) / 2
        
        nodes = list(cluster)
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                weight = self.env_graph.get_edge_weight(nodes[i], nodes[j])
                if weight > 0.1:
                    edges_found += weight
                    
        return min(1.0, (edges_found / max(1, total_possible)) + 0.2)

    def _generate_cluster_signature(self, cluster: set) -> str:
        """Generates a stable ID for a set of nodes."""
        return "WF_" + "_".join(sorted(list(cluster)))[:30]

    def _predict_next_node(self, current_cluster: set) -> str:
        """Uses Markov-like transition matrices + co-occurrence to predict likely next state."""
        predictions = defaultdict(float)
        for node in current_cluster:
            transitions = self._transition_matrix.get(node, {})
            total = sum(transitions.values())
            if total > 0:
                for next_node, count in transitions.items():
                    if next_node not in current_cluster:
                        # Base probability from Markov transition
                        prob = count / total
                        # Boost by co-occurrence with the rest of the cluster to recover from interruptions
                        cluster_cooc = sum(self._cooccurrence_matrix.get(next_node, {}).get(other, 0) for other in current_cluster)
                        predictions[next_node] += prob * (1.0 + math.log1p(cluster_cooc))
                        
        if not predictions:
            return ""
            
        return max(predictions.items(), key=lambda x: x[1])[0]

    def _decay_workflows(self, now: float):
        """Removes stale workflows gracefully."""
        to_remove = []
        for wid, wf in self.active_workflows.items():
            age = now - wf.last_updated
            if age > 600: # 10 minutes inactive
                wf.confidence *= math.exp(-age / 300.0)
            if wf.confidence < 0.1:
                to_remove.append(wid)
                
        for wid in to_remove:
            # We could archive this episode in semantic memory here
            del self.active_workflows[wid]

    def get_state_summary(self) -> Dict[str, Any]:
        active = self.infer_current_workflow()
        return {
            "active_workflows_count": len(self.active_workflows),
            "top_workflow": active[0].id if active else None,
            "top_confidence": active[0].confidence if active else 0.0,
            "prediction": active[0].predicted_next_phase if active else ""
        }
