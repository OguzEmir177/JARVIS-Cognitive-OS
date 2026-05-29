import logging
import re
from typing import Optional

logger = logging.getLogger("JARVIS.PatternExtractor")

class PatternExtractor:
    """By extracting patterns from the user's unsuccessful attempts
    Learning module that prevents the system from making the same mistakes in the future."""
    
    def __init__(self, memory):
        self.memory = memory

    def extract_patterns(self) -> None:
        """Reads episodic records with 'failure' outcome in ChromaDB.
        If there are 2+ unsuccessful attempts with the same tool, it generates a 'rule'."""
        if not self.memory or not getattr(self.memory, 'collection', None):
            return

        try:
            # get all memory that is "episodic"
            results = self.memory.collection.get(
                where={"memory_type": "episodic"}
            )
            
            if not results or not results.get("documents"):
                return
                
            docs = results["documents"]
            metadatas = results["metadatas"]
            
            # Group failed operations (by tool and estimated target)
            failures_by_tool = {}
            
            for doc, meta in zip(docs, metadatas):
                if meta.get("outcome") == "failure":
                    tool = meta.get("tool_used", "UNKNOWN")
                    
                    # Let's try to catch a word like "APP_OPEN discord" in the doc
                    # "Task: APP_OPEN discord. Result: failure."
                    match = re.search(f"{tool}\\s+([^\\.]+)", doc, re.IGNORECASE)
                    if match:
                        target = match.group(1).strip()
                    else:
                        target = "unknown_target"
                        
                    key = (tool, target.lower())
                    if key not in failures_by_tool:
                        failures_by_tool[key] = []
                    failures_by_tool[key].append(doc)
            
            for (tool, target), fail_docs in failures_by_tool.items():
                if len(fail_docs) >= 2:
                    # An example rule with a logical alternative when the goal cannot be achieved
                    if tool == "APP_OPEN":
                        rule_text = f"Opening '{target}' with {tool} failed {len(fail_docs)} times. Alternative: WEB_OPEN {target}.com"
                    else:
                        rule_text = f"Operation {tool} failed {len(fail_docs)} times for '{target}'. Try alternative routes."

                    # Check if the rule is in memory
                    existing_rules = self.memory.collection.get(
                        where={"memory_type": "pattern_rule"}
                    )
                    already_exists = False
                    if existing_rules and existing_rules.get("documents"):
                        for edoc in existing_rules["documents"]:
                            if rule_text in edoc:
                                already_exists = True
                                break
                    
                    if not already_exists:
                        self.save_pattern(rule_text)

        except Exception as e:
            logger.error(f"[PatternExtractor] Error running extract_patterns: {e}")

    def save_pattern(self, rule_text: str) -> None:
        """It saves the generated rule in memory as pattern_rule."""
        metadata = {
            "memory_type": "pattern_rule",
            "importance": 0.95,
            "auto_generated": True
        }
        # Check if memory.py's save_memory() method checks allow types
        # memory.py'yi inceledik: -> allowed_types = ["episodic", "semantic", "task"]
        # Wait! "pattern_rule" is not listed!
        # Might need to add "pattern_rule" to allowed_types in memory.py!
        # But constraint: "MemoryManager.save_memory() signature MUST NOT CHANGE". Its operation may change.
        
        self.memory.save_memory(rule_text, "pattern_rule", metadata)
        logger.info(f"[PatternExtractor] New Rule Learned and Saved: {rule_text}")

    def get_active_patterns(self) -> str:
        """Active learned rules are returned as string."""
        if not self.memory or not getattr(self.memory, 'collection', None):
            return ""
            
        try:
            results = self.memory.collection.get(
                where={"memory_type": "pattern_rule"}
            )
            
            if results and results.get("documents"):
                return "\n".join(results["documents"])
                
        except Exception as e:
            logger.warning(f"[PatternExtractor] Error pulling get_active_patterns: {e}")
            
        return ""
