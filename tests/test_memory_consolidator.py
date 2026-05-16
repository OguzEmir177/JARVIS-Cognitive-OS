import time
import pytest
from unittest.mock import MagicMock
from core.memory_consolidator import MemoryConsolidator

def test_consolidate():
    mock_memory = MagicMock()
    seven_days = 7 * 86400
    mock_memory.collection.get.return_value = {
        "ids": ["1", "2", "3"],
        "metadatas": [
            {"importance": 0.2, "timestamp": time.time() - seven_days - 100, "tool_used": "GOOGLE_SEARCH", "outcome": "success"},
            {"importance": 0.3, "timestamp": time.time() - seven_days - 100, "tool_used": "GOOGLE_SEARCH", "outcome": "success"},
            {"importance": 0.6, "timestamp": time.time() - seven_days - 100, "tool_used": "WHATSAPP", "outcome": "success"},
        ]
    }
    
    mac = MemoryConsolidator(mock_memory)
    mac.consolidate()
    
    mock_memory.collection.delete.assert_called_once_with(ids=["1", "2"])
    
    mock_memory.save_memory.assert_called_once()
    args, kwargs = mock_memory.save_memory.call_args
    assert "GOOGLE_SEARCH 2 kez kullanıldı, 2 başarılı 0 başarısız" in kwargs["text"]
    assert kwargs["memory_type"] == "semantic"
    assert kwargs["metadata"]["importance"] == 0.6

def test_prune_duplicates():
    mock_memory = MagicMock()
    mock_memory.collection.get.return_value = {
        "ids": ["1", "2", "3", "4"],
        "metadatas": [
            {"importance": 0.8, "timestamp": 1000000, "tool_used": "GOOGLE_SEARCH", "outcome": "success"},
            {"importance": 0.5, "timestamp": 1000000, "tool_used": "GOOGLE_SEARCH", "outcome": "success"},
            {"importance": 0.3, "timestamp": 1000000, "tool_used": "GOOGLE_SEARCH", "outcome": "success"},
            {"importance": 0.9, "timestamp": 1000000, "tool_used": "WHATSAPP", "outcome": "success"},
        ]
    }
    
    mac = MemoryConsolidator(mock_memory)
    mac.prune_duplicates()
    
    mock_memory.collection.delete.assert_called_once()
    deleted_ids = mock_memory.collection.delete.call_args[1]["ids"]
    assert set(deleted_ids) == {"2", "3"}

def test_get_stats():
    mock_memory = MagicMock()
    mock_memory.collection.count.return_value = 10
    mock_memory.collection.get.return_value = {
        "metadatas": [
            {"memory_type": "episodic", "timestamp": time.time() - 86400 * 2},
            {"memory_type": "pattern_rule", "timestamp": time.time() - 86400 * 5},
            {"memory_type": "semantic", "timestamp": time.time()}
        ]
    }
    
    mac = MemoryConsolidator(mock_memory)
    stats = mac.get_stats()
    
    assert stats["total_records"] == 10
    assert stats["episodic_count"] == 1
    assert stats["pattern_rules"] == 1
    assert 4.0 <= stats["oldest_record_days"] <= 6.0
