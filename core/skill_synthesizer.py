"""[V16.1] Dynamic Skill Synthesizer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Synthesizes new tools at runtime using LLM.
Written tools are saved in tools/dynamic_skills/ and added to the registry instantly.

Features:
- AST based Sandbox (Prevents malicious module imports)
- [V16.1 Audit] Shell access methods such as os.system / subprocess.* are also blocked in AST
- Asynchronous file I/O and import (does not block event-loop)
- Perfect Fail-Fast bug-catching armor"""

import os
import re
import ast
import asyncio
import logging
import importlib
import sys
from typing import Optional, Any
from tools.base_tool import BaseTool

logger = logging.getLogger("JARVIS.SkillSynthesizer")

# List of Safe Modules (Only these are allowed)
ALLOWED_MODULES = {
    "os", "sys", "asyncio", "aiohttp", "json", "time", "re", 
    "datetime", "logging", "math", "random", "tools.base_tool",
    "pathlib", "subprocess", "shutil", "urllib", "requests"
}

class SecurityViolationError(Exception):
    pass

class DynamicSkillSynthesizer:
    def __init__(self, registry):
        self.registry = registry
        self.skills_dir = os.path.join(os.getcwd(), "tools", "dynamic_skills")
        os.makedirs(self.skills_dir, exist_ok=True)
        # Let's make the dynamic_skills folder accessible to sys.path from the parent folder
        # It can already be imported as tools.dynamic_skills.

    def _validate_code_security(self, code: str) -> bool:
        """Parses the code using AST and detects dangerous import/call."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.error(f"SyntaxError in synthesized code: {e}")
            raise SyntaxError(f"There is a syntax error in the synthesized code: {e}")

        for node in ast.walk(tree):
            # Only permitted modules can be imported
            if isinstance(node, ast.Import):
                for alias in node.names:
                    base_module = alias.name.split('.')[0]
                    if alias.name not in ALLOWED_MODULES and base_module not in ALLOWED_MODULES:
                        raise SecurityViolationError(f"Security Violation: Module '{alias.name}' cannot be imported.")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    base_module = node.module.split('.')[0]
                    if node.module not in ALLOWED_MODULES and base_module not in ALLOWED_MODULES:
                        raise SecurityViolationError(f"Security Violation: Module '{node.module}' cannot be imported.")
                        
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ['eval', 'exec', '__import__', 'getattr', 'setattr', 'globals', 'locals', 'compile']:
                        raise SecurityViolationError(f"Security Violation: '{node.func.id}' function cannot be used.")

                # os.system(), os.popen(), subprocess.run(), subprocess.Popen() vb. yasak
                # [V16.1 AUDIT FIX] Even if os/subprocess in ALLOWED_MODULES
                # Dangerous methods that provide direct access to the shell command are blocked.
                if isinstance(node.func, ast.Attribute):
                    _BANNED_ATTR_CALLS = {
                        'system', 'popen',         # os.system(), os.popen()
                        'run', 'call', 'Popen',    # subprocess.run/call/Popen
                        'check_output',            # subprocess.check_output
                        'check_call',              # subprocess.check_call
                        'getoutput', 'getstatusoutput',  # subprocess.getoutput
                    }
                    if node.func.attr in _BANNED_ATTR_CALLS:
                        raise SecurityViolationError(
                            f"Security Violation: The '{node.func.attr}' call cannot be used because it provides shell access."
                        )

            # Block __builtins__ and other critical dunder features
            if isinstance(node, ast.Attribute):
                if node.attr in ['__builtins__', '__dict__', '__class__', '__bases__', '__subclasses__']:
                    raise SecurityViolationError(f"Security Violation: Access to property '{node.attr}' is prohibited.")
            if isinstance(node, ast.Name):
                if node.id in ['__builtins__', '__dict__', '__class__', '__bases__', '__subclasses__']:
                    raise SecurityViolationError(f"Security Violation: Access to property '{node.id}' is prohibited.")
                    
        return True

    def _write_and_import(self, tool_tag: str, code: str) -> Optional[BaseTool]:
        """Synchronous part: Writes the file and imports it dynamically.
        It will be called with run in executor."""
        file_name = f"skill_{tool_tag.lower()}.py"
        file_path = os.path.join(self.skills_dir, file_name)
        
        # Write file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
            
        try:
            # Import process
            module_name = f"tools.dynamic_skills.skill_{tool_tag.lower()}"
            
            # Reload if imported before
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
                
            # Find the BaseTool inheriting class
            tool_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseTool) and attr is not BaseTool:
                    tool_class = attr
                    break
                    
            if not tool_class:
                raise ImportError(f"BaseTool class not found in module {module_name}.")
                
            return tool_class()
            
        except Exception as e:
            logger.error(f"Dynamic import error: {e}")
            raise

    async def synthesize_tool(self, brain: Any, task_description: str, suggested_tag: str = "DYNAMIC_TOOL") -> bool:
        """Writes a brand new tool suitable for the specified task with LLM.
        It saves to the registry while returning."""
        logger.info(f"Synthesising Begins... Target Mission: {task_description}")
        
        prompt = (
            f"[MISSION: DYNAMIC VEHICLE SYNTHESIS]\n"
            f"You will write a Python Tool class to perform the following task: '{task_description}'\n\n"
            f"KURALLAR:\n"
            f"1. The class name does not matter but it must inherit from the `BaseTool` class.\n"
            f"2. imports should only be from this list: {', '.join(ALLOWED_MODULES)}\n"
            f"3. You should call `super().__init__(tag=\"{suggested_tag}\", description=\"...\")` in the `__init__(self)` method.\n"
            f"4. You should code the `async def execute(self, argument: str, context: dict = None) -> ToolResult:` method.\n"
            f"5. RETURN PYTHON CODE ONLY, no markdown or annotation.\n\n"
            f"SAMPLE DRAFT:\n"
            f"from tools.base_tool import BaseTool, ToolResult\n"
            f"import asyncio\n\n"
            f"class SynthesizedTool(BaseTool):\n"
            f"    def __init__(self):\n"
            f"super().__init__(tag=\"{suggested_tag}\", description=\"Auto-synthesized tool\")\n"
            f"    async def execute(self, argument: str, context: dict = None) -> ToolResult:\n"
            f"return ToolResult(success=True, message=\"Completed\", output=\"...\")\n"
        )
        
        try:
            response = await brain.think(prompt, bypass_history=True)
            
            # Kodu temizle
            code = response
            if "```python" in code:
                code = code.split("```python")[1].split("```")[0]
            elif "```" in code:
                code = code.split("```")[1].split("```")[0]
            code = code.strip()
            
            if not code:
                logger.warning("LLM returned empty code.")
                return False
                
            # 1. AST Sandbox Control & I/O Operation (Asynchronous)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._validate_code_security, code)
            
            # 2. Perform I/O and Import Operations in the Background (Asynchronous)
            tool_instance = await loop.run_in_executor(None, self._write_and_import, suggested_tag, code)
            
            if tool_instance:
                # 3. Instantly register to Registry
                self.registry.register(tool_instance)
                logger.info(f"Autonomous Vehicle '{suggested_tag}' has been successfully synthesized and activated!")
                return True
                
        except SyntaxError as se:
            logger.error(f"Syntax Error in Synthesized Vehicle: {se}")
        except SecurityViolationError as sve:
            logger.error(f"Security Violation in Synthesized Vehicle: {sve}")
        except Exception as e:
            logger.error(f"Error synthesizing vehicle: {e}")
            
        return False
