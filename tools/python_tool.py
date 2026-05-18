import sys
import io
import traceback
import logging
from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.PythonTool")

def _blocked_input(prompt=""):
    """input() yasak: J.A.R.V.I.S. ortamında kullanıcıdan girdi alınamaz."""
    raise NotImplementedError(
        "[SANDBOX KISITLAMASI] `input()` bu ortamda kullanılamaz. "
        "Kullanıcıdan girdi almak yerine, matematik işlemleri gibi araçları "
        "doğrudan sonucu hesaplayıp `print()` ile döndürecek şekilde yaz. "
        "Örnek: print(topla(5, 3)) → print(8)"
    )

class PythonExecutionTool(BaseTool):
    name = "python_execution"
    description = "Python kodu çalıştırır ve terminal çıktısını (print) döndürür. SADECE matematik, veri analizi, metin işleme veya karmaşık hesaplamalar gerektiğinde kullan. Normal sohbetler için KULLANMA."
    protocol_tag = "PYTHON_EXEC"
    domain = "system"
    latency_ms = 1000
    reliability_score = 0.95
    parameters = {"code": {"type": "string", "description": "Çalıştırılacak saf Python kodu (Markdown veya ``` olmadan). input() KULLANILMAZ, değerler sabit olmalı."}}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        code = params.get("code", "")
        if not code:
            return ToolResult(success=False, verified=False, error="NoCode", message="Çalıştırılacak kod bulunamadı.")

        # LLM bazen kodu ```python ... ``` tagleri arasına koyabilir, bunları temizle
        code = code.replace("```python", "").replace("```", "").strip()
        
        # LLM bazen [PROTOCOL: PYTHON_EXEC] veya [: PYTHON_EXEC] etiketlerini
        # kod bloğunun içine gömer — bunları temizle
        import re
        # Başta veya herhangi bir satırda gelen protokol etiketlerini sil
        code = re.sub(r'\[/?[A-Z_ :]+PYTHON_EXEC[^\]]*\]', '', code)
        # Genel protokol etiketlerini temizle: [PROTOCOL: ...] veya [/PROTOCOL: ...]
        code = re.sub(r'\[/?PROTOCOL[^\]]*\]', '', code)
        # Boş kalan satırları at ve yeniden birleştir
        code = "\n".join(line for line in code.splitlines() if line.strip()).strip()

        # Çıktıyı (print) yakalamak için stdout'u yönlendir
        old_stdout = sys.stdout
        redirected_output = io.StringIO()
        sys.stdout = redirected_output

        try:
            # Kodu J.A.R.V.I.S.'in kendi hafızasında (lokal) çalıştır
            # Önceki adımların sonuçlarını koda güvenli bir sözlük (dict) olarak enjekte et
            step_data = engine_context.get("step_results", {}) if engine_context else {}
            exec_globals = {
                "step_results": step_data,
                # [GÜVENLİ SANDBOX] input() çağrısını bloke ederek sistemi çökmekten koru
                "input": _blocked_input,
                "__builtins__": __builtins__,
            }
            
            exec(code, exec_globals)
            output = redirected_output.getvalue().strip()
            
            if not output:
                output = "Kod başarıyla çalıştı ancak ekrana (print) hiçbir şey yazdırmadı."
                
            return ToolResult(
                success=True, 
                verified=True, 
                message=f"Kod Çıktısı:\n{output}", 
                speak="Kod çalıştırıldı, sonucu yorumluyorum Efendim...",
                data={"output": output},
                next_action="PYTHON_INTERPRET"
            )
        except NotImplementedError as e:
            # input() sandbox hatası — LLM'e anlamlı bir mesaj dön
            logger.warning(f"[PythonExec] Sandbox ihlali (input() çağrısı): {e}")
            return ToolResult(
                success=False, 
                verified=False, 
                error="SandboxError", 
                message=f"HATA: {str(e)}\n\nÇözüm: Kodu input() olmadan, değerleri doğrudan yazarak yeniden üret.",
                speak="Efendim, yazdığım kodda input() kullandım. Bu ortamda yasak. Kodu düzeltiyorum."
            )
        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"[PythonExec] Kod Hatası:\n{error_msg}")
            return ToolResult(
                success=False, 
                verified=False, 
                error="ExecError", 
                message=f"Yazdığın kodda hata çıktı:\n{str(e)}\n\nTam hata:\n{error_msg}", 
                speak="Efendim, yazdığım kodda bir hata oluştu."
            )
        finally:
            # Stdout'u eski haline geri getir (Çok kritik, yoksa J.A.R.V.I.S. kör olur)
            sys.stdout = old_stdout

