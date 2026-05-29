"""[V12.0] J.A.R.V.I.S. — Cognitive OS Entry Point
━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━
The old 958 line God class (JarvisEngine) has been removed.
Moved all logic core/engine.py to ExecutionEngine.

This file just:
    1. Starts TTS/STT modules
    2. Injects into ExecutionEngine
    3. Starts the engine with asyncio.run()
    4. Provides GUI callback hook

The old main.py backup can be stored as main_v7_backup.py."""

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

# Mute HuggingFace and SentenceTransformers logs
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)

# [V12.1] Completely silences pure text flowing to Progress Bar (tqdm) and stderr
os.environ["TQDM_DISABLE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"

import sys
class StderrFilter(object):
    def __init__(self, stream):
        self.stream = stream
    def write(self, data):
        # Ignore loading screen texts
        if any(x in data for x in ["Loading weights", "BertModel LOAD REPORT", "embeddings.position_ids", "UNEXPECTED", "HF_TOKEN", "unauthenticated requests", "huggingface.co"]):
            return
        self.stream.write(data)
    def flush(self):
        self.stream.flush()

sys.stderr = StderrFilter(sys.stderr)

from core.engine import ExecutionEngine
from core.config import EngineConfig


async def main():
    """J.A.R.V.I.S. v8.0 main entry point.

    Lifecycle:
        1. Initialize TTS/STT modules
        2. Create ExecutionEngine
        3. Inject I/O interfaces
        4. Start Engine (infinite loop)"""
    config = EngineConfig()
    engine = ExecutionEngine(config)

    # ── TTS enjeksiyonu ──
    try:
        from audio.tts import TextToSpeech
        tts = TextToSpeech()
        engine.set_tts(tts.speak)
        print("[INIT] TTS module: Online")
    except Exception as e:
        print(f"[INIT] Failed to load TTS module: {e}")

    # ── STT enjeksiyonu ──
    try:
        from audio.stt import SpeechToText
        stt = SpeechToText()
        engine.set_stt(stt.listen)
        print("[INIT] STT module: Online")
    except Exception as e:
        print(f"[INIT] Failed to load STT module (stdin fallback): {e}")

    # ── Initialize subsystems ──
    await engine.initialize()

    # ── Enter main loop ──
    await engine.start()


def launch_with_gui():
    """Starting in GUI mode — Called by gui/interface.py.
    Injects GUI callbacks into the Engine.

    Usage (from gui/interface.py):
        from main import launch_with_gui
        launch_with_gui()"""
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
