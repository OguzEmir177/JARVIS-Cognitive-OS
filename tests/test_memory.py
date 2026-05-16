"""
[V8.0] J.A.R.V.I.S. Memory & Reflector Test Suite
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Testler:
    - Asynchronous Memory Manager (save_memory_async, retrieve_memory_async).
    - ChromaDB'nin mock edilmesi (Diske yazmayı önlemek için).
    - Core/Reflector.py'nin memory_manager.save_memory_async fonksiyonunu
      doğru argumentlerle çağırıp çağırmadığının testi.
"""

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
    """ChromaDB istemcisini mocklar, diske erişimi engeller."""
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
        """MemoryManager basarili olarak baslatilmali ve Chroma client'i cagirmali."""
        mem = MemoryManager(db_path=":memory:")
        mem.initialize()
        assert mem.collection is not None
        mock_chroma_client.assert_called_once()

    def test_save_memory_sync(self, mock_chroma_client):
        """Senkron save_memory başarılı şekilde veriyi eklemeli (metadata kontrolü)."""
        mem = MemoryManager(db_path=":memory:")
        mem.initialize()
        # Duplicate detection'ı atlamak için count 0 dönmeli
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
        """Asenkron save_memory_async fonksiyonu çağrısı doğrulaması."""
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
        """Asenkron retrieve_memory_async çağrısı doğrulaması."""
        mem = MemoryManager(db_path=":memory:")
        mem.initialize()
        
        results = await mem.retrieve_memory_async("test query", memory_type="episodic")
        # Bizim mock_collection.query return type'a göre 1 tane dönmeli
        assert len(results) == 1
        assert results[0]["id"] == "test-id"
        assert results[0]["text"] == "mocked result"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REFLECTOR TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestReflectorIntegration:
    @pytest.fixture
    def active_task(self):
        task = TaskState(id="t123", goal="Google'da araba modeli ara")
        task.tool_history.extend([
            {"tool": "GOOGLE_SEARCH", "success": True, "duration_ms": 1500},
            {"tool": "WEB_OPEN", "success": False, "duration_ms": 800}
        ])
        task.status = "completed"  # terminal hal
        return task

    @pytest.mark.asyncio
    async def test_reflector_saves_to_memory(self, active_task):
        """Reflector'ın _reflect işlemi başarılı olduğunda db kaydını (episodic memory) tetiklediğini test et."""
        # Mock Memory Manager
        mock_memory = MagicMock(spec=MemoryManager)
        mock_memory.save_memory_async = AsyncMock(return_value="mock_doc_id")

        reflector = Reflector(memory=mock_memory)
        
        reflection_result = await reflector.reflect(active_task)

        assert reflection_result is not None
        assert reflection_result["outcome"] == "partial"
        assert reflection_result["task_type"] == "web"
        assert "GOOGLE_SEARCH, WEB_OPEN" in reflection_result["tool_used"]

        # save_memory_async'in çağrılıp çağrılmadığını doğrula (1 kere)
        mock_memory.save_memory_async.assert_called_once()

        # Argümanları incele
        kwargs = mock_memory.save_memory_async.call_args[1]
        
        assert kwargs["memory_type"] == "episodic"
        assert "text" in kwargs
        assert "[NE YAPTIM]" in kwargs["text"]
        
        # İstenen Episodic Metadata'lar içinde mecut mu?
        metadata = kwargs["metadata"]
        assert metadata["task_id"] == "t123"
        assert metadata["task_type"] == "web"
        assert metadata["outcome"] == "partial"
        assert metadata["tool_used"] == "GOOGLE_SEARCH, WEB_OPEN"
        assert "reflection_summary" in metadata
        assert metadata["importance"] == 0.6

    @pytest.mark.asyncio
    async def test_reflector_ignores_non_terminal(self):
        """Bitmemiş görevlerde (non-terminal) reflection (yansıtma) çalışmamalı."""
        task = TaskState(id="t_running", goal="Test", status="running")
        reflector = Reflector()
        
        res = await reflector.reflect(task)
        assert res is None

    @pytest.mark.asyncio
    async def test_reflector_fallback_when_no_memory(self, active_task):
        """Memory modülü yoksa, Reflector sadece reflection dict dönmeli ve kilitlenmemeli (crash)."""
        reflector = Reflector(memory=None)
        res = await reflector.reflect(active_task)
        
        assert res is not None
        assert res["task_type"] == "web"
