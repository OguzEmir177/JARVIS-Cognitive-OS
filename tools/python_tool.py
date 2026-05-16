import sys
import io
import traceback
import logging
from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.PythonTool")

class PythonExecutionTool(BaseTool):
    name = "python_execution"
    description = "Python kodu çalıştırır ve terminal çıktısını (print) döndürür. SADECE matematik, veri analizi, metin işleme veya karmaşık hesaplamalar gerektiğinde kullan. Normal sohbetler için KULLANMA."
    protocol_tag = "PYTHON_EXEC"
    domain = "system"
    latency_ms = 1000
    reliability_score = 0.95
    parameters = {"code": {"type": "string", "description": "Çalıştırılacak saf Python kodu (Markdown veya ``` olmadan)"}}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        code = params.get("code", "")
        if not code:
            return ToolResult(success=False, verified=False, error="NoCode", message="Çalıştırılacak kod bulunamadı.")

        # LLM bazen kodu ```python ... ``` tagleri arasına koyabilir, bunları temizle
        code = code.replace("```python", "").replace("```", "").strip()

        # Çıktıyı (print) yakalamak için stdout'u yönlendir
        old_stdout = sys.stdout
        redirected_output = io.StringIO()
        sys.stdout = redirected_output

        try:
            # Kodu J.A.R.V.I.S.'in kendi hafızasında (lokal) çalıştır
            # Önceki adımların sonuçlarını koda güvenli bir sözlük (dict) olarak enjekte et
            step_data = engine_context.get("step_results", {}) if engine_context else {}
            exec_globals = {"step_results": step_data}
            
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
        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"[PythonExec] Kod Hatası:\n{error_msg}")
            return ToolResult(
                success=False, 
                verified=False, 
                error="ExecError", 
                message=f"Yazdığın kodda hata çıktı:\n{str(e)}", 
                speak="Efendim, yazdığım kodda bir hata oluştu."
            )
        finally:
            # Stdout'u eski haline geri getir (Çok kritik, yoksa J.A.R.V.I.S. kör olur)
            sys.stdout = old_stdout
