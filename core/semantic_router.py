"""
[V15.0] Semantic Router (Dynamic Embedding Cache)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Replaces the spaghetti regex/keyword router with a pure TF-IDF cosine similarity local vector model.
Lightning fast, local execution, no LLM latency.
Now features a Dynamic Embedding Cache for autonomous self-learning.
"""
import os
import json
import asyncio
import time
import logging
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    raise SystemError("SemanticRouter requires scikit-learn. Lütfen 'pip install scikit-learn' çalıştırın.")

logger = logging.getLogger("JARVIS.SemanticRouter")

@dataclass
class RouteMatch:
    tool_tag: str
    params: Dict[str, Any]
    confidence: float
    is_forced: bool = False
    reasoning: str = ""

class SemanticRouter:
    """
    [V15.0] Vektör Tabanlı Otonom Yönlendirici (Dynamic Embedding Cache)
    """
    def __init__(self):
        logger.info("SemanticRouter (TF-IDF Vector-based) başlatılıyor...")
        self.vectorizer = TfidfVectorizer(lowercase=True, analyzer='word', ngram_range=(1, 3))
        self.cache_path = os.path.join(os.getcwd(), "memory_db", "dynamic_embeddings.json")
        self.max_custom_commands = 1000
        
        # Niyet Vektörleri
        self.tool_definitions = {
            "APP_OPEN": ["uygulamayı başlat", "programı aç", "çalıştır", "aç", "spotify aç", "youtube aç", "discord aç", "chrome aç", "uygulama aç"],
            "APP_KILL": ["uygulamayı kapat", "sonlandır", "durdur", "programı kapat", "kapat", "çıkış yap"],
            "WEB_SEARCH": ["internette ara", "bilgi bul", "araştır", "google", "ne demek", "nedir", "kimdir", "kaç yaşında"],
            "YT_SEARCH": ["youtube'da ara", "video bul", "youtube ara"],
            "YT_PLAY": ["youtube'da oynat", "video izle", "video aç"],
            "WHATSAPP_MESSAGE": ["whatsapp mesaj gönder", "mesaj at", "mesaja yaz"],
            "SYSTEM_POWER": ["bilgisayarı kapat", "pc kapat", "yeniden başlat", "sistemi kapat", "gücü kes"],
            "CLOSE_LAST_TAB": ["sekmeyi kapat", "son sekmeyi kapat", "sayfayı kapat"],
            "FILE_READ": ["dosya oku", "dosya içeriği", "ne yazıyor", "belgeyi aç"],
            "FOLDER_OPEN": ["klasör aç", "dizini aç", "klasörü aç", "indirilenleri aç", "klasörünü göster"],
        }
        
        self.tags = []
        self.corpus = []
        self.learned_data = {}
        
        # 1. Sabit Tanımları Yükle
        for tag, phrases in self.tool_definitions.items():
            for phrase in phrases:
                self.tags.append(tag)
                self.corpus.append(phrase)
                
        # 2. Otonom Öğrenilenleri Disk'ten Yükle
        self._load_learned_routes()
                
        # Modeli eğit
        self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus)

    def _load_learned_routes(self):
        """Diskteki öğrenilmiş cache dosyasını senkron olarak okur (Fail-Fast)."""
        if not os.path.exists(self.cache_path):
            return
            
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                self.learned_data = json.load(f)
            
            count = 0
            for phrase, data in self.learned_data.items():
                self.tags.append(data["tool_tag"])
                self.corpus.append(phrase)
                count += 1
                
            if count > 0:
                logger.info(f"Otonom Cache: {count} adet dinamik komut vektör uzayına eklendi.")
        except json.JSONDecodeError as e:
            logger.error(f"SemanticRouter Cache (JSON) okuma hatası: Dosya bozuk! Detay: {e}")
            raise SystemError(f"Dynamic Embedding Cache okunamadı (JSON format hatası): {e}")
        except Exception as e:
            logger.error(f"SemanticRouter kritik hata: {e}")
            raise SystemError(f"SemanticRouter initialization failed: {e}")

    async def learn_new_route(self, user_input: str, tool_tag: str, arguments: Any = None):
        """LLM'in çözdüğü başarılı komutu lokal JSON'a asenkron olarak kaydeder."""
        if not user_input or len(user_input.split()) < 2 or len(user_input) > 50:
            return
            
        # Argüman tipi güvenliği
        if not isinstance(arguments, (dict, str, list)):
            arguments = {}

        def _update_and_write():
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            
            if user_input in self.learned_data:
                self.learned_data[user_input]["use_count"] += 1
                self.learned_data[user_input]["last_used"] = time.time()
                self.learned_data[user_input]["tool_tag"] = tool_tag
                self.learned_data[user_input]["arguments"] = arguments
            else:
                self.learned_data[user_input] = {
                    "tool_tag": tool_tag,
                    "arguments": arguments,
                    "use_count": 1,
                    "last_used": time.time()
                }
                
                # Budama (Pruning) Mantığı: Max limit aşılırsa en az kullanılanı sil
                if len(self.learned_data) > self.max_custom_commands:
                    sorted_keys = sorted(
                        self.learned_data.keys(), 
                        key=lambda k: (self.learned_data[k]["use_count"], self.learned_data[k]["last_used"])
                    )
                    least_used_key = sorted_keys[0]
                    del self.learned_data[least_used_key]
                    logger.info(f"Otonom Cache Limiti Aşıldı: '{least_used_key}' budandı (pruned).")
                    
            # Fail-fast disk yazma (hata yutulmaz)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.learned_data, f, ensure_ascii=False, indent=2)
            
            return True

        # I/O İşlemini ThreadPool'a atarak event loop bloklamasını engelle
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, _update_and_write)
        
        if success:
            logger.info(f"Otonom Öğrenme Başarılı: '{user_input}' -> {tool_tag} (Args: {arguments})")
            
            # RAM'deki vektörleri anında senkronize et
            if user_input not in self.corpus:
                self.tags.append(tool_tag)
                self.corpus.append(user_input)
                self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus)

    def route(self, user_input: str, world_context: Dict[str, Any] = None, context: Dict[str, Any] = None) -> Optional[RouteMatch]:
        """Komutu vektör uzayında test eder."""
        if not user_input or len(user_input.strip()) < 2:
            return None
            
        input_vec = self.vectorizer.transform([user_input])
        similarities = cosine_similarity(input_vec, self.tfidf_matrix).flatten()
        
        best_index = int(np.argmax(similarities))
        best_score = float(similarities[best_index])
        
        if best_score < 0.2:
            return None
            
        best_tag = self.tags[best_index]
        matched_phrase = self.corpus[best_index]
        
        if best_score > 0.65:
            # 1. Dinamik Öğrenilmiş Cache Eşleşmesi
            if matched_phrase in self.learned_data:
                cached_args = self.learned_data[matched_phrase].get("arguments", {})
                params = {"query": user_input}
                
                if isinstance(cached_args, dict):
                    params.update(cached_args)
                elif isinstance(cached_args, str):
                    params["learned_arg"] = cached_args
                    params["query"] = cached_args 
                    
                logger.info(f"Router: Dynamic Embedding Match → {best_tag} (Skor: {best_score:.3f})")
                
                # Arka planda kullanım istatistiğini güncelle
                def _update_stats():
                    if matched_phrase in self.learned_data:
                        self.learned_data[matched_phrase]["use_count"] += 1
                        self.learned_data[matched_phrase]["last_used"] = time.time()
                try:
                    asyncio.get_running_loop().run_in_executor(None, _update_stats)
                except Exception:
                    pass
                
                return RouteMatch(
                    tool_tag=best_tag,
                    params=params,
                    confidence=best_score,
                    is_forced=True,
                    reasoning=f"Dynamic Cache Match (Score: {best_score:.3f})"
                )
                
            # 2. Statik Kelime Grubu Eşleşmesi
            query = user_input.lower()
            phrases_to_remove = self.tool_definitions.get(best_tag, [])
            for phrase in phrases_to_remove:
                if phrase in query:
                    query = query.replace(phrase, "").strip()
                    
            if not query:
                query = user_input
                
            logger.info(f"Router: Statik Vektör Eşleşmesi → {best_tag} (Skor: {best_score:.3f})")
            return RouteMatch(
                tool_tag=best_tag, 
                params={"query": query}, 
                confidence=best_score, 
                is_forced=True, 
                reasoning=f"Static Cosine Similarity (Score: {best_score:.3f})"
            )
            
        logger.info(f"Router: Skor yetersiz ({best_score:.3f} < 0.65) → LLM Fallback (GroqBrain devrede)")
        return None

    def get_tool_stats(self) -> Dict[str, Any]:
        return {
            "model": "TF-IDF (scikit-learn)", 
            "vector_count": len(self.corpus), 
            "dynamic_cache_size": len(self.learned_data)
        }

    def record_execution(self, tool_tag: str, success: bool):
        pass

