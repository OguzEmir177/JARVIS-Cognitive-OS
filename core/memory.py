import os
import uuid
import time
import math
import logging
import asyncio
import chromadb
from chromadb.utils import embedding_functions
from typing import Callable, Optional

logger = logging.getLogger("JARVIS.MemoryManager")

class MemoryManager:
    """J.A.R.V.I.S. v2 Smart Memory Manager [10/10 Upgrade]

    ChromaDB based semantic memory.
    + get_display_memories() → Configured list for GUI MEMORY tab
    + _on_save_callback → "I learned" notification to GUI at save time"""

    def __init__(self, db_path: str = "./memory_db", max_memory_limit: int = 10000):
        db_path_str = str(db_path)
        if db_path_str == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = os.path.abspath(db_path_str)

        self.max_memory_limit = max_memory_limit
        self.client = None
        self.collection = None
        self.embedding_func = None
        self.logger = logger

        # [10/10] Callback for registration notification
        self._on_save_callback: Optional[Callable[[str, str, float], None]] = None

    # ─────────────────────────────────────────────────────────────────────────
    # CALLBACK
    # ─────────────────────────────────────────────────────────────────────────

    def set_on_save_callback(self, callback: Callable[[str, str, float], None]) -> None:
        """The function to be called when a new memory is saved.
        callback(text: str, memory_type: str, importance: float)"""
        self._on_save_callback = callback

    # ─────────────────────────────────────────────────────────────────────────
    # INITIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def setup_memory(self):
        try:
            if self.db_path != ":memory:" and not os.path.exists(self.db_path):
                os.makedirs(self.db_path, exist_ok=True)

            self.logger.info(f"[MEMORY] Starting: {self.db_path}")

            self.client = chromadb.PersistentClient(path=self.db_path)

            self.embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="paraphrase-multilingual-MiniLM-L12-v2"
            )

            self.collection = self.client.get_or_create_collection(
                name="jarvis_global_memory",
                embedding_function=self.embedding_func,
                metadata={"hnsw:space": "cosine"}
            )
            self.logger.info("[MEMORY] Smart Memory Manager has been started successfully.")

        except Exception as e:
            self.logger.error(f"[MEMORY INIT ERROR] Critical error: {e}")
            self.collection = None

    def migrate_legacy_memory(self, file_path: str):
        safe_path = os.path.abspath(file_path)
        if not os.path.exists(safe_path) or self.collection is None:
            return
        if self.collection.count() > 0:
            return

        self.logger.info(f"[MIGRATION] Migrating data via {safe_path}...")
        try:
            with open(safe_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("-") and ":" in line:
                    parts = line.replace("-", "", 1).split(":")
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        number = parts[1].strip()
                        content = f"Contacts Entry: Phone number of {name} {number}"
                        self.save_memory(content, "semantic", {"importance": 0.9, "source": "legacy_md",
                                                               "contact_name": name, "phone": number})
                elif ":" in line and not line.startswith("#"):
                    self.save_memory(line, "semantic", {"importance": 1.0, "source": "legacy_md"})

            self.logger.info("[MIGRATION] Completed successfully.")
            os.rename(safe_path, safe_path + ".bak")

        except Exception as e:
            self.logger.error(f"[MIGRATION ERROR]: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # KAYIT
    # ─────────────────────────────────────────────────────────────────────────

    def _preprocess_query(self, text: str) -> str:
        return str(text).lower().strip()

    def save_memory(self, text: str, memory_type: str, metadata: dict = None) -> str:
        if self.collection is None:
            return None

        allowed_types = ["episodic", "semantic", "task", "pattern_rule"]
        if memory_type not in allowed_types:
            raise ValueError(f"Invalid memory_type: '{memory_type}'")

        clean_text = self._preprocess_query(text)

        try:
            if self.collection.count() > 0:
                dup_search = self.collection.query(query_texts=[clean_text], n_results=1)
                if dup_search['distances'] and len(dup_search['distances'][0]) > 0:
                    if dup_search['distances'][0][0] <= 0.15:
                        return dup_search['ids'][0][0]
        except Exception as e:
            self.logger.warning(f"[MEMORY DUPLICATE CHECK ERROR]: {e}")

        if metadata is None:
            metadata = {}
        metadata["memory_type"] = memory_type
        metadata["importance"] = float(metadata.get("importance", 0.5))
        metadata["timestamp"] = metadata.get("timestamp", time.time())

        doc_id = str(uuid.uuid4())

        try:
            self.collection.add(
                documents=[clean_text],
                metadatas=[metadata],
                ids=[doc_id]
            )
            self._enforce_limit()

            # [10/10] Registration notification
            if self._on_save_callback:
                try:
                    self._on_save_callback(text, memory_type, metadata["importance"])
                except Exception:
                    pass

            return doc_id

        except Exception as e:
            self.logger.error(f"[MEMORY SAVE ERROR] Failed to write data: {e}")
            return None

    async def save_memory_async(self, text: str, memory_type: str, metadata: dict = None) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.save_memory, text, memory_type, metadata)

    # ─────────────────────────────────────────────────────────────────────────
    # SORGU
    # ─────────────────────────────────────────────────────────────────────────

    async def retrieve_memory_async(self, query: str, memory_type: str = None,
                                    top_k: int = 5, similarity_threshold: float = 0.4) -> list:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.retrieve_memory(query, memory_type, top_k, similarity_threshold)
        )

    def retrieve_memory(self, query: str, memory_type: str = None,
                        top_k: int = 5, similarity_threshold: float = 0.4) -> list:
        if self.collection is None or self.collection.count() == 0:
            return []

        clean_query = self._preprocess_query(query)
        where_clause = {"memory_type": memory_type} if memory_type else None

        try:
            results = self.collection.query(
                query_texts=[clean_query],
                n_results=min(top_k * 3, self.collection.count()),
                where=where_clause
            )

            memories = []
            current_time = time.time()

            if results['documents'] and len(results['documents'][0]) > 0:
                for i in range(len(results['documents'][0])):
                    distance = results['distances'][0][i]
                    metadata = results['metadatas'][0][i]
                    text = results['documents'][0][i]
                    doc_id = results['ids'][0][i]

                    relevance_score = max(0.0, 1.0 - distance)
                    if relevance_score < similarity_threshold:
                        continue

                    importance = float(metadata.get("importance", 0.5))
                    mem_time = metadata.get("timestamp", current_time)
                    age_in_days = max(0.0, (current_time - mem_time) / 86400.0)
                    recency_score = math.exp(-age_in_days / 30.0)

                    final_score = (relevance_score * 0.6) + (importance * 0.3) + (recency_score * 0.1)

                    memories.append({
                        "id": doc_id, "text": text, "metadata": metadata,
                        "relevance_score": round(relevance_score, 4),
                        "importance_score": round(importance, 4),
                        "recency_score": round(recency_score, 4),
                        "final_score": round(final_score, 4)
                    })

            memories = sorted(memories, key=lambda x: x["final_score"], reverse=True)
            return memories[:top_k]

        except Exception as e:
            self.logger.error(f"[MEMORY RETRIEVE ERROR] Query error: {e}")
            return []

    def retrieve_context(self, query: str, n: int = 3, distance_threshold: float = 0.35) -> str:
        if not hasattr(self, 'collection') or self.collection is None:
            return ""
        try:
            count = self.collection.count()
            if count == 0:
                return ""
            results = self.collection.query(
                query_texts=[query],
                n_results=min(n, count),
                include=["documents", "distances"]
            )
            docs = results.get("documents", [[]])[0]
            dists = results.get("distances", [[]])[0]
            relevant = [doc for doc, dist in zip(docs, dists) if dist < distance_threshold]
            return "\n".join(relevant) if relevant else ""
        except Exception as e:
            logger.warning(f"[MEMORY] retrieve_context error: {e}")
            return ""

    def get_recent_memories(self, n: int = 10) -> str:
        if not hasattr(self, 'collection') or self.collection is None:
            return ""
        try:
            count = self.collection.count()
            if count == 0:
                return ""
            all_data = self.collection.get(include=["documents", "metadatas"])
            sorted_items = sorted(
                zip(all_data['documents'], all_data['metadatas']),
                key=lambda x: x[1].get('timestamp', 0),
                reverse=True
            )
            recent_docs = [item[0] for item in sorted_items[:min(n, count)]]
            return "\n".join(recent_docs)
        except Exception as e:
            logger.warning(f"[MEMORY] get_recent_memories error: {e}")
            return ""

    # ─────────────────────────────────────────────────────────────────────────
    # [10/10] MEMORY LIST FOR GUI
    # ─────────────────────────────────────────────────────────────────────────

    def get_display_memories(self, n: int = 50) -> list:
        """Returns a list of configured memory for the GUI MEMORY tab.
        Each item:
          {
            "text": str,
            "memory_type": str,       # episodic | semantic | task | pattern_rule
            "importance": float,      # 0.0 – 1.0
            "timestamp": float,       # unix epoch
            "age_label": str,         # "2 saat önce" / "3 gün önce" vb.
          }
        Newest records come first."""
        if not hasattr(self, 'collection') or self.collection is None:
            return []
        try:
            count = self.collection.count()
            if count == 0:
                return []

            all_data = self.collection.get(include=["documents", "metadatas"])
            items = list(zip(all_data['documents'], all_data['metadatas']))
            items.sort(key=lambda x: x[1].get('timestamp', 0), reverse=True)
            items = items[:n]

            now = time.time()
            result = []
            for doc, meta in items:
                ts = meta.get('timestamp', now)
                age_sec = now - ts
                if age_sec < 3600:
                    age_label = f"{int(age_sec // 60)} minutes ago"
                elif age_sec < 86400:
                    age_label = f"{int(age_sec // 3600)} hours ago"
                else:
                    age_label = f"{int(age_sec // 86400)} days ago"

                result.append({
                    "text": doc,
                    "memory_type": meta.get("memory_type", "semantic"),
                    "importance": float(meta.get("importance", 0.5)),
                    "timestamp": ts,
                    "age_label": age_label,
                })
            return result

        except Exception as e:
            logger.warning(f"[MEMORY] get_display_memories error: {e}")
            return []

    def get_stats(self) -> dict:
        """[10/10] Summary statistics for GUI.
        Returns: {"total": int, "by_type": {type: count}, "avg_importance": float}"""
        if not hasattr(self, 'collection') or self.collection is None:
            return {"total": 0, "by_type": {}, "avg_importance": 0.0}
        try:
            count = self.collection.count()
            if count == 0:
                return {"total": 0, "by_type": {}, "avg_importance": 0.0}

            all_data = self.collection.get(include=["metadatas"])
            by_type = {}
            total_imp = 0.0
            for meta in all_data['metadatas']:
                mt = meta.get("memory_type", "semantic")
                by_type[mt] = by_type.get(mt, 0) + 1
                total_imp += float(meta.get("importance", 0.5))

            return {
                "total": count,
                "by_type": by_type,
                "avg_importance": round(total_imp / count, 3) if count else 0.0
            }
        except Exception as e:
            logger.warning(f"[MEMORY] get_stats error: {e}")
            return {"total": 0, "by_type": {}, "avg_importance": 0.0}

    # ─────────────────────────────────────────────────────────────────────────
    # BAKIM
    # ─────────────────────────────────────────────────────────────────────────

    def _enforce_limit(self):
        try:
            current_count = self.collection.count()
            if current_count <= self.max_memory_limit:
                return
            delete_count = int(self.max_memory_limit * 0.1)
            all_data = self.collection.get(include=["metadatas"])
            sorted_items = sorted(
                zip(all_data['ids'], all_data['metadatas']),
                key=lambda x: x[1].get('timestamp', 0)
            )
            ids_to_delete = [item[0] for item in sorted_items[:delete_count]]
            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
        except Exception as e:
            self.logger.error(f"[MEMORY PRUNING ERROR]: {e}")

    def clear_memory(self):
        if self.collection is None:
            return False
        try:
            self.client.delete_collection(name="jarvis_global_memory")
            self.collection = self.client.get_or_create_collection(
                name="jarvis_global_memory",
                embedding_function=self.embedding_func,
                metadata={"hnsw:space": "cosine"}
            )
            return True
        except Exception as e:
            self.logger.error(f"[MEMORY CLEAR ERROR]: {e}")
            return False