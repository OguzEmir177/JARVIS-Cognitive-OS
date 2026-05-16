"""
[V12.0] J.A.R.V.I.S. Cognitive Execution Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Merkezi orkestrasyon katmanı. 
Sorumluluklar:
    - Alt sistemlerin (Brain, Memory, IOBridge, PlanExecutor) başlatılması
    - Ana girdi döngüsü (Input Loop)
    - Görev durum yönetimi (TaskState)
"""

import asyncio
import logging
import re
import uuid
from typing import Callable, Optional

from core.telemetry import telemetry

from core.io_bridge import IOBridge
from core.state_manager import TaskState, StateManager
from core.task_queue import TaskQueue, TaskPriority
from core.planner import parse_plan, ExecutionPlan
from core.executor import Executor
from core.reflector import Reflector
from core.brain import GroqBrain
from core.memory import MemoryManager
from core.config import EngineConfig
from core.cognitive_core import CognitiveCore
from core.pattern_extractor import PatternExtractor
from core.adaptive_learner import AdaptiveLearner
from errors import JarvisError

logger = logging.getLogger("JARVIS.Engine")

class ExecutionEngine:
    """
    J.A.R.V.I.S. v8.1 Merkezi Orkestratör.
    """

    def __init__(self, config: Optional[EngineConfig] = None) -> None:
        self.config = config or EngineConfig()
        self._running: bool = False

        # decoupled bileşenler
        self.io_bridge = IOBridge(self.config)
        self.state_manager: StateManager = StateManager()
        self.task_queue: TaskQueue = TaskQueue(maxsize=self.config.max_queue_size)
        
        # Core bileşenler (initialize içinde kurulur)
        self.brain: Optional[GroqBrain] = None
        self.memory: Optional[MemoryManager] = None
        self.executor: Optional[Executor] = None
        self.reflector: Optional[Reflector] = None
        self.plan_executor: Optional["PlanExecutor"] = None
        self.cognitive_core: Optional[CognitiveCore] = None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  IO BRIDGE PROXIES (GUI Compatibility)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @property
    def text_mode(self) -> bool:
        return self.io_bridge.text_mode

    @text_mode.setter
    def text_mode(self, value: bool) -> None:
        self.io_bridge.text_mode = value

    @property
    def text_input_queue(self) -> Optional[object]:
        return self.io_bridge.text_input_queue

    @text_input_queue.setter
    def text_input_queue(self, value: Optional[object]) -> None:
        self.io_bridge.text_input_queue = value

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  DEPENDENCY INJECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def set_tts(self, tts_func: Callable) -> None:
        self.io_bridge.set_tts(tts_func)

    def set_stt(self, stt_func: Callable) -> None:
        self.io_bridge.set_stt(stt_func)

    def set_stt_instance(self, instance: object) -> None:
        self.io_bridge.set_stt_instance(instance)

    def reset_audio(self) -> None:
        """Kilitlenen ses motorunu (STT) GUI üzerinden sıfırlamak için kullanılır."""
        self.io_bridge.reset_audio_engine()

    def set_gui_callback(self, callback: Callable) -> None:
        self.io_bridge.set_gui_callback(callback)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  LIFECYCLE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def initialize(self) -> None:
        """Tüm alt sistemleri başlatır."""
        logger.info("Engine başlatılıyor...")

        # 1. Memory
        self.memory = await asyncio.get_running_loop().run_in_executor(
            None, self._init_memory
        )

        # 2. Brain
        self.brain = await self._init_brain_with_retry()

        # 3. Context Compressor [V11.1]
        from core.context_compressor import ContextCompressor
        self.compressor = ContextCompressor()
        self.brain.compressor = self.compressor # Brain'e enjekte et

        # 4. Executor
        self.executor = Executor(
            brain=self.brain,
            memory=self.memory,
            config=self.config,
        )

        # 5. Reflector
        self.reflector = Reflector(
            memory=self.memory,
            brain=self.brain,
        )

        # 6. Plan Executor
        from core.plan_executor import PlanExecutor
        self.plan_executor = PlanExecutor(
            self.brain, self.memory, self.executor, 
            self.state_manager, self.io_bridge, self.config
        )

        # [V9.0] ContactManager — kişi profil yöneticisi başlatma
        from core.contact_manager import ContactManager
        self.contact_manager = ContactManager(memory_manager=self.memory)
        self.contact_manager.initialize()

        # PlanExecutor'a referans ver
        self.plan_executor.contact_manager = self.contact_manager
        logger.info("ContactManager başlatıldı ve PlanExecutor'a bağlandı.")
        
        # [V9.0] Scheduler oluştur
        from core.scheduler import JarvisScheduler
        self.scheduler = JarvisScheduler(engine=self)
        self.plan_executor.scheduler = self.scheduler
        logger.info("Scheduler oluşturuldu.")
        
        # [V10.2] Otonom Bekçi (Watcher)
        from core.watcher import ProactiveWatcher
        self.watcher = ProactiveWatcher(engine=self)
        logger.info("Proaktif Watcher başlatıldı.")
        
        # [V12.0] Initialize Cognitive Core
        from core.cognitive_core import CognitiveCore
        self.cognitive_core = CognitiveCore(self.config, self.brain, self.memory)
        await self.cognitive_core.initialize()
        
        # Skill Registry entegrasyonu
        self.cognitive_core.skill_registry.register_from_tool_registry(self.executor.registry)
        
        # Memory Consolidator
        from core.memory_consolidator import MemoryConsolidator
        self.memory_consolidator = MemoryConsolidator(memory=self.memory)
        self.scheduler.add_daily(2, 0, "__SYSTEM_CONSOLIDATE__")
        
        self.pattern_extractor = PatternExtractor(memory=self.memory)
        self.memory.pattern_extractor = self.pattern_extractor
        
        # [V15.4] Otonom Çöp Temizleyici (Auto-Cleanup)
        if self.memory and self.memory.collection:
            try:
                def _clean_junk():
                    results = self.memory.collection.get(include=["documents"])
                    bad_ids = [res_id for i, res_id in enumerate(results.get("ids", [])) 
                               if results["documents"][i] and "[ne yaptim]" in results["documents"][i].lower()]
                    if bad_ids:
                        self.memory.collection.delete(ids=bad_ids)
                        logger.info(f"Otonom Temizlik: ChromaDB'den {len(bad_ids)} adet çöp log silindi.")
                
                # Event loop'u bloklamadan arka planda temizle
                asyncio.get_running_loop().run_in_executor(None, _clean_junk)
            except Exception as e:
                logger.debug(f"Auto-cleanup hatası: {e}")

        # [V14.0] Adaptive Learner — Otonom Öğrenme Motoru
        self.adaptive_learner = AdaptiveLearner()
        self.brain._adaptive_learner_ref = self.adaptive_learner  # Brain'e referans ver
        logger.info(f"Adaptive Learner başlatıldı: {self.adaptive_learner.get_stats()['total_strategies']} strateji yüklendi.")
        
        logger.info("Engine ve Cognitive OS Core V14.0 başarıyla başlatıldı.")


    async def start(self) -> None:
        """Ana yürütme döngüsü."""
        self._running = True
        await self.io_bridge.speak("Efendim, sistemler hazır. Buyurun sizi dinliyorum.")
        # [V9.0] Scheduler'ı arka planda başlat
        self._scheduler_task = asyncio.create_task(self.scheduler.run())
        # [V9.9] Watcher'ı arka planda başlat
        self._watcher_task = asyncio.create_task(self.watcher.run())
        # [V12.0] Autonomous Cognition Loop başlat
        if self.cognitive_core:
            await self.cognitive_core.start_cognition_loop(self)

        while self._running:
            try:
                self.io_bridge.update_gui("DİNLİYOR")

                user_input = await self.io_bridge.get_input()
                if not user_input or len(user_input.strip()) < 2:
                    continue

                if self._is_shutdown_command(user_input):
                    await self._handle_shutdown()
                    break

                # [V9.5] ShutdownTool sentinel kontrolü
                if user_input == "__SHUTDOWN__":
                    break

                user_input = self._clean_wake_word(user_input)
                if not user_input:
                    await self.io_bridge.speak("Buyurun efendim, sizi dinliyorum.")
                    continue

                # [V12.0] Interrupt cognition loop on user input
                if self.cognitive_core:
                    self.cognitive_core.interrupt_cognition("user_input")

                await self.process_input(user_input)

                # [V9.5] ShutdownTool execute sonrası bayrağı kontrol et
                if self.io_bridge.shutdown_requested:
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Engine döngü hatası: {e}", exc_info=True)
                await self.io_bridge.speak("Efendim, bir hata oluştu.")
                await asyncio.sleep(1)

        await self.shutdown()

    async def shutdown(self) -> None:
        """Tüm alt sistemleri temiz bir şekilde kapatır."""
        self._running = False
        logger.info("Engine kapatılıyor...")

        # [V12.0] Cognition Loop durdur
        if self.cognitive_core:
            self.cognitive_core.stop_cognition_loop()
            if self.cognitive_core.perception:
                self.cognitive_core.perception.stop()

        # [V9.9] Watcher'ı durdur
        if hasattr(self, 'watcher'):
            self.watcher.stop()
            if hasattr(self, '_watcher_task') and not self._watcher_task.done():
                self._watcher_task.cancel()
                try:
                    await self._watcher_task
                except asyncio.CancelledError:
                    pass

        # [V9.0] Scheduler'ı durdur
        if hasattr(self, 'scheduler'):
            self.scheduler.stop()
        if hasattr(self, '_scheduler_task') and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        if self.executor:
            await self.executor.cleanup()
        logger.info("Engine V12.0 kapatıldı.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PROCESSING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def process_input(self, user_input: str) -> None:
        """
        [V11.1] Hibrit Kognitif İşleme Motoru.
        
        Mimari: CognitiveCore modülleri karar zenginleştirme için kullanılır,
        gerçek tool yürütme ise kanıtlanmış legacy pipeline üzerinden yapılır.
        
        Pipeline:
          1. Goal Tracking (CognitiveCore)
          2. Semantic Routing (ToolRouter - deterministic)
          3. Brain Reasoning (LLM)
          4. Plan Execution (Legacy PlanExecutor)
          5. Reflection & Recovery (CognitiveCore)
          6. Event Emission (EventBus)
        """
        if user_input == "__SYSTEM_CONSOLIDATE__":
            await asyncio.get_running_loop().run_in_executor(
                None, self.memory_consolidator.consolidate)
            await asyncio.get_running_loop().run_in_executor(
                None, self.memory_consolidator.prune_duplicates)
            return

        task_id = str(uuid.uuid4())[:8]
        telemetry.log_event(task_id, "REQUEST_RECEIVED", "start", {"user_input": user_input})
        task_state = self.state_manager.create_task(task_id=task_id, goal=user_input)
        goal = None

        try:
            await self.io_bridge.speak("Anlaşıldı Efendim.")
            self.io_bridge.update_gui("İŞLENİYOR")

            # ════════════════════════════════════════════════════════
            #  PHASE 0: ADAPTIVE LEARNING PRE-CHECK
            # ════════════════════════════════════════════════════════

            # A. Tekrar Tespiti — Aynı komutu kısa sürede tekrar mı etti?
            repeat_task_id = None
            if hasattr(self, 'adaptive_learner'):
                repeat_task_id = self.adaptive_learner.detect_repeat(user_input)
                if repeat_task_id:
                    logger.info(f"[V14.0] Tekrar tespit edildi — farklı strateji denenecek.")

            # B. Öğrenilmiş Strateji Kontrolü
            # [V15.0] FILE_* ve FOLDER_* operasyonları için learned strategy KULLANMA
            # — her dosya komutu farklı bir dosyayı hedefler, cached arg geçersiz olur
            FILE_DYNAMIC_TAGS = {"FILE_CREATE", "FILE_WRITE", "FILE_READ", "FILE_DELETE",
                                  "FOLDER_OPEN", "FILE_LATEST"}
            learned_strategy = None
            if hasattr(self, 'adaptive_learner') and not repeat_task_id:
                # Önce keyword router'ı çalıştır — eğer FILE_* ise learned strategy atla
                try:
                    _quick_route = self.cognitive_core.tool_router._keyword_route(user_input) if self.cognitive_core else None
                    if _quick_route and _quick_route.tool_tag.upper() in FILE_DYNAMIC_TAGS:
                        logger.info(f"[V15.0] {_quick_route.tool_tag} — learned strategy atlandı (dynamic)")
                    else:
                        learned_strategy = self.adaptive_learner.find_strategy(user_input)
                except Exception:
                    learned_strategy = self.adaptive_learner.find_strategy(user_input)

            # ════════════════════════════════════════════════════════
            #  PHASE 1: COGNITIVE ENRICHMENT (Pre-Execution)
            # ════════════════════════════════════════════════════════

            # A. Goal Tracking — Persistent objective memory
            if self.cognitive_core:
                goal = self.cognitive_core.goal_manager.create_goal(user_input)
                self.cognitive_core.attention.record_interaction()
                
                # Store in working memory
                try:
                    await self.cognitive_core.memory.store(user_input, "working")
                except Exception as mem_err:
                    logger.debug(f"Working memory store skipped: {mem_err}")

            # B. Semantic Routing — Deterministic tool selection (LLM bypass)
            forced_route = None
            
            # [V14.0] Öğrenilmiş strateji varsa, onu öncelikle kullan (FILE_* hariç)
            if learned_strategy and not repeat_task_id:
                from core.tool_router import RouteMatch
                forced_route = RouteMatch(
                    tool_tag=learned_strategy.tool_chain[0],
                    params={"query": learned_strategy.arguments[0] if learned_strategy.arguments else user_input},
                    confidence=learned_strategy.confidence,
                    is_forced=True,
                    reasoning=f"Learned strategy ({learned_strategy.success_count}x success)"
                )
                logger.info(f"[V14.0] Öğrenilmiş strateji kullanılıyor: {learned_strategy.tool_chain}")
            elif self.cognitive_core:
                try:
                    forced_route = self.cognitive_core.tool_router.route(user_input)
                    if forced_route:
                        telemetry.log_event(task_id, "ROUTING", "matched", {"tool": forced_route.tool_tag, "confidence": forced_route.confidence})
                except Exception as route_err:
                    logger.warning(f"Semantic router hatası (fallback to Brain): {route_err}")

            # ════════════════════════════════════════════════════════
            #  PHASE 2: EXECUTION (Real Tool Pipeline)
            # ════════════════════════════════════════════════════════

            if forced_route and forced_route.is_forced:
                # ── DETERMINISTIC PATH: Router forced a tool ──
                logger.info(
                    f"[OTONOM KARAR] {forced_route.tool_tag} "
                    f"(Güven: {forced_route.confidence:.3f}, Forced: True)"
                )
                from core.planner import PlanNode

                # [V15.0] Param extraction — FILE_* araçları için router'ın verdiği
                # parametreyi aynen kullan (file_path_and_content, folder_path vb.)
                params = forced_route.params or {}

                # FILE_* araçları için doğru param key'i kullan
                FILE_PARAM_KEYS = {
                    "FILE_WRITE":  "file_path_and_content",
                    "FILE_CREATE": "file_path",
                    "FILE_READ":   "file_path",
                    "FILE_DELETE": "file_path",
                    "FOLDER_OPEN": "folder_path",
                    "FILE_LATEST": "dir_path",
                }
                tool_tag = forced_route.tool_tag.upper()
                if tool_tag in FILE_PARAM_KEYS:
                    # Önce router'ın doğru key'ini dene
                    # [V15.0] KRITIK: '' (boş string) de geçerli bir değer —
                    # tool context'ten last_active_file alır. None check kullan.
                    expected_key = FILE_PARAM_KEYS[tool_tag]
                    val = params.get(expected_key)
                    if val is not None:
                        node_arg = val  # "" bile olsa geçir — tool context'ten alır
                    elif "query" in params:
                        node_arg = params["query"]
                    else:
                        node_arg = user_input
                else:
                    # Diğer araçlar: query varsa al, yoksa ilk value veya user_input
                    if "query" in params:
                        node_arg = params["query"]
                    elif params:
                        node_arg = next(iter(params.values()))
                    else:
                        node_arg = user_input

                node = PlanNode(
                    step_number=1,
                    protocol_tag=forced_route.tool_tag,
                    argument=node_arg
                )
                success = await self.plan_executor.execute_node(task_state, node)

                if not success:
                    last_tool = task_state.tool_history[-1] if task_state.tool_history else {}
                    if not last_tool.get("result", {}).get("speak"):
                        await self.io_bridge.speak(
                            f"Efendim, {forced_route.tool_tag} işlemi başarısız oldu. "
                            f"Farklı bir yol deneyeyim mi?"
                        )
                    self.state_manager.fail_task(task_id, f"Deterministic route failed: {forced_route.tool_tag}")
            else:
                # ── STANDARD PATH: Brain → Plan → Execute ──
                # 1. Beyin Düşünür
                response = await self.brain.think(user_input)
                if response == "RATE_LIMIT_ALL":
                    await self.io_bridge.speak("Efendim, beyin modülüm dinlenmeye geçti.")
                    if goal:
                        self.cognitive_core.goal_manager.update_goal(goal.id, status="failed")
                    return

                # [V9.5] Plan Sızıntı Temizleyici
                response = self._sanitize_llm_output(response)

                # 2. Plan tespiti ve yürütme
                plan = await self.plan_executor.detect_and_parse_plan(response, user_input)

                if plan:
                    await self.plan_executor.execute_plan(task_state, plan)
                else:
                    # [V9.8] Karışık İçerik Yönetimi
                    protocol_start = response.find("[PROTOCOL:")
                    if protocol_start > 0:
                        preceding_text = response[:protocol_start].strip()
                        if preceding_text:
                            await self.io_bridge.speak(preceding_text)
                        remaining_response = response[protocol_start:]
                        await self.plan_executor.execute_single(task_state, remaining_response)
                    elif protocol_start == 0:
                        await self.plan_executor.execute_single(task_state, response)
                    else:
                        await self.io_bridge.speak(response)
                        self.state_manager.complete_task(task_id)

            # ════════════════════════════════════════════════════════
            #  PHASE 3: COGNITIVE REFLECTION (Post-Execution)
            # ════════════════════════════════════════════════════════

            # A. Legacy Reflection (episodic memory)
            if self.reflector:
                _ref_task = asyncio.create_task(self.reflector.reflect(task_state))
                _ref_task.add_done_callback(
                    lambda t: logger.warning(f"Reflection task hatası: {t.exception()!r}")
                    if not t.cancelled() and t.exception() is not None
                    else None
                )

            # B. Pattern Extraction (learning from failures)
            if hasattr(self, 'pattern_extractor'):
                await asyncio.get_running_loop().run_in_executor(
                    None, self.pattern_extractor.extract_patterns)

            # C. Goal Completion
            if goal and self.cognitive_core:
                is_success = task_state.status != "failed"
                self.cognitive_core.goal_manager.update_goal(
                    goal.id,
                    status="completed" if is_success else "failed",
                    progress=1.0 if is_success else 0.0
                )
            
            telemetry.log_event(task_id, "RESPONSE_GENERATED", "end", {"status": task_state.status, "tools": len(task_state.tool_history)})

            # D. [V14.0] ADAPTIVE LEARNING — Başarı/Başarısızlık Kaydı
            if hasattr(self, 'adaptive_learner'):
                tools_used = [h.get("tool", "") for h in task_state.tool_history if h.get("tool")]
                args_used = [h.get("arg", "") for h in task_state.tool_history if h.get("tool")]
                is_success = task_state.status != "failed"
                
                if tools_used:
                    if is_success:
                        self.adaptive_learner.record_success(user_input, tools_used, args_used)
                    else:
                        self.adaptive_learner.record_failure(user_input, tools_used)
                
                # Repeat detection için task_id'yi güncelle
                self.adaptive_learner.update_recent_task_id(user_input, task_id)

            # E. Event Emission + Tool Learning
            if self.cognitive_core:
                await self.cognitive_core.event_bus.emit("TASK_COMPLETED", {
                    "task_id": task_id,
                    "goal": user_input,
                    "status": task_state.status,
                    "tools_used": len(task_state.tool_history),
                    "tool_used": task_state.tool_history[-1] if task_state.tool_history else ""
                }, sender="Engine")

        except Exception as e:
            logger.error(f"İşleme hatası [{task_id}]: {e}", exc_info=True)
            self.state_manager.fail_task(task_id, str(e))

            # Recovery System
            if self.cognitive_core:
                try:
                    recovery = await self.cognitive_core.recovery.handle_failure(
                        task_id, str(e), {"goal": user_input}
                    )
                    logger.info(f"Recovery strategy: {recovery}")
                    
                    if goal:
                        self.cognitive_core.goal_manager.update_goal(goal.id, status="failed")
                    
                    await self.cognitive_core.event_bus.emit("TASK_FAILED", {
                        "task_id": task_id, "error": str(e), "recovery": recovery
                    }, sender="Engine")
                except Exception as rec_err:
                    logger.warning(f"Recovery system hatası: {rec_err}")

            await self.io_bridge.speak("Efendim, bir sorun oluştu.")
        finally:
            self.io_bridge.update_gui("DİNLİYOR")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _sanitize_llm_output(text: str) -> str:
        """
        [V9.5] Plan Sızıntı Temizleyici (Plan Leak Sanitizer)
        ─────────────────────────────────────────────────────
        LLM bazen [PLAN] bloğunu [/PLAN] yerine uydurma etiketle kapatır.
        Bu etiketler parser'dan kaçıp kullanıcı ekranına ham string olarak sızar.

        Temizlenen örüntüler:
          ./PROTOCOL PLAN   [en sık görülen halüsinasyon]
          /PROTOCOL PLAN
          [/PROTOCOL]
          [/PROTOCOL PLAN]
          [PLAN_END]  [END_PLAN]  [/PLAN_END]
          ./PLAN  /PLAN (tek başına yanlış yerde)

        Strateji:
          - Önce köşeli parantezli tam örüntüler (en spesifik → greedy sorunu önler)
          - Sonra slash-prefix genel örüntüler
          - [/PLAN] (geçerli kapanış) DOKUNULMAZ.
        """
        if not text:
            return text

        # ── 1. Köşeli parantez içindeki uydurma kapanışlar (ÖNCELİKLİ) ───
        # [/PROTOCOL PLAN], [/PROTOCOL], [PLAN_END], [END_PLAN], [PLAN_CLOSE]
        text = re.sub(
            r'\[\.?/?(?:PROTOCOL(?:[:\s]+PLAN)?|PLAN_END|END_PLAN|PLAN_CLOSE|/PLAN_END)\]',
            '', text, flags=re.IGNORECASE
        )

        # ── 2. Nokta-slash prefix ile gelen uydurma etiketler ─────────────
        # Örn: "Google'da aratıldı ./PROTOCOL PLAN"
        text = re.sub(
            r'\.?\s*/\s*PROTOCOL(?:[:\s]+PLAN)?\b',
            '', text, flags=re.IGNORECASE
        )

        # ── 3. Slash-prefix genel uydurma etiketler ───────────────────────
        # /PROTOCOL, /PROTOCOL PLAN  (köşeli parantez olmadan)
        text = re.sub(
            r'(?<!\[)/\s*PROTOCOL(?:[:\s]+PLAN)?\b',
            '', text, flags=re.IGNORECASE
        )

        # ── 4. Protokol Sızıntısı Temizleyici (Metin içindeki sızıntılar) ─
        # Eğer bir satırda [PROTOCOL: REMEMBER] gibi bir ifade geçiyorsa ve bu bir komut değil de
        # cümlenin ortasındaysa onu temizle.
        # [V9.8] Sadece komut başlangıcı olmayanları temizle.
        def _leak_fixer(match):
            full_match = match.group(0)
            # Eğer satır başındaysa veya öncesinde sadece boşluk varsa komut kabul et (dokunma)
            # Ama metnin içindeyse ("Lütfen [PROTOCOL: ...]") temizle.
            start_pos = match.start()
            if start_pos > 0 and text[start_pos-1] not in ['\n', ' ']:
                return ""
            return full_match

        text = re.sub(r'\[PROTOCOL:\s*\w+\]', _leak_fixer, text, flags=re.IGNORECASE)

        # ── 4. Artık boş satırları temizle ────────────────────────────────
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+\n', '\n', text)

        return text.strip()

    def _is_shutdown_command(self, text: str) -> bool:
        return any(cmd in text.lower() for cmd in ["sistemi kapat", "jarvis kapan", "kendini kapat", "çıkış yap"])

    def _clean_wake_word(self, text: str) -> str:
        # v8.0 logic simplified for orchestrator
        return text.strip()

    async def _handle_shutdown(self) -> None:
        """
        [V9.5 FIX] Keyword ile tetiklenen kapatma yolu.
        Artık io_bridge.request_shutdown() çağrılıyor:
          → GUI'ye 'KAPATILIYOR' sinyali gider → _on_close() tetiklenir
          → Sentinel kuyruğa girer → blocking get() açılır
          → self._running = False  (engine döngüsü kırılır)
        """
        await self.io_bridge.speak("Sistemler kapatılıyor. İyi günler dilerim Efendim.")
        self.io_bridge.request_shutdown()   # ← GUI sinyali + bayrak + sentinel
        self._running = False

    def _init_memory(self):
        from core.memory import MemoryManager
        # [V8.1 Fix] Pass path string, not config object
        m = MemoryManager(db_path=self.config.memory_db_path)
        m.initialize()
        return m

    async def _init_brain_with_retry(self) -> "GroqBrain":
        """
        [V8.1 FIX] BUG #3: Gerçek retry döngüsü — önceki versiyonda check_connection()
        dönüş değeri yok sayılıyor ve hiçbir retry yapılmıyordu.

        Strateji:
            - Her başarısız denemeden sonra üstel geri çekilme (2^attempt saniye)
            - Tüm denemeler tükenirse kısıtlı modda devam et (çökme değil)
        """
        from core.brain import GroqBrain
        b = GroqBrain(self.config, memory_manager=self.memory)

        for attempt in range(self.config.brain_connect_retries):
            connected = await b.check_connection()
            if connected:
                logger.info(f"Brain bağlantısı kuruldu (deneme {attempt + 1}/{self.config.brain_connect_retries})")
                return b

            wait_s = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s…
            logger.warning(
                f"Brain bağlantı denemesi {attempt + 1}/{self.config.brain_connect_retries} "
                f"başarısız. {wait_s}s sonra tekrar denenecek..."
            )
            await asyncio.sleep(wait_s)

        # Tüm denemeler başarısız — kısıtlı modda başlat (RuntimeError atmıyoruz)
        logger.error(
            "Brain bağlantısı hiç kurulamadı! "
            "Sistem kısıtlı modda (bağlantısız) başlatılıyor."
        )
        return b

    def _setup_logging(self) -> None:
        pass