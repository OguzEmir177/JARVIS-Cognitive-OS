import sys, asyncio, logging, os
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')

from core.engine import ExecutionEngine
from core.config import EngineConfig
from pathlib import Path

desktop = Path(os.environ['USERPROFILE']) / 'Desktop'
target = desktop / 'jarvis_regression_test.txt'
if target.exists():
    target.unlink()

async def main():
    config = EngineConfig()
    engine = ExecutionEngine(config)
    await engine.initialize()
    engine.plan_executor.last_active_file = None

    print(f'Target: {target}')
    print('=== FILE_CREATE ===')
    await engine.process_input('masaüstünde jarvis_regression_test.txt oluştur')
    await asyncio.sleep(1)
    print(f'pe.last_active_file: {engine.plan_executor.last_active_file}')
    print(f'File exists: {target.exists()}')
    print()

    print('=== FILE_WRITE (explicit) ===')
    await engine.process_input('jarvis_regression_test.txt içine merhaba yaz')
    await asyncio.sleep(1)
    print(f'pe.last_active_file: {engine.plan_executor.last_active_file}')
    if target.exists():
        content = target.read_text(encoding='utf-8')
        print(f'File content: {repr(content)}')
    else:
        print('TARGET DOES NOT EXIST')

    await engine.shutdown()

asyncio.run(main())
