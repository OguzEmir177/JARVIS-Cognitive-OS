"""
[V8.0] J.A.R.V.I.S. Base Tool & ToolResult
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tüm async tool'ların temel sınıfı ve standart çıktı yapısı.

Değişiklikler (core/tools.py'den farklar):
    - execute() → async def execute()
    - Zorunlu metadata: domain, latency_ms, reliability_score
    - to_schema() metadata alanlarını da export eder

Tasarım Kararı:
    Neden async execute()?
    → Playwright native async. Desktop/system tool'lar
      internal run_in_executor ile sarılır.
    → Executor tek bir await tool.execute() çağrısı yapar.
    → Uniform interface — hiçbir tool özel handling gerektirmez.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("JARVIS.Tools")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TOOL RESULT — Standart Araç Çıktısı
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class ToolResult:
    """
    Her tool execute()'dan bu nesneyi döndürür.
    """
    success: bool
    verified: bool = False
    message: str = ""
    error: Optional[str] = None
    execution_time_ms: int = 0
    speak: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    next_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success":           self.success,
            "verified":          self.verified,
            "message":           self.message,
            "error":             self.error,
            "execution_time_ms": self.execution_time_ms,
            "speak":             self.speak,
            "data":              self.data,
            "next_action":       self.next_action,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BASE TOOL — Async Soyut Temel Sınıf
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BaseTool(ABC):
    """
    Tüm J.A.R.V.I.S. v8.0 araçlarının temel sınıfı.

    Alt sınıflar şunları ZORUNLU tanımlamalı:
        - name:              Araç adı (benzersiz, snake_case)
        - description:       İnsan okunabilir açıklama
        - protocol_tag:      [PROTOCOL: X] etiketiyle eşleşme
        - parameters:        Parametre şemaları (JSON Schema benzeri dict)
        - domain:            "web" | "desktop" | "system"
        - latency_ms:        Tahmini gecikme (ms)
        - reliability_score: Güvenilirlik puanı (0.0-1.0)
        - execute():         async — işlemi gerçekleştiren metod

    Opsiyonel:
        - requires_interaction: Engine düzeyinde etkileşim gerektiren araçlar
        - pre_speak:            Execute öncesi TTS mesajı
    """

    name: str = ""
    description: str = ""
    protocol_tag: str = ""
    parameters: Dict[str, dict] = {}

    # ── ZORUNLU METADATA ──
    domain: str = "system"           # "web" | "desktop" | "system"
    latency_ms: int = 1000           # Tahmini ms
    reliability_score: float = 0.5   # 0.0 - 1.0

    # ── OPSIYONEL ──
    requires_interaction: bool = False
    pre_speak: str = ""

    @abstractmethod
    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        """
        Aracı asenkron olarak çalıştır.

        Args:
            params:         Tool'a özel parametreler
            engine_context: Engine tarafından salt-okunur bağlam

        Returns:
            ToolResult
        """
        pass

    def to_schema(self) -> dict:
        """
        Aracın tanımını LLM'in anlayacağı JSON Schema formatında dışa aktarır.
        Metadata alanları da dahil.
        """
        return {
            "name": self.name,
            "description": self.description,
            "protocol_tag": self.protocol_tag,
            "parameters": self.parameters,
            "requires_interaction": self.requires_interaction,
            "domain": self.domain,
            "latency_ms": self.latency_ms,
            "reliability_score": self.reliability_score,
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"tag={self.protocol_tag}, "
            f"domain={self.domain}, "
            f"reliability={self.reliability_score})"
        )


def _run_sync(func, *args):
    """
    Blocking fonksiyonu asyncio thread pool'da çalıştırmak için yardımcı.
    Desktop ve system tool'ları bu fonksiyonu kullanır.
    """
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, func, *args)
