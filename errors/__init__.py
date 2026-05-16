"""
[V8.0] J.A.R.V.I.S. Error Taxonomy
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Typed exception hierarchy for structured error handling.

Her hata türü bir recovery stratejisine eşlenir:
    ToolExecutionError  → retry + fallback tool
    PlanParseError      → replan (LLM'den yeni plan iste)
    ProtocolParseError  → fallback parser katmanı
    EnvironmentError    → retry + kullanıcı bildirimi

Tasarım Kararı:
    Neden tek base class?
    → Tüm J.A.R.V.I.S. hataları JarvisError'dan türer.
      Engine tek bir except JarvisError ile yakalayabilir,
      ama isinstance() ile stratejiye yönlendirebilir.
    → Python stdlib Exception hierarchy'si korunur.
"""

from typing import Optional


class JarvisError(Exception):
    """
    Tüm J.A.R.V.I.S. hatalarının base class'ı.

    Attributes:
        message:         İnsan okunabilir hata mesajı
        recovery_hint:   Önerilen recovery stratejisi
        retry_allowed:   Bu hata için retry yapılabilir mi?
        original_error:  Sarmalanan orijinal exception (varsa)
    """

    def __init__(
        self,
        message: str,
        recovery_hint: str = "none",
        retry_allowed: bool = False,
        original_error: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.recovery_hint = recovery_hint
        self.retry_allowed = retry_allowed
        self.original_error = original_error

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"msg='{self.message[:60]}', "
            f"recovery='{self.recovery_hint}', "
            f"retry={self.retry_allowed})"
        )


class ToolExecutionError(JarvisError):
    """
    Tool çalıştırma sırasında oluşan hatalar.

    Recovery: retry (aynı tool) → fallback (alternatif tool)

    Edge Cases:
        - Playwright browser crash → retry_allowed=True
        - pywinauto ElementNotFound → fallback tool dene
        - Tool timeout → retry_allowed=False (zaten beklendi)
    """

    def __init__(
        self,
        message: str,
        tool_name: str = "",
        original_error: Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message=message,
            recovery_hint="retry_then_fallback",
            retry_allowed=True,
            original_error=original_error,
        )
        self.tool_name = tool_name


class PlanParseError(JarvisError):
    """
    LLM çıktısından plan parse edilemediğinde.

    Recovery: replan (LLM'den düzeltilmiş plan iste)

    Edge Cases:
        - Boş LLM yanıtı → replan
        - Geçersiz JSON + tüm katmanlar fail → replan
        - Replan limiti aşıldı → kullanıcıya bildir
    """

    def __init__(
        self,
        message: str,
        raw_response: str = "",
        original_error: Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message=message,
            recovery_hint="replan",
            retry_allowed=False,
            original_error=original_error,
        )
        self.raw_response = raw_response


class ProtocolParseError(JarvisError):
    """
    Tek bir [PROTOCOL: X] etiketi parse edilemediğinde.

    Recovery: fallback parser katmanı (daha esnek regex)

    Edge Cases:
        - LLM'in uydurduğu bilinmeyen tag → ToolRegistry alias check
        - Tag var ama argüman yok → boş argümanla devam et
    """

    def __init__(
        self,
        message: str,
        raw_line: str = "",
    ) -> None:
        super().__init__(
            message=message,
            recovery_hint="fallback_parser",
            retry_allowed=False,
        )
        self.raw_line = raw_line


class EnvironmentError(JarvisError):
    """
    Sistem/ağ düzeyinde hatalar.

    Recovery: retry (bağlantı) + kullanıcı bildirimi

    Edge Cases:
        - Groq API unreachable → retry with backoff
        - ChromaDB disk full → kullanıcıya bildir
        - Playwright browser binary missing → kurulum talimatı
    """

    def __init__(
        self,
        message: str,
        original_error: Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message=message,
            recovery_hint="retry_with_notification",
            retry_allowed=True,
            original_error=original_error,
        )
