"""
[V8.0] Shared Test Fixtures
━━━━━━━━━━━━━━━━━━━━━━━━━━━
pytest conftest — tüm testlerin kullandığı ortak mock'lar ve fixture'lar.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from core.config import EngineConfig
from core.state_manager import TaskState, StateManager
from core.task_queue import TaskQueue
from core.reflector import Reflector


@pytest.fixture
def engine_config():
    """Test için hızlı timeout'lu EngineConfig."""
    return EngineConfig(
        tool_timeout_seconds=5.0,
        brain_timeout_seconds=3.0,
        max_replan_attempts=1,
        brain_connect_retries=1,
        max_task_retries=1,
    )


@pytest.fixture
def state_manager():
    """Temiz bir StateManager instance."""
    return StateManager()


@pytest.fixture
def task_queue():
    """Temiz bir TaskQueue instance."""
    return TaskQueue(maxsize=10)


@pytest.fixture
def mock_brain(engine_config):
    """Mock GroqBrain — LLM çağrıları yapmaz. [V8.1 Hardened]"""
    from core.brain import GroqBrain
    brain = MagicMock(spec=GroqBrain)
    brain.think = AsyncMock(return_value="[PROTOCOL: GOOGLE_SEARCH] test")
    brain.check_connection = AsyncMock(return_value=True)
    brain.chat_history = [{"role": "system", "content": "..."}]
    brain.client = MagicMock()

    # Mock LLM response for reflection
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = "CONTINUE"
    brain.client.chat.completions.create = MagicMock(return_value=mock_completion)

    return brain


@pytest.fixture
def mock_memory():
    """Mock MemoryManager — [V8.1 Hardened]"""
    from core.memory import MemoryManager
    memory = MagicMock(spec=MemoryManager)
    memory.save_memory = MagicMock(return_value="mock-id")
    memory.retrieve_memory = MagicMock(return_value=[])
    memory.get_contacts = MagicMock(return_value={
        "Ablam": "+905551234567",
        "Annem": "+905559876543",
    })
    return memory


@pytest.fixture
def mock_tool_result():
    """Başarılı bir ToolResult mock'u."""
    # [V8.1 FIX] BUG #7: 'core.tools' path yanlıştı — asıl kaynak 'tools.base_tool'
    # Yanlış import isinstance() kontrollerini bozuyor ve test mock'larını production
    # kodundan koparıyordu.
    from tools.base_tool import ToolResult
    return ToolResult(
        success=True,
        message="İşlem başarılı.",
        speak="Başarıyla tamamlandı Efendim.",
    )


@pytest.fixture
def mock_tool_result_fail():
    """Başarısız bir ToolResult mock'u."""
    # [V8.1 FIX] BUG #7: Aynı düzeltme — tools.base_tool
    from tools.base_tool import ToolResult
    return ToolResult(
        success=False,
        message="Araç bulunamadı.",
        speak="Hata oluştu Efendim.",
    )


@pytest.fixture
def reflector(mock_memory, mock_brain):
    """Gerçek Reflector instance (mock bağımlılıklarla)."""
    return Reflector(memory=mock_memory, brain=mock_brain)


@pytest.fixture
def sample_task_state():
    """Tamamlanmış bir örnek TaskState."""
    import time
    ts = TaskState(
        id="test-001",
        goal="Google'da Python arat",
        status="completed",
        start_time=time.monotonic() - 2.0,
        end_time=time.monotonic(),
        tool_history=[
            {"tool": "GOOGLE_SEARCH", "success": True, "duration_ms": 1500},
        ],
    )
    return ts


@pytest.fixture
def failed_task_state():
    """Başarısız bir örnek TaskState."""
    import time
    ts = TaskState(
        id="test-002",
        goal="Discord'u kapat",
        status="failed",
        start_time=time.monotonic() - 3.0,
        end_time=time.monotonic(),
        last_error="Process bulunamadı",
        tool_history=[
            {"tool": "APP_KILL", "success": False, "duration_ms": 2000},
        ],
    )
    return ts
