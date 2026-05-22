"""
[V14.0] Semantic Router (Vector-based)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Replaces the spaghetti regex/keyword router with a pure TF-IDF cosine similarity local vector model.
Lightning fast, local execution, no LLM latency.
"""
import logging
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    raise ImportError("SemanticRouter requires scikit-learn. Lütfen 'pip install scikit-learn' çalıştırın.")

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
    [V14.0] Vektör Tabanlı Yönlendirici (Fail-Fast)
    """
    def __init__(self):
        logger.info("SemanticRouter (TF-IDF Vector-based) başlatılıyor...")
        # (1,3) ngram kullanarak kelime öbeklerini de yakala
        self.vectorizer = TfidfVectorizer(lowercase=True, analyzer='word', ngram_range=(1, 3))
        
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
        
        for tag, phrases in self.tool_definitions.items():
            for phrase in phrases:
                self.tags.append(tag)
                self.corpus.append(phrase)
                
        # Modeli eğit
        self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus)

    def route(self, user_input: str, world_context: Dict[str, Any] = None, context: Dict[str, Any] = None) -> Optional[RouteMatch]:
        """Komutu vektör uzayında test eder."""
        if not user_input or len(user_input.strip()) < 2:
            return None
            
        input_vec = self.vectorizer.transform([user_input])
        similarities = cosine_similarity(input_vec, self.tfidf_matrix).flatten()
        
        best_index = int(np.argmax(similarities))
        best_score = float(similarities[best_index])
        
        # Tamamen alakasız
        if best_score < 0.2:
            return None
            
        best_tag = self.tags[best_index]
        
        # Güvenlik Eşiği
        if best_score > 0.65:
            # Query'i temizle
            query = user_input.lower()
            for phrase in self.tool_definitions[best_tag]:
                if phrase in query:
                    query = query.replace(phrase, "").strip()
                    
            if not query:
                query = user_input
                
            logger.info(f"Router: Vektörel Eşleşme Başarılı → {best_tag} (Skor: {best_score:.3f})")
            return RouteMatch(
                tool_tag=best_tag, 
                params={"query": query}, 
                confidence=best_score, 
                is_forced=True, 
                reasoning=f"Cosine Similarity (Score: {best_score:.3f})"
            )
            
        logger.info(f"Router: Skor yetersiz ({best_score:.3f} < 0.65) → LLM Fallback (GroqBrain devrede)")
        return None

    def get_tool_stats(self) -> Dict[str, Any]:
        return {"model": "TF-IDF (scikit-learn)", "vector_count": len(self.corpus)}

    def record_execution(self, tool_tag: str, success: bool):
        # Statik vektör router profilleme yapmaz.
        pass
