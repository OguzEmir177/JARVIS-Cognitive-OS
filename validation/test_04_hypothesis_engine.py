import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from validation.framework import ValidationFramework
from core.hypothesis_engine import HypothesisEngine, Evidence

def run_hypothesis_validation():
    """
    Validates Hypothesis generation, reinforcement, decay, and refutation.
    """
    engine = HypothesisEngine(event_bus=None) # No event bus for manual test
    metrics = {}
    
    # 1. Generation & Initial Confidence
    ev1 = Evidence(source="vision", weight=0.6, description="User opened code editor")
    hid1 = engine.generate_hypothesis(
        category="intent",
        description="User is starting to code",
        base_prob=0.3,
        initial_evidence=ev1
    )
    
    initial_conf = engine.hypotheses[hid1].confidence
    metrics["initial_confidence"] = initial_conf
    
    # 2. Reinforcement
    ev2 = Evidence(source="system", weight=0.8, description="User typed 'npm start'")
    engine.reinforce(hid1, ev2)
    
    reinforced_conf = engine.hypotheses[hid1].confidence
    metrics["reinforced_confidence"] = reinforced_conf
    
    if reinforced_conf <= initial_conf:
        raise ValueError("Confidence did not increase after strong reinforcement.")
        
    # 3. Decay simulation
    # We will fake the last_reinforced time
    engine.hypotheses[hid1].last_reinforced -= 600 # 10 minutes ago
    decayed_conf = engine.hypotheses[hid1].confidence
    metrics["decayed_confidence"] = decayed_conf
    
    if decayed_conf >= reinforced_conf:
        raise ValueError("Confidence did not decay after simulated time gap.")
        
    # 4. Refutation (Contradiction handling)
    engine.refute(hid1, "User immediately closed the editor and opened Netflix")
    
    refuted_conf = engine.hypotheses[hid1].confidence
    metrics["refuted_confidence"] = refuted_conf
    
    if refuted_conf != 0.0:
        raise ValueError("Confidence did not drop to 0.0 upon refutation.")
        
    # 5. Deduplication validation
    ev3 = Evidence("test", 0.5, "Test")
    hid2 = engine.generate_hypothesis("intent", "User is watching the movie", 0.5, ev3)
    hid3 = engine.generate_hypothesis("intent", "User is watching the movie now", 0.5, ev3) # High Jaccard similarity
    
    if hid2 != hid3:
        raise ValueError("Hypothesis engine failed to deduplicate similar hypotheses.")
        
    metrics["deduplication_successful"] = True
    
    return metrics

if __name__ == "__main__":
    framework = ValidationFramework()
    framework.measure("Hypothesis Engine Validation", run_hypothesis_validation)
    framework.generate_report()
