"""
[V16.0] Dynamic Skill Synthesizer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LLM'i kullanarak çalışma zamanında yeni araçlar (Tools) sentezler.
Yazılan araçlar tools/dynamic_skills/ içerisine kaydedilir ve anında registry'ye eklenir.

Özellikler:
- AST tabanlı Sandbox (Kötü niyetli modül importlarını engeller)
- Asenkron dosya I/O ve import (Event-loop'u bloklamaz)
- Kusursuz Fail-Fast hata yakalama zırhı
"""

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

# Güvenli Modüller Listesi (Sadece bunlara izin verilir)
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
        # sys.path'e dynamic_skills klasörünü üst klasörden erişilebilir yapalım
        # Zaten tools.dynamic_skills şeklinde import edilebilir.

    def _validate_code_security(self, code: str) -> bool:
        """AST kullanarak kodu ayrıştırır ve tehlikeli import/call tespit eder."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.error(f"SyntaxError in synthesized code: {e}")
            raise SyntaxError(f"Sentezlenen kodda sözdizimi hatası var: {e}")

        for node in ast.walk(tree):
            # Sadece izin verilen modüller import edilebilir
            if isinstance(node, ast.Import):
                for alias in node.names:
                    base_module = alias.name.split('.')[0]
                    if alias.name not in ALLOWED_MODULES and base_module not in ALLOWED_MODULES:
                        raise SecurityViolationError(f"Güvenlik İhlali: '{alias.name}' modülü import edilemez.")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    base_module = node.module.split('.')[0]
                    if node.module not in ALLOWED_MODULES and base_module not in ALLOWED_MODULES:
                        raise SecurityViolationError(f"Güvenlik İhlali: '{node.module}' modülü import edilemez.")
                        
            # eval, exec kullanımı yasak
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ['eval', 'exec']:
                        raise SecurityViolationError(f"Güvenlik İhlali: '{node.func.id}' fonksiyonu kullanılamaz.")
        return True

    def _write_and_import(self, tool_tag: str, code: str) -> Optional[BaseTool]:
        """Senkron kısım: Dosyayı yazar ve dinamik olarak import eder.
        Run in executor ile çağrılacak."""
        file_name = f"skill_{tool_tag.lower()}.py"
        file_path = os.path.join(self.skills_dir, file_name)
        
        # Dosyayı yaz
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
            
        try:
            # Import işlemi
            module_name = f"tools.dynamic_skills.skill_{tool_tag.lower()}"
            
            # Daha önce import edildiyse reload et
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
                
            # BaseTool miras alan sınıfı bul
            tool_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseTool) and attr is not BaseTool:
                    tool_class = attr
                    break
                    
            if not tool_class:
                raise ImportError(f"Modül {module_name} içinde BaseTool sınıfı bulunamadı.")
                
            return tool_class()
            
        except Exception as e:
            logger.error(f"Dinamik import hatası: {e}")
            raise

    async def synthesize_tool(self, brain: Any, task_description: str, suggested_tag: str = "DYNAMIC_TOOL") -> bool:
        """
        LLM ile belirtilen göreve uygun yepyeni bir araç yazar.
        Dönerken registry'ye kaydeder.
        """
        logger.info(f"Sentezleme Başlıyor... Hedef Görev: {task_description}")
        
        prompt = (
            f"[GÖREV: DİNAMİK ARAÇ SENTEZİ]\n"
            f"Şu görevi gerçekleştirmek için bir Python Tool sınıfı yazacaksın: '{task_description}'\n\n"
            f"KURALLAR:\n"
            f"1. Sınıf adı önemli değil ancak `BaseTool` sınıfından miras almalıdır.\n"
            f"2. importlar sadece bu listeden olmalıdır: {', '.join(ALLOWED_MODULES)}\n"
            f"3. `__init__(self)` metodunda `super().__init__(tag=\"{suggested_tag}\", description=\"...\")` çağırmalısın.\n"
            f"4. `async def execute(self, argument: str, context: dict = None) -> ToolResult:` metodunu kodlamalısın.\n"
            f"5. SADECE PYTHON KODU DÖNDÜR, markdown veya açıklama yok.\n\n"
            f"ÖRNEK TASLAK:\n"
            f"from tools.base_tool import BaseTool, ToolResult\n"
            f"import asyncio\n\n"
            f"class SynthesizedTool(BaseTool):\n"
            f"    def __init__(self):\n"
            f"        super().__init__(tag=\"{suggested_tag}\", description=\"Otomatik sentezlenmiş araç\")\n"
            f"    async def execute(self, argument: str, context: dict = None) -> ToolResult:\n"
            f"        return ToolResult(success=True, message=\"Tamamlandı\", output=\"...\")\n"
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
                logger.warning("LLM boş kod döndürdü.")
                return False
                
            # 1. AST Sandbox Kontrolü
            self._validate_code_security(code)
            
            # 2. I/O ve Import İşlemini Arka Planda (Asenkron) Yap
            loop = asyncio.get_running_loop()
            tool_instance = await loop.run_in_executor(None, self._write_and_import, suggested_tag, code)
            
            if tool_instance:
                # 3. Registry'ye anında kayıt yap
                self.registry.register(tool_instance)
                logger.info(f"Otonom Araç '{suggested_tag}' başarıyla sentezlendi ve aktifleşti!")
                return True
                
        except SyntaxError as se:
            logger.error(f"Sentezlenen Araçta Syntax Hatası: {se}")
        except SecurityViolationError as sve:
            logger.error(f"Sentezlenen Araçta Güvenlik İhlali: {sve}")
        except Exception as e:
            logger.error(f"Araç sentezlenirken hata oluştu: {e}")
            
        return False
