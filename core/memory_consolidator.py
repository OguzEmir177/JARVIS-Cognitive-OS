import time
import logging
from collections import defaultdict
from core.memory import MemoryManager

logger = logging.getLogger("JARVIS.MemoryConsolidator")

class MemoryConsolidator:
    def __init__(self, memory: MemoryManager):
        self.memory = memory

    def consolidate(self):
        if not self.memory or not self.memory.collection:
            return

        try:
            results = self.memory.collection.get(
                where={"memory_type": "episodic"},
                include=["metadatas", "documents"]
            )
            
            if not results or not results['ids']:
                return

            current_time = time.time()
            seven_days = 7 * 86400
            
            to_delete_ids = []
            grouped_records = defaultdict(lambda: {"success": 0, "failed": 0, "total": 0})
            
            for doc_id, metadata in zip(results['ids'], results['metadatas']):
                importance = float(metadata.get("importance", 0.5))
                timestamp = float(metadata.get("timestamp", current_time))
                
                if (current_time - timestamp) > seven_days and importance < 0.4:
                    to_delete_ids.append(doc_id)
                    tool_used = str(metadata.get("tool_used", "UNKNOWN"))
                    outcome = str(metadata.get("outcome", "unknown"))
                    
                    grouped_records[tool_used]["total"] += 1
                    if outcome.lower() == "success":
                        grouped_records[tool_used]["success"] += 1
                    else:
                        grouped_records[tool_used]["failed"] += 1

            for tool, stats in grouped_records.items():
                if stats["total"] > 0:
                    summary = f"Geçen hafta {tool} {stats['total']} kez kullanıldı, {stats['success']} başarılı {stats['failed']} başarısız."
                    self.memory.save_memory(
                        text=summary,
                        memory_type="semantic",
                        metadata={
                            "importance": 0.6,
                            "timestamp": time.time(),
                            "source": "consolidation"
                        }
                    )

            if to_delete_ids:
                self.memory.collection.delete(ids=to_delete_ids)

        except Exception as e:
            logger.error(f"[CONSOLIDATION ERROR] {e}")

    def prune_duplicates(self):
        if not self.memory or not self.memory.collection:
            return

        try:
            results = self.memory.collection.get(
                where={"memory_type": "episodic"},
                include=["metadatas"]
            )
            
            if not results or not results['ids']:
                return

            from datetime import datetime
            
            grouped = defaultdict(list)
            current_time = time.time()
            
            for doc_id, metadata in zip(results['ids'], results['metadatas']):
                tool_used = str(metadata.get("tool_used", "UNKNOWN"))
                outcome = str(metadata.get("outcome", "unknown"))
                timestamp = float(metadata.get("timestamp", current_time))
                day_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
                
                group_key = f"{tool_used}_{outcome}_{day_str}"
                importance = float(metadata.get("importance", 0.5))
                
                grouped[group_key].append((doc_id, importance))

            to_delete_ids = []
            for key, items in grouped.items():
                if len(items) > 1:
                    items.sort(key=lambda x: x[1], reverse=True)
                    for item in items[1:]:
                        to_delete_ids.append(item[0])

            if to_delete_ids:
                self.memory.collection.delete(ids=to_delete_ids)

        except Exception as e:
            logger.error(f"[PRUNE ERROR] {e}")

    def clean_corrupted_records(self):
        if not self.memory or not self.memory.collection:
            return

        try:
            # where filtresi KALDIRILDI — tüm kayıtları tara (memory_type fark etmez)
            results = self.memory.collection.get(
                include=["metadatas", "documents"]
            )
            
            if not results or not results['ids']:
                return

            to_delete_ids = []
            
            for doc_id, metadata, doc in zip(results['ids'], results['metadatas'], results['documents']):
                if not doc:
                    continue
                    
                doc_lower = doc.lower()
                importance = float(metadata.get("importance", 0.0))
                
                if (
                    "heijan" in doc_lower 
                    or "oluşturulan mesaj" in doc_lower
                    or "[protocol:" in doc_lower
                    or doc_lower.startswith("kullanıcı,")
                    or "whatsapp_dictate" in doc_lower
                    or "app_navigate" in doc_lower
                    or "905059" in doc_lower
                    or "numarasını kullan" in doc_lower
                ):
                    to_delete_ids.append(doc_id)
                    continue
                    
                word_count = len(doc.split())
                if word_count < 15:
                    to_delete_ids.append(doc_id)
                    continue

            if to_delete_ids:
                self.memory.collection.delete(ids=to_delete_ids)
                logger.info(f"[CLEANUP] {len(to_delete_ids)} corrupted record(s) deleted.")

        except Exception as e:
            logger.error(f"[CLEANUP ERROR] {e}")

    def get_stats(self) -> dict:
        stats = {
            "total_records": 0,
            "episodic_count": 0,
            "pattern_rules": 0,
            "oldest_record_days": 0.0
        }
        
        if not self.memory or not self.memory.collection:
            return stats
            
        try:
            stats["total_records"] = self.memory.collection.count()
            
            all_records = self.memory.collection.get(include=["metadatas"])
            if not all_records or not all_records['metadatas']:
                return stats
                
            current_time = time.time()
            oldest_ts = current_time
            
            for metadata in all_records['metadatas']:
                mtype = metadata.get("memory_type", "")
                if mtype == "episodic":
                    stats["episodic_count"] += 1
                elif mtype == "pattern_rule":
                    stats["pattern_rules"] += 1
                    
                ts = float(metadata.get("timestamp", current_time))
                if ts < oldest_ts:
                    oldest_ts = ts
                    
            if oldest_ts < current_time:
                stats["oldest_record_days"] = (current_time - oldest_ts) / 86400.0
                
        except Exception as e:
            logger.error(f"[STATS ERROR] {e}")
            
        return stats
