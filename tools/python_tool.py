import sys
import io
import traceback
import logging
from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.PythonTool")

def _blocked_input(prompt=""):
    """input() forbidden: J.A.R.V.I.S. Input cannot be received from the user in the environment."""
    raise NotImplementedError(
        "[SANDBOX RESTRICTION] `input()` cannot be used in this environment."
        "Instead of taking input from the user, it uses tools such as mathematical operations."
        "Write it in a way that directly calculates the result and returns it with `print()`."
        "Example: print(sum(5, 3)) → print(8)"
    )

class PythonExecutionTool(BaseTool):
    name = "python_execution"
    description = "Python runs the code and returns terminal output (print). Use ONLY when math, data analysis, text processing, or complex calculations are required. DO NOT USE for normal chats."
    protocol_tag = "PYTHON_EXEC"
    domain = "system"
    latency_ms = 1000
    reliability_score = 0.95
    parameters = {"code": {"type": "string", "description": "Pure Python code to run (without Markdown or ```). input() CANNOT be used, values ​​must be constants."}}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        code = params.get("code", "")
        if not code:
            return ToolResult(success=False, verified=False, error="NoCode", message="Couldn't find code to run.")

        # LLM can sometimes put code between ```python...`` tags, clean them up
        code = code.replace("```python", "").replace("```", "").strip()
        
        # LLM bazen [PROTOCOL: PYTHON_EXEC] veya [: PYTHON_EXEC] etiketlerini
        # embeds inside code block — clear them
        import re
        # Delete leading protocol tags or any line
        code = re.sub(r'\[/?[A-Z_ :]+PYTHON_EXEC[^\]]*\]', '', code)
        # Genel protokol etiketlerini temizle: [PROTOCOL: ...] veya [/PROTOCOL: ...]
        code = re.sub(r'\[/?PROTOCOL[^\]]*\]', '', code)
        # Discard empty lines and recombine
        code = "\n".join(line for line in code.splitlines() if line.strip()).strip()

        # Redirect stdout to capture output (print)
        old_stdout = sys.stdout
        redirected_output = io.StringIO()
        sys.stdout = redirected_output

        try:
            # Run the code in J.A.R.V.I.S.'s own memory (local)
            # Inject the results of previous steps into the code as a safe dictionary (dict)
            step_data = engine_context.get("step_results", {}) if engine_context else {}
            exec_globals = {
                "step_results": step_data,
                # [SAFE SANDBOX] Protect system from crash by blocking input() call
                "input": _blocked_input,
                "__builtins__": __builtins__,
            }
            
            exec(code, exec_globals)
            output = redirected_output.getvalue().strip()
            
            if not output:
                output = "The code ran successfully but did not print anything to the screen."
                
            return ToolResult(
                success=True, 
                verified=True, 
                message=f"Code Output:\n{output}", 
                speak="The code has been run, I am interpreting the result, Sir...",
                data={"output": output},
                next_action="PYTHON_INTERPRET"
            )
        except NotImplementedError as e:
            # input() sandbox error — return a meaningful message to LLM
            logger.warning(f"[PythonExec] Sandbox violation (input() call): {e}")
            return ToolResult(
                success=False, 
                verified=False, 
                error="SandboxError", 
                message=f"ERROR: {str(e)}\n\nSolution: Regenerate the code without input(), by writing the values ​​directly.",
                speak="Sir, I used input() in the code I wrote. It is prohibited in this environment. I'm fixing the code."
            )
        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"[PythonExec] Code Error:\n{error_msg}")
            return ToolResult(
                success=False, 
                verified=False, 
                error="ExecError", 
                message=f"There was an error in the code you wrote:\n{str(e)}\n\nExact error:\n{error_msg}", 
                speak="Sir, there was an error in the code I wrote."
            )
        finally:
            # Reset stdout (Very critical or J.A.R.V.I.S. will go blind)
            sys.stdout = old_stdout

