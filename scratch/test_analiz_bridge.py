
import sys
import os
sys.path.append(os.getcwd())
import asyncio
from tools.analiz_pro_tool import AnalizProTool

async def test_bridge():
    tool = AnalizProTool()
    print("Executing AnalizProTool health check...")
    result = await tool.execute({"query": "bağlantı testi"})
    print(f"Success: {result.success}")
    print(f"Message: {result.message}")
    print(f"Speak: {result.speak}")

if __name__ == "__main__":
    asyncio.run(test_bridge())
