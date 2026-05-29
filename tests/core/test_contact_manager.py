import os
import json
import tempfile
import pytest
from unittest.mock import MagicMock

from core.contact_manager import ContactManager, CONTACT_ID_PREFIX

@pytest.fixture
def mock_memory():
    # ChromaDB koleksiyonunu taklit eden mock objesi
    memory = MagicMock()
    
    # Internal state for mock collection
    memory.storage = {}
    
    def upsert(ids, documents, metadatas=None):
        metadatas = metadatas or [None]*len(ids)
        for idx, doc, meta in zip(ids, documents, metadatas):
            memory.storage[idx] = {"document": doc, "metadata": meta}
            
    def get(ids=None, where=None, include=None):
        include = include or []
        if ids:
            docs, returned_ids = [], []
            for idx in ids:
                if idx in memory.storage:
                    returned_ids.append(idx)
                    docs.append(memory.storage[idx]["document"])
                else:
                    docs.append(None)
            return {"ids": returned_ids, "documents": docs if "documents" in include else None}
        elif where:
            returned_ids = [k for k, v in memory.storage.items() if v["metadata"] and v["metadata"].get("type") == where.get("type")]
            return {"ids": returned_ids, "documents": None}
        return {"ids": [], "documents": []}
            
    memory.collection.upsert.side_effect = upsert
    memory.collection.get.side_effect = get
    
    return memory

@pytest.fixture
def contacts_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, 'w', encoding="utf-8") as f:
        json.dump({"Alice": "12345", "Bob": "67890"}, f)
    yield path
    os.remove(path)

def test_initialize_idempotent_migration(mock_memory, contacts_file):
    manager = ContactManager(mock_memory, contacts_path=contacts_file)
    
    # First run -> 2 people must be added
    manager.initialize()
    assert len(mock_memory.storage) == 2
    assert f"{CONTACT_ID_PREFIX}Alice" in mock_memory.storage
    assert f"{CONTACT_ID_PREFIX}Bob" in mock_memory.storage
    
    # updating contacts.json (adding new contact)
    with open(contacts_file, "w", encoding="utf-8") as f:
        json.dump({"Alice": "12345", "Bob": "67890", "Charlie": "11111"}, f)
        
    # Second run -> Only Charlie should be added, old records should be skipped
    manager.initialize()
    assert len(mock_memory.storage) == 3
    assert f"{CONTACT_ID_PREFIX}Charlie" in mock_memory.storage
    
def test_get_profile_fallback_to_json(mock_memory, contacts_file):
    manager = ContactManager(mock_memory, contacts_path=contacts_file)
    
    # Initially, ChromaDB is empty (storage is empty) and cache is empty
    assert len(mock_memory.storage) == 0
    
    # When Alice is called -> Must be found from JSON and written to ChromaDB
    profile = manager.get_profile("Alice")
    assert profile["name"] == "Alice"
    assert profile["phone"] == "12345"
    
    # Let's check if it is saved to ChromaDB
    assert f"{CONTACT_ID_PREFIX}Alice" in mock_memory.storage
    saved_doc = json.loads(mock_memory.storage[f"{CONTACT_ID_PREFIX}Alice"]["document"])
    assert saved_doc["name"] == "Alice"
    
    # Also, let's check if it has been written to the cache.
    assert "Alice" in manager._cache

def test_initialize_skips_when_no_json(mock_memory):
    manager = ContactManager(mock_memory, contacts_path="non_existent.json")
    manager.initialize()
    assert len(mock_memory.storage) == 0

def test_update_after_message(mock_memory, contacts_file):
    manager = ContactManager(mock_memory, contacts_path=contacts_file)
    manager.update_after_message("Bob", "Hello there!", success=True)
    
    # When successful, Bob should be saved in ChromaDB with _upsert_profile
    assert f"{CONTACT_ID_PREFIX}Bob" in mock_memory.storage
    saved_doc = json.loads(mock_memory.storage[f"{CONTACT_ID_PREFIX}Bob"]["document"])
    
    assert saved_doc["message_count"] == 1
    assert len(saved_doc["last_topics"]) == 1
    assert "Hello there!" in saved_doc["last_topics"]
