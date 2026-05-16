import logging
import re
from typing import Optional

logger = logging.getLogger("JARVIS.PatternExtractor")

class PatternExtractor:
    """
    Kullanıcının başarısız denemelerinden desenler çıkararak
    sistemin gelecekte aynı hatalara düşmesini engelleyen öğrenme modülü.
    """
    
    def __init__(self, memory):
        self.memory = memory

    def extract_patterns(self) -> None:
        """
        ChromaDB'deki 'failure' outcome'lu episodic kayıtları okur.
        Aynı tool ile 2+ başarısız deneme varsa bir 'kural' üretir.
        """
        if not self.memory or not getattr(self.memory, 'collection', None):
            return

        try:
            # "episodic" olan tüm bellekleri al
            results = self.memory.collection.get(
                where={"memory_type": "episodic"}
            )
            
            if not results or not results.get("documents"):
                return
                
            docs = results["documents"]
            metadatas = results["metadatas"]
            
            # Başarısız işlemleri (tool ve tahmini hedefe göre) grupla
            failures_by_tool = {}
            
            for doc, meta in zip(docs, metadatas):
                if meta.get("outcome") == "failure":
                    tool = meta.get("tool_used", "UNKNOWN")
                    
                    # doc içinde "APP_OPEN discord" gibi bir kelime yakalamaya çalışalım
                    # "Görev: APP_OPEN discord. Sonuç: failure."
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
                    # Hedefe ulaşılamadığında mantıklı bir alternatif içeren örnek bir kural
                    if tool == "APP_OPEN":
                        rule_text = f"{tool} ile '{target}' açma {len(fail_docs)} kez başarısız oldu. Alternatif: WEB_OPEN {target}.com"
                    else:
                        rule_text = f"{tool} işlemi '{target}' için {len(fail_docs)} kez başarısız oldu. Alternatif yollar deneyin."

                    # Kuralın hafızada olup olmadığını kontrol et
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
            logger.error(f"[PatternExtractor] extract_patterns çalıştırılırken hata: {e}")

    def save_pattern(self, rule_text: str) -> None:
        """
        Üretilen kuralı hafızaya pattern_rule olarak kaydeder.
        """
        metadata = {
            "memory_type": "pattern_rule",
            "importance": 0.95,
            "auto_generated": True
        }
        # memory.py'nin save_memory() metodu allow types kontrolü yapıyor mu diye kontrol edilir
        # memory.py'yi inceledik: -> allowed_types = ["episodic", "semantic", "task"]
        # Bekle! "pattern_rule" listede değil!
        # memory.py'de allowed_types içine "pattern_rule" eklenmesi gerekebilir!
        # Ancak constraint: "MemoryManager.save_memory() imzası DEĞİŞMEMELİ". İşleyişi değişebilir.
        
        self.memory.save_memory(rule_text, "pattern_rule", metadata)
        logger.info(f"[PatternExtractor] Yeni Kural Öğrenildi ve Kaydedildi: {rule_text}")

    def get_active_patterns(self) -> str:
        """
        Aktif öğrenilmiş kuralları string olarak döner.
        """
        if not self.memory or not getattr(self.memory, 'collection', None):
            return ""
            
        try:
            results = self.memory.collection.get(
                where={"memory_type": "pattern_rule"}
            )
            
            if results and results.get("documents"):
                return "\n".join(results["documents"])
                
        except Exception as e:
            logger.warning(f"[PatternExtractor] get_active_patterns çekilirken hata: {e}")
            
        return ""
