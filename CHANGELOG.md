# Changelog

All notable changes to **J.A.R.V.I.S. Cognitive OS** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v16.3.0] - 2026-05-30
### Added
- **[System] STT Initialization Logs:** Translated the Groq Whisper & Fallback Google Web Speech API initialization logs to English to ensure a fully unified English system/console experience.
- **[UI/System] Global Translation:** Translated all major UI elements (HAFIZA to MEMORY, YAZILI MOD to TEXT MODE, KAPATILIYOR to SHUTTING DOWN), system logs, comments, and debug messages to English across the core system.

### Fixed
- **[Stability] Proactive Watcher Idle Fix:** Fixed a critical bug where the Proactive Watcher would mistakenly assume the user wanted to shut down J.A.R.V.I.S. after exactly 15 minutes of inactivity. Added a strict calibration rule forbidding the `SYSTEM_SHUTDOWN` and `SYSTEM_POWER` protocols during background proactive cycles.
- **[Core] System Tool Restoration:** Restored `system_tool.py` ensuring that all tool classes (StressTestTool through YouTubeStrategyTool) are fully operational.

---

## [v16.2.0]
### Added
- **[Installer] 1-Click System Setup (`install.bat`):** Added a new, fully automated 7-step installer for Windows systems. Sets up Python `venv`, fetches FFmpeg, manages configs, and places a desktop shortcut.

### Fixed
- **[Optimizations] Memory Leak Fix:** Addressed a critical memory leak in `SemanticRouter` during TF-IDF vector pruning.
- **[Optimizations] Semantic Routing Threshold:** Expanded confidence routing; scores between `0.30 <= score < 0.65` now match with `is_forced=False`, keeping local matching speed while leaving final validation to the cognitive LLM.

---

## [v16.1.0] - The Architect Update
### Added
- **[Security] Un-bypassable AST Sandbox:** Enhanced AST validation of `DynamicSkillSynthesizer` to block all potential sandbox escape vectors. Direct built-in manipulation (`__import__`, `getattr`, `setattr`, `globals`, `locals`, `compile`) and dunder attributes (`__builtins__`, `__dict__`, `__class__`, etc.) are now strictly blocked. Validation runs entirely asynchronous in a thread pool to avoid blocking the event loop.
- **Async LRU & FFmpeg Integration:** Refactored caching to support async flows and integrated FFmpeg properly for local audio operations.
- **Code Freeze:** Formalized core OS stability with strict checks and silent exception swallowing prevention.

---

## [v16.0.0]
### Added
- **[Dynamic Skill Synthesizer]:** Autonomously writes its own asynchronous Python tools on the fly, applies AST security checks, and hot-loads them into the registry.

---

## [v15.4.0]
### Added
- **[Cognitive OS Evolution]:** TTS cache, sandbox input block, reflection self-healing engine, and dynamic config updates.
- **[Memory Protocols]:** Added `REMEMBER` and `STARTUP_REMINDER` protocols for true episodic memory creation.

---

## [v15.0.0]
### Added
- **[Self-Learning Loop]:** Implemented autonomous self-learning loop with dynamic embedding cache.
- **[Semantic Router]:** Implemented zero-latency vector-based semantic router, replacing the legacy regex engine.

---

## [v13.2.0]
### Added
- **[Ghost Shield]:** Implemented Ghost Shield to prevent Whisper hallucinations and low-energy speech processing.
- **[Updater]:** Added one-click auto-updater (`update.py`) — no Git required, protects personal data.

---

*(Earlier version histories can be found within the repository commit history.)*
