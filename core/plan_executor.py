"""
[V8.3] J.A.R.V.I.S. Plan Executor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Plan adımlarını sıralı/paralel yürüten katman.
V8.3 Düzeltmesi: Mangled code cleanup + TypeError fix.
"""

import asyncio
import logging
import re
import time
import json
import os
from typing import Optional, List, Any

from core.planner import parse_plan, ExecutionPlan, PlanNode
from tools.base_tool import ToolResult

logger = logging.getLogger("JARVIS.PlanExecutor")

# [V15.5] Kod hata düzeltme döngüsü için maksimum deneme sayısı
MAX_CODE_FIX_ATTEMPTS = 3


class PlanExecutor:
    """
    J.A.R.V.I.S. v8.3 Plan Yürütme Katmanı.
    """

    def __init__(self, brain, memory, executor, state_manager, io_bridge, config):
        self.brain = brain
        self.memory = memory
        self.executor = executor
        self.state_manager = state_manager
        self.io_bridge = io_bridge
        self.config = config

        # State tracking (Tool'lara aktarılır)
        self.last_whatsapp_num = None
        self.last_whatsapp_time = 0.0
        self.last_active_file = None
        self.last_contact = None
        self.contacts_path = "contacts.json"

    def _load_contacts(self) -> dict:
        if not os.path.exists(self.contacts_path):
            return {}
        try:
            with open(self.contacts_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Rehber yükleme hatası: {e}")
            return {}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PLAN EXECUTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def execute_plan(self, task_state, plan: ExecutionPlan, _replan_depth: int = 0) -> None:
        logger.info(f"Plan yürütülüyor: {plan.total_steps} ana adım. (depth={_replan_depth})")

        tags_in_plan = [n.protocol_tag.upper() for n in plan.steps]
        has_whatsapp = any("WHATSAPP" in t for t in tags_in_plan)

        for i, node in enumerate(plan.steps):
            if not task_state.is_active():
                break

            # Logic Shield
            if node.protocol_tag.upper() == "VISION" and has_whatsapp:
                if any("SEARCH" in t for t in tags_in_plan[:i]):
                    logger.warning(f"Adım {node.step_number} (VISION) atlandı.")
                    continue

            if node.sub_nodes:
                tasks = [self.execute_node(task_state, snode) for snode in node.sub_nodes]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                if any(isinstance(r, Exception) or r is False for r in results):
                    logger.warning(f"Adım {node.step_number} paralel yürütmede kısmi hata.")
            else:
                success = await self.execute_node(task_state, node)
                if not success:
                    if _replan_depth >= self.config.max_replan_attempts:
                        reason = f"Adım {node.step_number} başarısız; max replan aşıldı."
                        logger.error(reason)
                        await self.io_bridge.speak("Efendim, plan limiti aşıldı.")
                        self.state_manager.fail_task(task_state.id, reason)
                        return

                    new_plan = await self.replan(task_state, plan, node, "Adım başarısız")
                    if new_plan:
                        await self.execute_plan(task_state, new_plan, _replan_depth=_replan_depth + 1)
                    else:
                        self.state_manager.fail_task(task_state.id, "Replan başarısız.")
                    return

        if task_state.is_active():
            self.state_manager.complete_task(task_state.id)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  NODE EXECUTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def execute_node(self, task_state, node: PlanNode) -> bool:
        """Tek bir plan düğümünü yürütür. [V13.0 Integrated]"""
        
        # 1. Bütünleşik Çekirdek Protokolleri (Araç gerektirmeyenler)
        if node.protocol_tag.upper() == "SPEAK":
            await self.io_bridge.speak(str(node.argument))
            task_state.add_tool_call("SPEAK", str(node.argument), {"success": True})
            return True

        # 2. Iron Dome & Aliases & [V14.0] Adaptive Learning
        if not self.executor.registry.is_registered(node.protocol_tag):
            # Try smart alias
            alias = self.executor.registry.smart_aliases.get(node.protocol_tag.upper())
            if alias:
                node.protocol_tag = alias
            else:
                logger.warning(f"Iron Dome: Kayıtsız protokol engellendi: {node.protocol_tag}")
                
                # [V14.0] Bilinmeyen komutlar için kendi kendine öğrenmeyi dene
                learned = False
                if hasattr(self.brain, '_adaptive_learner_ref') and self.brain._adaptive_learner_ref:
                    logger.info(f"Iron Dome: Bilinmeyen komut LLM ile çözümlenmeye çalışılıyor...")
                    await self.io_bridge.speak("Bu yeteneğim henüz tanımlı değil, nasıl yapabileceğimi öğreniyorum...")
                    
                    available_tools = self.executor.registry.all_tags
                    # Orijinal kullanıcı komutunu task_state'den al
                    original_req = getattr(task_state, 'goal', str(node.argument))
                    
                    learned_data = await self.brain._adaptive_learner_ref.learn_unknown_command(
                        self.brain, original_req, available_tools
                    )
                    
                    if learned_data and learned_data.get("tool") != "SPEAK":
                        logger.info(f"Iron Dome: LLM başarılı bir strateji buldu: {learned_data}")
                        node.protocol_tag = learned_data["tool"]
                        node.argument = learned_data["argument"]
                        learned = True
                        await self.io_bridge.speak(f"Bulduğum en uygun yöntemle deniyorum.")
                
                if not learned:
                    # [V16.0] Kutsal Kase: Tool Synthesis (Kendi Kendine Kod Yazma)
                    synthesized = False
                    if hasattr(self, 'skill_synthesizer') and self.skill_synthesizer:
                        await self.io_bridge.speak(f"Efendim, bu işlem için hazır bir aracım yok. GroqBrain ile anında yeni bir araç kodluyorum. Lütfen bekleyin.")
                        original_req = getattr(task_state, 'goal', str(node.argument))
                        # Tool tag geçerli bir sınıf ismi formuna yakın olması için temizlenir
                        safe_tag = "".join(c if c.isalnum() else "_" for c in node.protocol_tag.upper())
                        if not safe_tag:
                            safe_tag = "DYNAMIC_TOOL"
                        synthesized = await self.skill_synthesizer.synthesize_tool(self.brain, original_req, safe_tag)
                        
                    if synthesized:
                        await self.io_bridge.speak(f"Yeni aracı başarıyla sentezledim ve sisteme enjekte ettim. Şimdi çalıştırıyorum.")
                        node.protocol_tag = safe_tag
                    else:
                        await self.io_bridge.speak(
                            f"Efendim, '{node.protocol_tag}' adında bir yeteneğim yok. "
                            f"Kendi başıma bir araç da sentezleyemedim."
                        )
                        return False

        # 3. Context Interpolation
        context = self._build_context(task_state)
        
        # 3. Execution
        logger.info(f"[execute_node] Başlatılıyor: [{node.protocol_tag}] arg='{str(node.argument)[:60]}'")
        try:
            # CORRECTED SIGNATURE: engine_context=context
            result = await self.executor.execute_tool(
                node.protocol_tag, 
                str(node.argument), 
                engine_context=context
            )
        except Exception as e:
            logger.error(f"[execute_node] Tool execute hatası: {e}", exc_info=True)
            return False

        # ── [V15.5] PYTHON_EXEC SELF-HEALING DÖNGÜSÜ ──────────────────────
        # Eğer Python kodu hata verdiyse, hatayı LLM'e gönderip kodu düzelttir.
        if not result.success and node.protocol_tag.upper() == "PYTHON_EXEC":
            result = await self._python_self_heal(node, result, context, task_state)
        # ─────────────────────────────────────────────────────────────────────

        # 4. State Update
        task_state.add_tool_call(node.protocol_tag, str(node.argument), result.to_dict())
        
        # 5. Post-Action
        await self._handle_post_execution(task_state, result)
        
        return result.success

    async def _handle_post_execution(self, task_state, result: ToolResult) -> None:
        """Yürütme sonrası TTS veya GUI güncellemelerini yönetir."""
        if result.speak:
            await self.io_bridge.speak(result.speak)
            
        if result.next_action:
            await self.handle_next_action(result)

    async def execute_single(self, task_state, response: str) -> None:
        """Yanıttaki tüm protokol etiketlerini sırayla yürütür."""
        # [PROTOL SIZINTISI KORUMASI - ULTRA GÜVENLİ]
        # Yanıt sadece ve sadece resmi J.A.R.V.I.S. protokol başlangıçları ([PROTOCOL: veya [PLAN) ile başlıyorsa çalıştırılır.
        # Aksi takdirde bu kesinlikle konuşmadır. İçindeki tüm sızıntı etiketleri temizlenip doğrudan seslendirilir.
        cleaned_response = response.strip()
        if not (cleaned_response.startswith("[PROTOCOL:") or cleaned_response.startswith("[PLAN") or cleaned_response.startswith("[/PLAN")):
            logger.warning(f"[PlanExecutor] Protokol sızıntısı engellendi. Konuşma olarak yürütülüyor.")
            import re as _re
            clean_speech = _re.sub(r'\[PROTOCOL:.*?\]', '', response).strip()
            await self.io_bridge.speak(clean_speech)
            self.state_manager.complete_task(task_state.id)
            return

        matches = list(re.finditer(r'\[PROTOCOL:\s*(\w+)\](.*?)(?=\[PROTOCOL:|$)', response, re.DOTALL))
        if not matches:
            self.state_manager.complete_task(task_state.id)
            return
            
        for i, match in enumerate(matches):
            tag = match.group(1).upper()
            arg = match.group(2).strip()
            node = PlanNode(step_number=i+1, protocol_tag=tag, argument=arg)
            success = await self.execute_node(task_state, node)
            if not success:
                self.state_manager.fail_task(task_state.id, f"{tag} işlemi başarısız oldu.")
                return
                
        self.state_manager.complete_task(task_state.id)

    async def handle_next_action(self, result: ToolResult) -> None:
        """Tool sonucundaki next_action sinyallerini işler."""
        if not result.next_action: return

        handlers = {
            "START_DICTATION":      self._handle_dictation,
            "VISION_INTERPRET":     self._handle_vision_interpret,
            "PYTHON_INTERPRET":     self._handle_python_interpret,
            "CONFIRM_BROWSER_KILL": self._handle_browser_kill_confirm,
            "RUN_STRESS_TEST":      self._handle_stress_test,
            "CLEAR_LAST_HISTORY":   self._handle_clear_history,
            "FILE_WRITE_INTERPRET": self._handle_file_write_interpret,
        }
        handler = handlers.get(result.next_action)
        if handler:
            await handler(result)

    async def _handle_dictation(self, result) -> None:
        self.io_bridge.update_gui("DİKTE EDİLİYOR")
        dictated_msg = await self.io_bridge.get_input()
        if not dictated_msg: return
        
        recipient = result.data.get("recipient", self.last_contact)
        contacts = self._load_contacts()
        matched = self._fuzzy_match_contact(recipient, contacts)
        
        if matched:
            from tools.utils.native_ops import NativeOps
            for m_name, m_num in matched:
                await asyncio.get_running_loop().run_in_executor(None, NativeOps.send_whatsapp_blind, m_num, dictated_msg)
                self.last_whatsapp_num = m_num
                self.last_whatsapp_time = time.time()
                self.last_contact = m_name

    @staticmethod
    def _strip_speak_tag(text: str) -> str:
        """
        Brain bazen '[PROTOCOL: SPEAK] mesaj' formatında yanıt döner.
        Bu etiket io_bridge.speak()'e ham geçilirse log'a sızar.
        Yalnızca temiz mesaj metnini döndürür.
        """
        import re as _re
        # [PROTOCOL: SPEAK] veya [PROTOCOL:SPEAK] etiketini baştan soy
        cleaned = _re.sub(r'^\s*\[PROTOCOL\s*:\s*SPEAK\]\s*', '', text, flags=_re.IGNORECASE)
        return cleaned.strip()

    async def _handle_vision_interpret(self, result) -> None:
        raw_analysis = result.data.get("raw_analysis", "")
        if not raw_analysis: return
        final = await self.brain.think(f"Ekranda ne olduğunu Efendine açıkla: '{raw_analysis}'")
        await self.io_bridge.speak(self._strip_speak_tag(final))

    async def _handle_python_interpret(self, result) -> None:
        output = result.data.get("output", "")
        if not output: return
        final = await self.brain.think(
            f"Yazdığın Python kodunun çıktısı şu: '{output}'. "
            f"Bu sonucu Efendine doğal, kısa ve saygılı bir dille söyle. "
            f"(Örn: 'Efendim, hesaplamayı tamamladım, sonuç şu...' gibi)"
        )
        await self.io_bridge.speak(self._strip_speak_tag(final))

    async def _handle_file_write_interpret(self, result) -> None:
        filename = result.data.get("filename", "")
        prompt = (
            f"Az önce '{filename}' dosyasına yazma işlemi gerçekleştirdin. "
            f"Efendine çok kısa (1-2 cümle) bir dille 'ne yazdığını' ve 'bunu neden yaptığını' söyle. "
            f"Örn: 'Efendim, hesap makinesi fonksiyonunu düzelttim çünkü toplama hatası vardı.'"
        )
        final = await self.brain.think(prompt, bypass_history=True)
        await self.io_bridge.speak(self._strip_speak_tag(final))

    async def _handle_browser_kill_confirm(self, result) -> None:
        browser = result.data.get("browser", "")
        confirm = await self.io_bridge.get_input()
        if confirm and "evet" in confirm.lower():
            from tools.utils.native_ops import NativeOps
            await asyncio.get_running_loop().run_in_executor(None, NativeOps.kill_app, browser)
            await self.io_bridge.speak(f"{browser} kapatıldı Efendim.")

    async def _handle_stress_test(self, result) -> None:
        await self.io_bridge.speak("Stres testi tamamlandı.")

    async def _handle_clear_history(self, result) -> None:
        if hasattr(self.brain, "chat_history"):
            self.brain.chat_history = self.brain.chat_history[:-1]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [V15.5] PYTHON SELF-HEALING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _python_self_heal(
        self,
        node: "PlanNode",
        failed_result: "ToolResult",
        context: dict,
        task_state,
    ) -> "ToolResult":
        """
        [V15.5] Python Kod Öz-İyileştirme Döngüsü
        ─────────────────────────────────────────────
        Bir PYTHON_EXEC adımı başarısız olduğunda:
        1. Hatalı kodu + hata mesajını alır.
        2. LLM'e "Kodu düzelt" prompt'u gönderir.
        3. Düzeltilmiş kodu aynı tool üzerinden tekrar çalıştırır.
        4. Başarılı olana veya MAX_CODE_FIX_ATTEMPTS'a ulaşana kadar döner.
        """
        current_result = failed_result
        broken_code = str(node.argument)  # İlk kod

        for attempt in range(1, MAX_CODE_FIX_ATTEMPTS + 1):
            error_detail = current_result.message or str(current_result.error)
            logger.warning(
                f"[PythonSelfHeal] Deneme {attempt}/{MAX_CODE_FIX_ATTEMPTS} — "
                f"hata: {error_detail[:120]}"
            )

            # Kullanıcıya bildir
            await self.io_bridge.speak(
                f"Efendim, kodumda bir hata var. Düzeltiyorum, deneme {attempt}."
            )

            # LLM'e düzeltme talebi gönder (bypass_history=True → bağlamı kirletme)
            fix_prompt = (
                f"[PYTHON KOD DÜZELTME GÖREVİ]\n"
                f"Aşağıdaki Python kodu çalıştırıldı ve hata verdi.\n"
                f"Hatayı düzelt ve SADECE düzeltilmiş, çalışan Python kodunu ver.\n"
                f"KURALLAR:\n"
                f"  - Hiç açıklama metni yazma, sadece saf Python kodu yaz.\n"
                f"  - Kod içinde input() KULLANMA.\n"
                f"  - Sonucu mutlaka print() ile yaz.\n"
                f"  - Markdown (```) veya protokol etiketi KULLANMA.\n\n"
                f"HATALI KOD:\n{broken_code}\n\n"
                f"HATA MESAJI:\n{error_detail}\n\n"
                f"Düzeltilmiş kod:"
            )

            try:
                fixed_response = await self.brain.think(fix_prompt, bypass_history=True)
            except Exception as brain_err:
                logger.error(f"[PythonSelfHeal] Brain çağrısı başarısız: {brain_err}")
                break

            # LLM yanıtından ham kodu çıkar (protokol etiketleri veya markdown varsa sil)
            import re as _re
            fixed_code = fixed_response
            # [PROTOCOL: PYTHON_EXEC] veya [PROTOCOL: SPEAK] gibi etiket varsa içeriği al
            protocol_match = _re.search(
                r'\[PROTOCOL:\s*PYTHON_EXEC\]\s*(.+)',
                fixed_code, _re.DOTALL | _re.IGNORECASE
            )
            if protocol_match:
                fixed_code = protocol_match.group(1).strip()
            # Markdown kod bloğu varsa temizle
            fixed_code = fixed_code.replace("```python", "").replace("```", "").strip()
            # Kalan protokol etiketlerini temizle
            fixed_code = _re.sub(r'\[/?[A-Z_ :]+PYTHON_EXEC[^\]]*\]', '', fixed_code)
            fixed_code = _re.sub(r'\[/?PROTOCOL[^\]]*\]', '', fixed_code)
            fixed_code = "\n".join(line for line in fixed_code.splitlines() if line.strip()).strip()

            if not fixed_code:
                logger.warning("[PythonSelfHeal] LLM boş kod döndürdü, duruyorum.")
                break

            logger.info(f"[PythonSelfHeal] LLM'den gelen düzeltilmiş kod:\n{fixed_code[:300]}")

            # Düzeltilmiş kodu çalıştır
            node.argument = fixed_code
            broken_code = fixed_code  # Bir sonraki iterasyon için güncelle

            try:
                new_result = await self.executor.execute_tool(
                    "PYTHON_EXEC",
                    fixed_code,
                    engine_context=context
                )
            except Exception as exec_err:
                logger.error(f"[PythonSelfHeal] Düzeltilmiş kod execute hatası: {exec_err}")
                break

            if new_result.success:
                logger.info(f"[PythonSelfHeal] Deneme {attempt}'de başarıyla düzeltildi.")
                await self.io_bridge.speak("Kodu düzelttim ve başarıyla çalıştırdım Efendim.")
                return new_result
            else:
                current_result = new_result

        # Tüm denemeler tükendi
        logger.error("[PythonSelfHeal] Tüm düzeltme denemeleri başarısız.")
        await self.io_bridge.speak(
            "Efendim, birkaç denemeye rağmen kodu düzeltemedim. "
            "Lütfen görevi daha ayrıntılı tarif eder misiniz?"
        )
        return current_result

    async def replan(self, task_state, old_plan, failed_node, error_msg: str) -> Optional[ExecutionPlan]:
        replan_prompt = (
            f"GÖREV BAŞARISIZ: {error_msg}.\n"
            f"Mevcut durum: {old_plan.get_context_summary()}\n"
            f"Tamamlanan adım sonuçları: {task_state.get_results()}\n"
            f"Yeni bir plan üret."
        )
        try:
            new_response = await self.brain.think(replan_prompt)
            return parse_plan(new_response)
        except: return None

    async def detect_and_parse_plan(self, response: str, user_input: str) -> Optional[ExecutionPlan]:
        if "PLAN" in response.upper() or "```json" in response:
            plan = parse_plan(response)
            if plan:
                plan.original_request = user_input
                return plan
        return None

    def _build_context(self, task_state) -> dict:
        ctx = {
            "task_id":            task_state.id,
            "last_whatsapp_num":  self.last_whatsapp_num,
            "last_whatsapp_time": self.last_whatsapp_time,
            "last_active_file":   self.last_active_file,
            "step_results":       task_state.get_results(),
            "io_bridge":          self.io_bridge,
            "brain":              self.brain,
            "memory":             self.memory,
            "plan_executor":      self,
        }
        if hasattr(self, 'scheduler') and self.scheduler:
            ctx["scheduler"] = self.scheduler
        return ctx

    def _fuzzy_match_contact(self, name_target: str, contacts: dict) -> list:
        matched = []
        name_clean = str(name_target).lower().strip()
        for c_name, c_num in contacts.items():
            if name_clean in c_name.lower() or c_name.lower() in name_clean:
                matched.append((c_name, c_num))
        return matched