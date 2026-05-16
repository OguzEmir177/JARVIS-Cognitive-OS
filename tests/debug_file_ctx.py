import sys
sys.path.insert(0, '.')
from tools.file_tool import FileCreateTool, FileWriteTool
from pathlib import Path
import os, asyncio

async def test():
    create_tool = FileCreateTool()
    write_tool = FileWriteTool()

    ctx = {}

    # FileCreate
    result = await create_tool.execute({'file_path': 'masaüstünde jarvis_regression_test.txt oluştur'}, ctx)
    laf = ctx.get("last_active_file")
    print("CREATE result:", result.success, result.message)
    print("last_active_file after CREATE:", laf)
    print()

    # FileWrite explicit
    result2 = await write_tool.execute({'file_path_and_content': 'jarvis_regression_test.txt icine merhaba yaz'}, ctx)
    print("WRITE result:", result2.success, result2.message)
    print("last_active_file after WRITE:", ctx.get("last_active_file"))

    # Dosya içeriği
    if laf:
        p = Path(laf)
        if p.exists():
            print("File content:", p.read_text(encoding='utf-8'))
        else:
            print("FILE DOES NOT EXIST:", p)

asyncio.run(test())
