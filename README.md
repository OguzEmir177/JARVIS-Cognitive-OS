# J.A.R.V.I.S. v8.0 — Autonomous Agent Architecture

J.A.R.V.I.S. (Just A Rather Very Intelligent System) is an autonomous, AI-driven assistant utilizing a completely asynchronous execution core.

J.A.R.V.I.S. v8.0 has evolved from a linear, command-based script into a fully autonomous, self-correcting agent capable of complex reasoning, episodic memory, and dynamic re-planning. 

## Architectural Overview

The v8.0 completely re-architects the system into decoupled, high-performance submodules centered around `asyncio`.

### 1. The Core Engine (`core/engine.py`)
The central orchestrator of the system. Instead of sequentially evaluating scripts, it manages an asynchronous `TaskQueue`. It dynamically handles sub-task execution, delegates tools to the `Executor`, and seamlessly integrates `LLM` decisions. 
- Features parallel execution tracking via `StateManager`.
- Non-blocking interactions using `asyncio.gather()`.
- Intelligent error recovery (`_replan` mechanisms).

### 2. Autonomous Planner (`core/planner.py` & Katman 0)
The planning mechanism features a completely rigid tree-based JSON engine.
- **Layer 0 (Tree Structure):** The LLM dynamically constructs goals, subtasks, and parameters in a strictly typed JSON format (`PlanNode`).
- **Layers 1-4 (Regex Fallback):** Backward compatibility for natural language plans to guarantee parsing success under any LLM output conditionally.

### 3. Tool System (`tools/`)
Tools are completely isolated into a stateless plugin architecture mapping specific intents/protocols to asynchronous operations via the `ToolRegistry`.
- `browser_tool.py`: Headless/Headed Playwright interactions for Google Search, YouTube, Web Open.
- `desktop_tool.py`: PyWinAuto-based local desktop bindings.
- `system_tool.py`: System/Hardware utilities including Vision module integrations.

### 4. Memory & Reflector (`core/memory.py` & `core/reflector.py`)
J.A.R.V.I.S. now features **Cognitive Memory** (Bilişsel Zeka).
- **Reflector:** After each action (or failure), the system reflects on what went wrong and what worked.
- **Episodic Memory:** Pushes successes, failures, task metrics, and logs to `ChromaDB` embeddings seamlessly matching contextual similar incidents for future tool usage.

## Dynamic Re-planning (Self-Healing)
If a step encounters a strict failure through the Tool System and all pre-configured fallback strategies fail, the `TaskQueue` is halted (`cancel_all`). The engine combines the `Reflector`'s fault analysis with the remaining plan, consulting the AI to produce an entirely new, adapted sub-plan—without user intervention.

## Testing & Stability
- 100% Async logic under `Python 3.11`.
- Fully tested End-to-End lifecycle (Plan → Execute → Fail → Reflect → Replan) ensuring Graceful Fallbacks.
- Global coverage targets ensuring logic nodes are immune to infinite loop collapses.

---
_J.A.R.V.I.S. is maintained as a proprietary local orchestration environment._
