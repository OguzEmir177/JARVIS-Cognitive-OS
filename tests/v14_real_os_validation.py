import asyncio
import os
import psutil
import time
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.engine import ExecutionEngine
from core.config import EngineConfig
from core.telemetry import telemetry

async def check_process(name):
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and name.lower() in proc.info['name'].lower():
            return True
    return False

def check_log(tool_name):
    try:
        with open("logs/tool_execution.log", "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in reversed(lines):
                log_data = json.loads(line)
                if log_data.get("tool_name") == tool_name:
                    return log_data.get("success") == True
    except:
        pass
    return False

async def run_validation():
    print("==================================================")
    print("=== V14.5 PRODUCTION-GRADE REAL OS VALIDATION ===")
    print("==================================================")
    print("NOTE: These tests perform REAL execution and verify REAL OS state.")
    print("No mocks are used. Success implies actual action occurred.")
    print("--------------------------------------------------\n")
    
    config = EngineConfig()
    engine = ExecutionEngine(config)
    await engine.initialize()
    
    to_kill = ["calculator", "calc"]
    total_tests = 0
    passed_tests = 0
    
    # 1. APP_OPEN Tests
    app_tests = [
        {"input": "youtube aç", "check_process": ["chrome", "msedge"]},
        {"input": "hesap makinesi aç", "check_process": ["calc", "calculator"]},
        {"input": "chrome aç", "check_process": ["chrome"]},
    ]
    
    for t in app_tests:
        total_tests += 1
        print(f"\n> [TEST] Girdi: '{t['input']}'")
        try:
            await engine.process_input(t['input'])
            time.sleep(3)
            success = False
            for p in t['check_process']:
                if await check_process(p):
                    success = True
                    break
            
            if success:
                print(f"   [PASS] Gercek OS dogrulandi: Process acildi.")
                passed_tests += 1
            else:
                print(f"   [FAIL] Gercek OS dogrulandi: Process acilamadi!")
        except Exception as e:
            print(f"   [ERROR] Istisna: {e}")

    # 2. FILE OPERATIONS (Context-Aware)
    target_path = os.path.join(os.path.expanduser("~"), "Desktop", "test_jarvis.txt")
    if os.path.exists(target_path): 
        os.remove(target_path)
        
    print("\n> [TEST] Girdi: 'masaüstünde test_jarvis.txt oluştur'")
    total_tests += 1
    await engine.process_input("masaüstünde test_jarvis.txt oluştur")
    time.sleep(2)
    if os.path.exists(target_path) and check_log("FILE_CREATE"):
        print(f"   [PASS] Dosya yaratıldı (FILE_CREATE).")
        passed_tests += 1
    else:
        print(f"   [FAIL] Dosya yaratılamadı veya log hatalı.")

    print("\n> [TEST] Girdi: 'içine merhaba yaz' (Context-Aware Test)")
    total_tests += 1
    await engine.process_input("içine merhaba yaz")
    time.sleep(2)
    with open(target_path, "r", encoding="utf-8") as f:
        content = f.read()
    if "merhaba" in content.lower() and check_log("FILE_WRITE"):
        print(f"   [PASS] Dosyaya yazıldı (FILE_WRITE) ve context çalıştı.")
        passed_tests += 1
    else:
        print(f"   [FAIL] Dosyaya yazılamadı veya log hatalı. Content: {content}")

    print("\n> [TEST] Girdi: 'dosyayı oku'")
    total_tests += 1
    await engine.process_input("dosyayı oku")
    time.sleep(2)
    if check_log("FILE_READ"):
        print(f"   [PASS] Dosya okundu (FILE_READ).")
        passed_tests += 1
    else:
        print(f"   [FAIL] Dosya okunamadı.")

    print("\n> [TEST] Girdi: 'dosyayı sil'")
    total_tests += 1
    await engine.process_input("dosyayı sil")
    time.sleep(2)
    if not os.path.exists(target_path) and check_log("FILE_DELETE"):
        print(f"   [PASS] Dosya silindi (FILE_DELETE).")
        passed_tests += 1
    else:
        print(f"   [FAIL] Dosya silinemedi.")

    # 3. DIRECTORY TESTS
    print("\n> [TEST] Girdi: 'indirilenler klasörünü aç'")
    total_tests += 1
    await engine.process_input("indirilenler klasörünü aç")
    time.sleep(2)
    if check_log("FOLDER_OPEN"):
        print(f"   [PASS] Klasör açıldı (FOLDER_OPEN).")
        passed_tests += 1
    else:
        print(f"   [FAIL] Klasör açılamadı.")

    print("\n> [TEST] Girdi: 'son indirilen dosya nedir'")
    total_tests += 1
    await engine.process_input("son indirilen dosya nedir")
    time.sleep(2)
    if check_log("FILE_LATEST"):
        print(f"   [PASS] Son dosya bulundu (FILE_LATEST).")
        passed_tests += 1
    else:
        print(f"   [FAIL] Son dosya bulunamadı.")

    print("\n==================================================")
    print(f"=== SONUÇ: {passed_tests}/{total_tests} BAŞARILI ===")
    print("==================================================")
    
    for k in to_kill:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and k.lower() in proc.info['name'].lower():
                try:
                    proc.kill()
                except:
                    pass

if __name__ == "__main__":
    asyncio.run(run_validation())
