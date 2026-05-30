import pygame
import threading
import asyncio
import os
import tempfile
import edge_tts
import logging

# [V15.5] Translation cache — same sentence is translated once, instant return on subsequent calls
_TRANSLATION_CACHE: dict = {}

class TextToSpeech:
    def __init__(self):
        # Initialize pygame for audio playback
        pygame.mixer.init()
        
    def speak(self, text: str):
        # Always use RyanNeural (British Jarvis) voice
        voice = "en-GB-RyanNeural"
        
        # Use daemon thread so it doesn't block the main loop
        thread = threading.Thread(target=self._play_audio, args=(text, voice), daemon=True)
        thread.start()
        
    def _play_audio(self, text: str, voice: str):
        temp_path = None
        try:
            # Default rate and pitch for RyanNeural (charismatic)
            rate = "+0%"
            pitch = "+0Hz"
            
            # Create a temporary mp3 file
            fp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            fp.close()
            temp_path = fp.name
            
            # Edge-TTS Async Execution and Translation
            async def generate_speech():
                global _TRANSLATION_CACHE
                speech_text = text

                # ── Translation Cache + 429 Retry ────────────────────────
                if text in _TRANSLATION_CACHE:
                    speech_text = _TRANSLATION_CACHE[text]
                else:
                    import urllib.request
                    import urllib.parse
                    import urllib.error
                    import json as _json
                    import time as _time

                    def _do_translate() -> str:
                        encoded = urllib.parse.quote(text)
                        url = (
                            "https://translate.googleapis.com/translate_a/single"
                            f"?client=gtx&sl=tr&tl=en&dt=t&q={encoded}"
                        )
                        req = urllib.request.Request(
                            url, headers={"User-Agent": "Mozilla/5.0"}
                        )
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            raw = resp.read().decode("utf-8")
                        data = _json.loads(raw)
                        return "".join(part[0] for part in data[0] if part[0])

                    try:
                        loop = asyncio.get_running_loop()
                        translated = await loop.run_in_executor(None, _do_translate)
                        if translated:
                            _TRANSLATION_CACHE[text] = translated
                            speech_text = translated
                    except urllib.error.HTTPError as e:
                        if e.code == 429:
                            # Rate limit — wait 3 seconds and retry twice
                            for retry_count in range(2):
                                # logging.warning(f"TTS: 429 Rate Limit (Attempt {retry_count+1}), waiting 3s...")
                                await asyncio.sleep(3)
                                try:
                                    translated = await loop.run_in_executor(None, _do_translate)
                                    if translated:
                                        _TRANSLATION_CACHE[text] = translated
                                        speech_text = translated
                                        break
                                except Exception:
                                    continue
                        else:
                            pass # logging.warning(f"TTS Translation HTTP error ({e.code}): {e} — using original text")
                    except Exception as e:
                        pass # logging.warning(f"TTS Translation error: {e} — using original text")
                # ──────────────────────────────────────────────────────────
                    
                retries = 3
                for attempt in range(retries):
                    try:
                        communicate = edge_tts.Communicate(speech_text, voice, rate=rate, pitch=pitch)
                        # Add 15s timeout per attempt via asyncio.wait_for (for long sentences)
                        await asyncio.wait_for(communicate.save(temp_path), timeout=15)
                        return True
                    except Exception as e:
                        if attempt < retries - 1:
                            # print(f"[TTS_RETRY] Attempt {attempt+1} failed: {e}. Retrying...")
                            await asyncio.sleep(0.5)
                        else:
                            raise e
                return False
                
            asyncio.run(generate_speech())
            
            # Play the generated file with Pygame
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()
            else:
                raise Exception("Audio file could not be created.")
            
            # Wait until audio finishes (only this thread blocks, main GUI stays responsive)
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
                
        except Exception as e:
            # print(f"\n[AUDIO MODULE ERROR]: Could not generate speech via edge-tts: {str(e)}")
            # [V8.2 FIXED] pyttsx3 fallback disabled.
            # Continuing silently to prevent asyncio loop conflicts and "run loop already started" errors.
            # logging.warning(f"TTS failed (Internet/DNS?), continuing silently. Detail: {e}")
            return
            
        finally:
            pygame.mixer.music.unload()
            # Clean up temp files
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
