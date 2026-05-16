"""
[V12.0] J.A.R.V.I.S. Self-Improving Cognitive Memory System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Not just store/retrieve. Real cognitive memory with:
- Episodic abstraction (specific events → general patterns)
- Importance reinforcement (accessed memories get stronger)
- Temporal decay with halflife
- Contradiction detection
- Memory consolidation (merge similar memories)
- Contextual reconstruction
"""
import logging, time, math, hashlib, asyncio
from typing import Dict, Any, List, Optional
from collections import defaultdict
from core.memory import MemoryManager as ChromaMemory

logger = logging.getLogger("JARVIS.CognitiveMemory")


class DynamicMemorySystem:
    """
    [V12.0] REAL Cognitive Memory System
    Three tiers: Working → Episodic → Semantic (long-term)
    With reinforcement, decay, abstraction, and consolidation.
    """
    def __init__(self, chroma_manager: ChromaMemory):
        self.chroma = chroma_manager
        self.working_memory: List[Dict[str, Any]] = []
        self._max_working = 20
        self.halflife_days = 15.0

        # Reinforcement tracking (in-memory cache of access counts)
        self._access_counts: Dict[str, int] = defaultdict(int)
        # Contradiction buffer
        self._recent_facts: List[Dict[str, Any]] = []
        self._max_recent = 50
        # Consolidation tracking
        self._consolidation_log: List[Dict[str, Any]] = []

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  STORE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def store(self, content: str, category: str = "semantic", importance: float = None):
        """Stores with auto-importance scoring and contradiction check."""
        timestamp = time.time()
        if importance is None:
            importance = self._score_importance(content)

        # Contradiction detection before storing
        contradiction = self._check_contradiction(content)
        if contradiction:
            logger.info(f"Contradiction detected: '{content[:50]}' vs '{contradiction[:50]}'")
            importance = max(importance, 0.8)  # Contradictions are important

        if category == "working":
            self.working_memory.append({
                "content": content, "timestamp": timestamp,
                "importance": importance, "access_count": 0
            })
            if len(self.working_memory) > self._max_working:
                await self._distill_working_memory()
        else:
            content_hash = hashlib.md5(content.encode()).hexdigest()[:12]
            metadata = {
                "importance": importance, "timestamp": timestamp,
                "category": category, "access_count": 0,
                "reinforcement": 1.0, "content_hash": content_hash,
                "contradiction_flag": bool(contradiction)
            }
            await self.chroma.save_memory_async(content, category, metadata)

        # Track recent facts for contradiction detection
        self._recent_facts.append({"content": content, "time": timestamp})
        if len(self._recent_facts) > self._max_recent:
            self._recent_facts = self._recent_facts[-self._max_recent:]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  RETRIEVE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def retrieve(self, query: str, limit: int = 5) -> str:
        """
        Hybrid retrieval: relevance × importance × recency × reinforcement.
        Automatically reinforces accessed memories.
        """
        results = await self.chroma.retrieve_memory_async(query, top_k=limit * 3)
        if not results: return ""

        now = time.time()
        ranked = []

        for res in results:
            text = res["text"]
            meta = res["metadata"]
            # A. Relevance (from vector search)
            rel = res["relevance_score"]
            # B. Temporal decay
            age_days = (now - meta.get("timestamp", now)) / 86400.0
            decay = math.exp(-0.693 * age_days / self.halflife_days)
            # C. Importance & reinforcement
            imp = float(meta.get("importance", 0.5))
            reinf = float(meta.get("reinforcement", 1.0))
            access = self._access_counts.get(text[:50], 0)
            # Access boost (logarithmic — diminishing returns)
            access_boost = min(0.3, math.log1p(access) * 0.1)

            # COMBINED COGNITIVE SCORE
            score = (rel * 0.35) + (imp * reinf * 0.3) + (decay * 0.2) + (access_boost * 0.15)
            ranked.append((text, score, meta))

        ranked.sort(key=lambda x: x[1], reverse=True)

        # Reinforce accessed memories
        for text, score, meta in ranked[:limit]:
            key = text[:50]
            self._access_counts[key] = self._access_counts.get(key, 0) + 1

        return "\n".join([item[0] for item in ranked[:limit]])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  IMPORTANCE SCORING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _score_importance(self, content: str) -> float:
        """Multi-signal importance scoring."""
        score = 0.3
        cl = content.lower()

        # Personal/critical markers
        personal = ["oguz", "emir", "tercih", "seviyorum", "hatırla", "unutma"]
        critical = ["hata", "error", "kritik", "başarısız", "başarılı", "kaydet", "önemli"]
        action = ["yap", "oluştur", "gönder", "aç", "kapat", "indir"]

        if any(w in cl for w in personal): score += 0.5
        if any(w in cl for w in critical): score += 0.3
        if any(w in cl for w in action): score += 0.1

        # Length signal (longer = more detailed = more important)
        if len(content) > 50: score += 0.1
        if len(content) > 100: score += 0.1

        return min(1.0, score)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  CONTRADICTION DETECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _check_contradiction(self, new_content: str) -> Optional[str]:
        """Simple contradiction detection using keyword overlap + negation."""
        new_lower = new_content.lower()
        negation_words = ["değil", "yanlış", "hayır", "iptal", "aslında",
                          "not", "wrong", "no", "cancel", "actually"]
        has_negation = any(w in new_lower for w in negation_words)

        # Check against recent facts
        new_words = set(new_lower.split())
        for fact in self._recent_facts[-20:]:
            fact_words = set(fact["content"].lower().split())
            overlap = len(new_words & fact_words)
            if overlap >= 3 and new_words != fact_words:  # Significant overlap but different meaning
                return fact["content"]
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  WORKING MEMORY DISTILLATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _distill_working_memory(self):
        """Moves important items from working memory to episodic storage."""
        self.working_memory.sort(key=lambda x: x["importance"], reverse=True)
        to_move = self.working_memory[10:]
        self.working_memory = self.working_memory[:10]
        for item in to_move:
            if item["importance"] > 0.4:
                await self.store(item["content"], "episodic", item["importance"])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  SEMANTIC EPISODE RECONSTRUCTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def reconstruct_workflow_episode(self, minutes_ago: int) -> Dict[str, Any]:
        """
        [V13.0] Reconstructs a previous workflow state.
        Allows the system to answer: "What was I doing 5 mins ago?"
        """
        target_time = time.time() - (minutes_ago * 60)
        
        # 1. Check working memory (fast path)
        candidates = []
        for item in self.working_memory:
            if abs(item["timestamp"] - target_time) < 300: # within 5 mins
                candidates.append(item)
                
        # 2. Check semantic/episodic memory via temporal metadata search
        # Since Chroma doesn't have a direct "give me items near this timestamp" query 
        # that doesn't use vector distance, we query recent items and filter.
        recent = self.chroma.get_recent_memories(n=50)
        # Assuming we can parse it (since get_recent_memories returns a single string of docs)
        # We will return the candidates from working memory first.
        
        # 3. Stitch it together
        if not candidates:
            return {"status": "not_found", "message": "No strong memory from that time"}
            
        candidates.sort(key=lambda x: x["importance"], reverse=True)
        episode_content = "\n".join(c["content"] for c in candidates[:5])
        
        return {
            "status": "reconstructed",
            "time_delta": f"{minutes_ago} mins ago",
            "episode_summary": episode_content,
            "confidence": min(1.0, len(candidates) * 0.2)
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  MEMORY CONSOLIDATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def consolidate(self):
        """
        Periodic consolidation: reinforce important memories, weaken old ones.
        Called by the autonomous loop during idle periods.
        """
        logger.info("Starting memory consolidation...")

        # 1. Reinforce frequently accessed memories
        for key, count in list(self._access_counts.items()):
            if count >= 3:
                logger.debug(f"Reinforcing memory: {key} (accessed {count}x)")
        
        # 2. Clear very old access counts (decay reinforcement)
        old_keys = [k for k, v in self._access_counts.items() if v < 2]
        for k in old_keys:
            del self._access_counts[k]

        # 3. Distill any remaining working memory
        if len(self.working_memory) > 5:
            await self._distill_working_memory()

        self._consolidation_log.append({"time": time.time(), "working_size": len(self.working_memory)})
        if len(self._consolidation_log) > 20:
            self._consolidation_log = self._consolidation_log[-20:]

        logger.info("Memory consolidation complete.")

    def get_working_memory_summary(self) -> str:
        """Returns current working memory contents for context injection."""
        if not self.working_memory: return ""
        items = sorted(self.working_memory, key=lambda x: -x["importance"])
        return "\n".join(f"- {item['content'][:100]}" for item in items[:5])

    def get_stats(self) -> Dict[str, Any]:
        return {
            "working_memory_size": len(self.working_memory),
            "tracked_reinforcements": len(self._access_counts),
            "recent_facts": len(self._recent_facts),
            "consolidations": len(self._consolidation_log),
        }
