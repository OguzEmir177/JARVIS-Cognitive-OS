"""
[V12.0] J.A.R.V.I.S. — Cognitive OS Entry Point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Eski 958 satırlık God class (JarvisEngine) kaldırıldı.
Tüm logic core/engine.py ExecutionEngine'e taşındı.

Bu dosya sadece:
    1. TTS/STT modüllerini başlatır
    2. ExecutionEngine'e enjekte eder
    3. asyncio.run() ile engine'i başlatır
    4. GUI callback hook'u sağlar

Eski main.py yedek: main_v7_backup.py olarak saklanabilir.
"""

import asyncio
import os
import sys
import logging
import warnings

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")

# HuggingFace ve SentenceTransformers loglarını sustur
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)

# [V12.1] Progress Bar (tqdm) ve stderr'e akan saf metinleri tamamen susturur
os.environ["TQDM_DISABLE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"

import sys
class StderrFilter(object):
    def __init__(self, stream):
        self.stream = stream
    def write(self, data):
        # Yükleme ekranı yazılarını yoksay
        if any(x in data for x in ["Loading weights", "BertModel LOAD REPORT", "embeddings.position_ids", "UNEXPECTED", "HF_TOKEN", "unauthenticated requests", "huggingface.co"]):
            return
        self.stream.write(data)
    def flush(self):
        self.stream.flush()

sys.stderr = StderrFilter(sys.stderr)

from core.engine import ExecutionEngine
from core.config import EngineConfig


async def main():
    """
    J.A.R.V.I.S. v8.0 ana giriş noktası.

    Lifecycle:
        1. TTS/STT modüllerini başlat
        2. ExecutionEngine oluştur
        3. I/O arayüzlerini enjekte et
        4. Engine'i başlat (sonsuz döngü)
    """
    config = EngineConfig()
    engine = ExecutionEngine(config)

    # ── TTS enjeksiyonu ──
    try:
        from audio.tts import TextToSpeech
        tts = TextToSpeech()
        engine.set_tts(tts.speak)
        print("[INIT] TTS modülü: Çevrimiçi")
    except Exception as e:
        print(f"[INIT] TTS modülü yüklenemedi: {e}")

    # ── STT enjeksiyonu ──
    try:
        from audio.stt import SpeechToText
        stt = SpeechToText()
        engine.set_stt(stt.listen)
        print("[INIT] STT modülü: Çevrimiçi")
    except Exception as e:
        print(f"[INIT] STT modülü yüklenemedi (stdin fallback): {e}")

    # ── Alt sistemleri başlat ──
    await engine.initialize()

    # ── Ana döngüye gir ──
    await engine.start()


def launch_with_gui():
    """
    GUI modunda başlatma — gui/interface.py tarafından çağrılır.
    Engine'e GUI callback'lerini enjekte eder.

    Kullanım (gui/interface.py içinden):
        from main import launch_with_gui
        launch_with_gui()
    """
    async def _gui_main():
        config = EngineConfig()
        engine = ExecutionEngine(config)

        # TTS
        try:
            from audio.tts import TextToSpeech
            tts = TextToSpeech()
            engine.set_tts(tts.speak)
        except Exception:
            pass

        # STT
        try:
            from audio.stt import SpeechToText
            stt = SpeechToText()
            engine.set_stt(stt.listen)
        except Exception:
            pass

        await engine.initialize()
        await engine.start()

    asyncio.run(_gui_main())


if __name__ == "__main__":
    print("=" * 50)
    print("  J.A.R.V.I.S. v12.0 — Autonomous Cognitive OS")
    print("=" * 50)
    asyncio.run(main())
