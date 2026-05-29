import asyncio
from core.brain import GroqBrain
from core.config import EngineConfig

async def main():
    brain = GroqBrain(EngineConfig())
    plan = await brain.think("Make me a calculator that can do addition, subtraction, multiplication and division.")
    print("PLAN OUTPUT:")
    print(plan)

asyncio.run(main())
