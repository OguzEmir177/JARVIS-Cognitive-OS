"""[V8.0] J.A.R.V.I.S. Memory & Reflector Test Suite
━━━━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━━━━
Tests:
    - Asynchronous Memory Manager (save_memory_async, retrieve_memory_async).
    - Mocking ChromaDB (to avoid writing to disk).
    - Memory_manager.save_memory_async function of Core/Reflector.py
      Testing whether you call it with the right arguments."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from core.memory import MemoryManager
from core.reflector import Reflector
from core.state_manager import TaskState

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MEMORY MANAGER TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def mock_chroma_client():
    """Mocks the ChromaDB client, preventing disk access."""
    with patch("chromadb.PersistentClient") as mock_client:
        mock_collection = MagicMock()
        mock_client.return_value.get_or_create_collection.return_value = mock_collection
        
        # collection count varsayilan donusu
        mock_collection.count.return_value = 1
        
        # documentleri db'den okuma / duplicates search response for query
        mock_collection.query.return_value = {
            'documents': [["mocked result"]],
            'distances': [[0.1]],
            'metadatas': [[{"importance": 0.9, "timestamp": 0}]],
            'ids': [["test-id"]]
        }
        yield mock_client

class TestMemoryManager:
    def test_init_safe(self, mock_chroma_client):
        """MemoryManager should launch successfully and call the Chroma client."""
        mem = MemoryManager(db_path=":memory:")
        mem.initialize()
        assert mem.collection is not None
        mock_chroma_client.assert_called_once()

    def test_save_memory_sync(self, mock_chroma_client):
        """Synchronous save_memory should successfully add data (metadata check)."""
        mem = MemoryManager(db_path=":memory:")
        mem.initialize()
        # count should return 0 to bypass duplicate detection
        mem.collection.count.return_value = 0
        doc_id = mem.save_memory(
            text="J.A.R.V.I.S. completed a task",
            memory_type="episodic",
            metadata={"task_type": "web"}
        )
        assert doc_id is not None
        mem.collection.add.assert_called_once()
        
        call_args = mem.collection.add.call_args[1]
        assert "task_type" in call_args["metadatas"][0]
        assert call_args["metadatas"][0]["memory_type"] == "episodic"
        assert "importance" in call_args["metadatas"][0]

    @pytest.mark.asyncio
    async def test_save_memory_async(self, mock_chroma_client):
        """Asynchronous save_memory_async function call validation."""
        mem = MemoryManager(db_path=":memory:")
        mem.initialize()
        mem.collection.count.return_value = 0
        
        doc_id = await mem.save_memory_async(
            text="Async task execution",
            memory_type="episodic",
            metadata={"outcome": "success"}
        )
        assert doc_id is not None
        mem.collection.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_memory_async(self, mock_chroma_client):
        """Asynchronous retrieve_memory_async call validation."""
        mem = MemoryManager(db_path=":memory:")
        mem.initialize()
        
        results = await mem.retrieve_memory_async("test query", memory_type="episodic")
        # According to our mock_collection.query return type, it should return 1
        assert len(results) == 1
        assert results[0]["id"] == "test-id"
        assert results[0]["text"] == "mocked result"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REFLECTOR TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestReflectorIntegration:
    @pytest.fixture
    def active_task(self):
        task = TaskState(id="t123", goal="Search car model on Google")
        task.tool_history.extend([
            {"tool": "GOOGLE_SEARCH", "success": True, "duration_ms": 1500},
            {"tool": "WEB_OPEN", "success": False, "duration_ms": 800}
        ])
        task.status = "completed"  # terminal hal
        return task

    @pytest.mark.asyncio
    async def test_reflector_saves_to_memory(self, active_task):
        """Test that Reflector triggers db recording (episodic memory) when _reflect operation is successful."""
        # Mock Memory Manager
        mock_memory = MagicMock(spec=MemoryManager)
        mock_memory.save_memory_async = AsyncMock(return_value="mock_doc_id")

        reflector = Reflector(memory=mock_memory)
        
        reflection_result = await reflector.reflect(active_task)

        assert reflection_result is not None
        assert reflection_result["outcome"] == "partial"
        assert reflection_result["task_type"] == "web"
        assert "GOOGLE_SEARCH, WEB_OPEN" in reflection_result["tool_used"]

        # Verify if save_memory_async is called (1 time)
        mock_memory.save_memory_async.assert_called_once()

        # Examine the arguments
        kwargs = mock_memory.save_memory_async.call_args[1]
        
        assert kwargs["memory_type"] == "episodic"
        assert "text" in kwargs
        assert "[NE YAPTIM]" in kwargs["text"]
        
        # Is it included in the requested Episodic Metadata?
        metadata = kwargs["metadata"]
        assert metadata["task_id"] == "t123"
        assert metadata["task_type"] == "web"
        assert metadata["outcome"] == "partial"
        assert metadata["tool_used"] == "GOOGLE_SEARCH, WEB_OPEN"
        assert "reflection_summary" in metadata
        assert metadata["importance"] == 0.6

    @pytest.mark.asyncio
    async def test_reflector_ignores_non_terminal(self):
        """Reflection should not work on unfinished tasks (non-terminal)."""
        task = TaskState(id="t_running", goal="Test", status="running")
        reflector = Reflector()
        
        res = await reflector.reflect(task)
        assert res is None

    @pytest.mark.asyncio
    async def test_reflector_fallback_when_no_memory(self, active_task):
        """If there is no memory module, Reflector should only return the reflection dict and not crash."""
        reflector = Reflector(memory=None)
        res = await reflector.reflect(active_task)
        
        assert res is not None
        assert res["task_type"] == "web"
