"""
[V8.0] J.A.R.V.I.S. Centralized Configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tüm timeout, retry, limit değerleri tek noktada.

Tasarım Kararı:
    Neden dataclass ve .env değil?
    → Basitlik. Değerler runtime'da değişmez, hardcoded defaults yeter.
    → İleride .env'den yükleme eklenebilir (genişletilebilirlik).
    → Groq free tier limitleri sabit (30 req/min).
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# [V8.0] Çevre değişkenlerini uygulama başlamadan yükle
load_dotenv()


def load_config() -> dict:
    """Çevre değişkenlerini ve temel ayarları yükler (legacy uyumluluk)."""
    load_dotenv()
    return {
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
        "ASSISTANT_NAME": "J.A.R.V.I.S.",
        "MASTER_NAME": "Oğuz Emir",
    }


@dataclass
class EngineConfig:
    """
    ExecutionEngine yapılandırması.

    Tüm değerler Groq free tier sınırlarına göre ayarlıdır:
        - 30 requests/minute
        - 6000 tokens/minute
        - 14,400 requests/day

    Attributes:
        max_queue_size:         Aynı anda bekleyebilecek maks görev sayısı
        tool_timeout_seconds:   Tek bir tool çalıştırma timeout'u
        max_replan_attempts:    Başarısız adımda kaç kez replan denenecek
        brain_connect_retries:  Brain bağlantısı kaç kez denenecek
        brain_timeout_seconds:  Tek bir LLM çağrısı timeout'u
        brain_models:           Fallback model sırası (Groq model ID'leri)
        reflection_cooldown_s:  İki reflection arası minimum süre
        max_task_retries:       Tek bir görevin kaç kez retry edilebileceği
    """

    # ── Queue & Concurrency ──
    max_queue_size: int = 50

    # ── Timeout'lar ──
    tool_timeout_seconds: float = 30.0
    brain_timeout_seconds: float = 10.0

    # ── Retry Limitleri ──
    max_replan_attempts: int = 2
    brain_connect_retries: int = 5
    max_task_retries: int = 2

    # ── LLM Model Fallback Chain ──
    brain_models: list = field(default_factory=lambda: [
        "llama-3.3-70b-versatile", # En gelişmiş model (Llama 3.3)
        "llama-3.1-70b-versatile", # Güçlü yedek
        "llama-3.1-8b-instant"     # Hızlı fallback
    ])
    ping_model: str = None         # Fallback test modeli (None ise brain_models[0] kullanılır)
    function_calling_enabled: bool = False  # [V9.7] Devre dışı bırakıldı: LLM'in [PLAN] metnini doğrudan üretmesini zorunlu kılar.

    # ── Reflection ──
    reflection_cooldown_s: float = 5.0

    # ── Storage & Paths ──
    memory_db_path: str = "./memory_db"
    log_dir: str = "./logs"
    log_level: str = "INFO"
