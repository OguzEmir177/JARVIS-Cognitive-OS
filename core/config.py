"""[V8.0] J.A.R.V.I.S. Centralized Configuration
━━━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━━
All timeout, retry and limit values are at one point.

Design Decision:
    Why dataclass and not .env?
    → Simplicity. Values ​​do not change at runtime, hardcoded defaults are sufficient.
    → .env loading may be added in the future (extensibility).
    → Groq free tier limits are fixed (30 req/min)."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# [V8.0] Load environment variables before application starts
load_dotenv()


def load_config() -> dict:
    """Loads environment variables and basic settings (legacy compatibility)."""
    load_dotenv()
    return {
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
        "ASSISTANT_NAME": "J.A.R.V.I.S.",
        "MASTER_NAME": "Oguz Emir",
    }


@dataclass
class EngineConfig:
    """ExecutionEngine configuration.

    All values are set according to Groq free tier limits:
        - 30 requests/minute
        - 6000 tokens/minute
        - 14,400 requests/day

    Attributes:
        max_queue_size: Max number of tasks that can wait simultaneously
        tool_timeout_seconds: Timeout for a single tool run
        max_replan_attempts: How many times to replan on failed step
        brain_connect_retries: How many times will the brain connection be tried?
        brain_timeout_seconds: Timeout of a single LLM call
        brain_models: Fallback model order (Groq model IDs)
        reflection_cooldown_s: Minimum time between two reflections
        max_task_retries: How many times a single task can be retried"""

    # ── Queue & Concurrency ──
    max_queue_size: int = 50

    # ── Timeout'lar ──
    tool_timeout_seconds: float = 30.0
    brain_timeout_seconds: float = 10.0

    # ── Retry Limitleri ──
    max_replan_attempts: int = 2
    brain_connect_retries: int = 5
    max_task_retries: int = 2

    # ── LLM Model Fallback Chain ──
    brain_models: list = field(default_factory=lambda: [
        "llama-3.3-70b-versatile", # Most advanced model (Llama 3.3)
        "llama-3.1-70b-versatile", # Powerful backup
        "llama-3.1-8b-instant"     # Fast fallback
    ])
    ping_model: str = None         # Fallback test model (if None, brain_models[0] is used)
    function_calling_enabled: bool = False  # [V9.7] Disabled: Forces LLM to generate [PLAN] text directly.

    # ── Reflection ──
    reflection_cooldown_s: float = 5.0

    # ── Storage & Paths ──
    memory_db_path: str = "./memory_db"
    log_dir: str = "./logs"
    log_level: str = "INFO"
