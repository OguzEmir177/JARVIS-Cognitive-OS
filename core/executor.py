"""
[V8.0] J.A.R.V.I.S. Tool Executor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool Registry üzerinden araç bulup çalıştıran katman.

Sorumluluklar:
    - Protocol tag → tool eşleştirme
    - Parametre hazırlama (arg → param dict)
    - Async tool execution (blocking tool'lar run_in_executor ile)
    - Metadata-tabanlı fallback tool seçimi
    - Tool çalışma süresini ölçme

Tasarım Kararları:
    Neden Executor ayrı bir class?
    → engine.py'yi tool çalıştırma detaylarından soyutlar.
    → Tool seçim mantığı (metadata, fallback) tek yerde.
    → Tool'lar engine state'e dokunmaz kuralını executor zorlar
      (engine_context salt-okunur dict olarak geçirilir).

    Neden execute_tool() async?
    → Playwright tool'lar native async.
    → Blocking tool'lar (pyautogui, subprocess) için
      run_in_executor() kullanılır.
    → Engine asyncio.wait_for(timeout) ile sarabilir.

Edge Cases:
    - Bilinmeyen protocol_tag → ToolExecutionError
    - Tool.execute() exception fırlatırsa → ToolExecutionError'a sar
    - Fallback tool bulunamazsa → None döner (engine karar verir)
    - Tool süresi config.tool_timeout_seconds'ı aşarsa →
      engine tarafında TimeoutError (executor'ın sorumluluğu değil)
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

from core.config import EngineConfig
from core.brain import GroqBrain
from core.memory import MemoryManager
from tools.base_tool import BaseTool, ToolResult
from tools.tool_registry import ToolRegistry, create_default_registry
from errors import ToolExecutionError
from core.telemetry import telemetry

logger = logging.getLogger("JARVIS.Executor")


# Metadata artık tool class'larında tanımlı (domain, latency_ms, reliability_score)
# Fallback zincirleri tools/tool_registry.py'de tanımlı (FALLBACK_CHAINS)


class Executor:
    """
    Tool çalıştırma ve fallback yönetim katmanı.

    engine.py ile uyumlu API:
        executor = Executor(brain, memory, config)

        result = await executor.execute_tool(
            protocol_tag="GOOGLE_SEARCH",
            argument="Python dersleri",
            engine_context={"last_whatsapp_num": None},
        )

        fallback = await executor.try_fallback(
            protocol_tag="YT_PLAY",
            argument="lofi beats",
            engine_context={},
        )

        await executor.cleanup()

    Attributes:
        registry:   ToolRegistry instance (tüm tool'lar burada kayıtlı)
        brain:      GroqBrain reference (tool'ların LLM erişimi gerekirse)
        memory:     MemoryManager reference (tool context'e eklenir)
        config:     EngineConfig reference
        _metadata:  Tool metadata cache
    """

    def __init__(
        self,
        brain: GroqBrain,
        memory: Optional[MemoryManager] = None,
        config: Optional[EngineConfig] = None,
    ) -> None:
        self.brain = brain
        self.memory = memory
        self.config = config or EngineConfig()

        # Tool Registry — tools/ paketi üzerinden
        self.registry: ToolRegistry = create_default_registry()

        logger.info(
            f"Executor başlatıldı: {self.registry.count} tool kayıtlı → "
            f"{self.registry.all_tags}"
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  EXECUTE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def execute_tool(
        self,
        protocol_tag: str,
        argument: str = "",
        engine_context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Belirtilen protocol_tag'e karşılık gelen tool'u bulur ve çalıştırır.

        Args:
            protocol_tag:   Tool'un protokol etiketi (ör: "GOOGLE_SEARCH")
            argument:       Tool'a geçilecek argüman (ör: "Python dersleri")
            engine_context: Engine tarafından sağlanan salt-okunur bağlam

        Returns:
            ToolResult — tool'un çalışma sonucu

        Raises:
            ToolExecutionError: Tool bulunamadı veya execute() exception fırlattı

        Edge Cases:
            - Bilinmeyen tag → Registry alias check → hala yoksa hata
            - Tool.execute() blocking ise → run_in_executor ile async sarılır
            - Tool None dönerse → ToolResult(success=False) üretilir
        """
        tool = self.registry.get_by_protocol(protocol_tag)

        if tool is None:
            msg = f"Bilinmeyen protokol: '{protocol_tag}'"
            logger.error(msg)
            raise ToolExecutionError(
                message=msg,
                tool_name=protocol_tag,
            )

        # Interpolation (Bağlam Aktarımı)
        interpolated_arg = self._interpolate_argument(argument, engine_context)

        # Parametre hazırlama — ilk parametre = argüman
        params = self._build_params(tool, interpolated_arg)
        ctx = engine_context or {}
        ctx["brain"] = self.brain  # [V9.0] Dosya özetleme için beyin referansını ekle

        # Pre-speak (uzun süren tool'lar için)
        if hasattr(tool, "pre_speak") and tool.pre_speak:
            logger.info(f"Tool pre_speak: {tool.pre_speak[:40]}...")

        # Execution
        start_time = time.monotonic()

        logger.info(
            f"Tool execute: {tool.name} "
            f"(tag={protocol_tag}, arg='{argument[:50]}', "
            f"domain={tool.domain}, "
            f"expected_latency={tool.latency_ms}ms)"
        )

        try:
            import asyncio
            # [V15.0] Tool-specific timeouts — fail-fast, deadlock prevention
            TOOL_TIMEOUTS = {
                "APP_OPEN":    20.0,
                "APP_KILL":    10.0,
                "FOLDER_OPEN": 8.0,
                "FILE_CREATE": 10.0,
                "FILE_WRITE":  10.0,
                "FILE_READ":   10.0,
                "FILE_DELETE": 10.0,
                "FILE_LATEST": 10.0,
                "WEB_OPEN":    45.0,
                "YT_PLAY":     45.0,
                "YT_SEARCH":   45.0,
                "GOOGLE_SEARCH": 45.0,
                "WEB_SEARCH":  90.0,
                "PYTHON_EXEC": 60.0,
            }
            timeout = TOOL_TIMEOUTS.get(protocol_tag, 30.0)
            result = await asyncio.wait_for(tool.execute(params, ctx), timeout=timeout)

            if result is None:
                result = ToolResult(
                    success=False,
                    verified=False,
                    message=f"{tool.name} None döndürdü.",
                )

            duration_ms = int((time.monotonic() - start_time) * 1000)
            result.execution_time_ms = duration_ms
            
            if not result.verified:
                result.success = False

        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(f"Tool timeout: {tool.name} (süre: {duration_ms}ms, limit={timeout}s)")
            return ToolResult(
                success=False,
                verified=False,
                error="Timeout",
                message=f"Görev zaman aşımına uğradı ({timeout:.0f}s limiti aşıldı)."
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            trace_id = engine_context.get("task_id", "unknown") if engine_context else "unknown"
            telemetry.log_tool_execution(
                trace_id=trace_id,
                tool_name=tool.protocol_tag,
                input_params=params,
                duration_ms=duration_ms,
                success=False,
                output="",
                error=str(e)
            )
            logger.error(
                f"Tool exception: {tool.name} → {e} "
                f"(süre: {duration_ms}ms)",
                exc_info=True,
            )
            raise ToolExecutionError(
                message=f"{tool.name} çalıştırılırken hata: {str(e)[:100]}",
                tool_name=tool.name,
                original_error=e,
            )

        trace_id = engine_context.get("task_id", "unknown") if engine_context else "unknown"
        
        telemetry.log_tool_execution(
            trace_id=trace_id,
            tool_name=tool.protocol_tag,
            input_params=params,
            duration_ms=duration_ms,
            success=result.success,
            output=result.message,
            error=""
        )

        logger.info(
            f"Tool result: {tool.name} → "
            f"success={result.success}, "
            f"duration={duration_ms}ms, "
            f"next_action={result.next_action or 'none'}"
        )

        return result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  FALLBACK
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def try_fallback(
        self,
        protocol_tag: str,
        argument: str = "",
        engine_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[ToolResult]:
        """
        Başarısız tool için fallback zincirinden alternatif dener.

        Fallback seçim mantığı:
            1. FALLBACK_CHAINS'den sıralı alternatifler alınır
            2. Her alternatif execute_tool() ile denenir
            3. İlk başarılı sonuç döndürülür
            4. Hiçbiri başarılı olmazsa None döner

        Args:
            protocol_tag:   Başarısız olan orijinal tool'un tag'i
            argument:       Orijinal argüman (fallback'e de aynısı verilir)
            engine_context: Salt-okunur engine bağlamı

        Returns:
            ToolResult: Başarılı fallback sonucu
            None:       Hiçbir fallback çalışmadı

        Edge Cases:
            - Fallback zinciri tanımlı değilse → None (sessiz)
            - Fallback tool da başarısız → zincirdeki sonraki denenrir
            - Fallback tool da exception → logla, sonrakine geç
        """
        fallback_tools = self.registry.get_fallback_chain(protocol_tag)

        if not fallback_tools:
            logger.info(
                f"Fallback zinciri yok: {protocol_tag}"
            )
            return None

        for fallback_tool in fallback_tools:
            fallback_tag = fallback_tool.protocol_tag
            logger.info(
                f"Fallback deneniyor: {protocol_tag} → {fallback_tag}"
            )
            try:
                result = await self.execute_tool(
                    protocol_tag=fallback_tag,
                    argument=argument,
                    engine_context=engine_context,
                )
                if result.success:
                    logger.info(
                        f"Fallback başarılı: {fallback_tag}"
                    )
                    return result
                else:
                    logger.warning(
                        f"Fallback başarısız: {fallback_tag} → {result.message}"
                    )
            except ToolExecutionError as e:
                logger.warning(
                    f"Fallback exception: {fallback_tag} → {e.message}"
                )
                continue

        logger.warning(
            f"Tüm fallback'ler başarısız: {protocol_tag} → {fallback_tools}"
        )
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  METADATA QUERY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_tool_metadata(self, protocol_tag: str) -> Dict[str, Any]:
        """
        Tool'un metadata'sını doğrudan tool class'ından okur.
        """
        tool = self.registry.get_by_protocol(protocol_tag)
        if tool:
            return {
                "domain": tool.domain,
                "latency_ms": tool.latency_ms,
                "reliability_score": tool.reliability_score,
            }
        return {}

    def get_best_tool_for_domain(self, domain: str) -> Optional[str]:
        """
        Registry üzerinden domain'de en iyi tool'u döndürür.
        """
        best = self.registry.get_best_tool(domain)
        return best.protocol_tag if best else None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  CLEANUP
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def cleanup(self) -> None:
        """
        Executor kaynakalarını temizler.
        engine.py shutdown sırasında çağırır.
        Playwright browser instance kapatılır.
        """
        try:
            from tools.browser_tool import BrowserManager
            await BrowserManager.close()
        except Exception as e:
            logger.warning(f"Browser cleanup hatası: {e}")
        logger.info("Executor cleanup tamamlandı.")

    @staticmethod
    def _interpolate_argument(argument: str, context: Optional[Dict[str, Any]]) -> str:
        """
        Argüman içindeki [PROTOCOL: TAG] yer tutucularını önceki adımların sonuçlarıyla değiştirir.
        """
        if not argument or not context or "step_results" not in context:
            return argument

        # [V8.2] Hem [PROTOCOL: TAG] hem de [STEP: TAG] formatını destekle
        pattern = r"\[(?:PROTOCOL|STEP):\s*(\w+)\]"
        results = context.get("step_results", {})

        def _replace(match):
            tag = match.group(1)
            # Eğer o tag ile bir sonuç varsa enjekte et, yoksa yer tutucuyu bırak
            return str(results.get(tag, match.group(0)))

        return re.sub(pattern, _replace, argument)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  INTERNAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _build_params(tool: BaseTool, argument: str) -> Dict[str, Any]:
        """
        [V15.0] Tool parametre şemasına göre argument → param dict.

        FILE_* tool'ları için özel eşleştirme:
          FILE_WRITE  → file_path_and_content: argument
          FILE_CREATE → file_path: argument
          FILE_READ   → file_path: argument
          FILE_DELETE → file_path: argument
          FOLDER_OPEN → folder_path: argument
          FILE_LATEST → dir_path: argument

        Diğer tool'lar: ilk parametre ismine argument.
        """
        if not tool.parameters:
            return {}

        argument = argument or ""

        # [V15.0] FILE tool'ları için kesin param isimleri
        FILE_PARAM_MAP = {
            "FILE_WRITE":  "file_path_and_content",
            "FILE_CREATE": "file_path",
            "FILE_READ":   "file_path",
            "FILE_DELETE": "file_path",
            "FOLDER_OPEN": "folder_path",
            "FILE_LATEST": "dir_path",
        }

        tag = tool.protocol_tag.upper()
        if tag in FILE_PARAM_MAP:
            return {FILE_PARAM_MAP[tag]: argument}

        first_param_name = next(iter(tool.parameters.keys()), None)
        if first_param_name:
            return {first_param_name: argument}
        return {}
