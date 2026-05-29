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

    # Create
    await engine.process_input('create jarvis_regression_test.txt on desktop')
    await asyncio.sleep(1)
    print(f'After CREATE: pe.laf={engine.plan_executor.last_active_file}, exists={target.exists()}')

    # Write
    await engine.process_input('Type hello in jarvis_regression_test.txt')
    await asyncio.sleep(1)
    print(f'After WRITE: pe.laf={engine.plan_executor.last_active_file}')

    # Delete
    print(f'Before DELETE: target exists={target.exists()}')
    await engine.process_input('delete file')
    await asyncio.sleep(1)
    print(f'After DELETE: target exists={target.exists()}')
    print(f'After DELETE: pe.laf={engine.plan_executor.last_active_file}')

    await engine.shutdown()

asyncio.run(main())
