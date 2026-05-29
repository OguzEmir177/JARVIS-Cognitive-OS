import pytest
from core.contact_manager import ContactManager
from tools.system_tool import WhatsAppTool
from core.memory_consolidator import MemoryConsolidator

def test_contact_manager_unknown_profile():
    class DummyMemory:
        class Collection:
            def get(self, *args, **kwargs):
                return {"ids": [], "documents": []}
            def upsert(self, *args, **kwargs):
                pass
        def __init__(self):
            self.collection = self.Collection()
            
    cm = ContactManager(memory_manager=DummyMemory(), contacts_path="dummy.json")
    profile = cm.get_profile("Invisible Man")
    assert profile["unknown"] is True
    assert profile["phone"] == ""

@pytest.mark.asyncio
async def test_whatsapp_tool_unknown_contact():
    tool = WhatsAppTool()
    
    # Mock resolve_phone_number
    tool._resolve_phone_number = lambda recipient: recipient
    
    result = await tool.execute({"target": "Invisible Man|hi"})
    assert result.success is False
    assert result.next_action == "REQUEST_CONTACT_NUMBER"
    assert "unknown_name" in result.data
    assert result.data["unknown_name"] == "Invisible Man"

def test_memory_consolidator_clean():
    class DummyCollection:
        def __init__(self):
            self.deleted_ids = []
            
        def get(self, *args, **kwargs):
            return {
                "ids": ["1", "2", "3", "4", "5", "6"],
                "metadatas": [
                    {"importance": 1.0},
                    {"importance": 0.9},
                    {"importance": 0.5},
                    {"importance": 0.2},
                    {"importance": 0.5},
                    {"importance": 0.5}
                ],
                "documents": [
                    "heijan biz ablama",
                    "created message",
                    "[protocol: app_open] whatsapp",
                    "If the user wants to say something, etc.",
                    "kisa yazi",
                    "This text must be much longer than fifteen words so that the test can be passed successfully, right? We really exceeded fifteen words."
                ]
            }
            
        def delete(self, ids):
            self.deleted_ids.extend(ids)
            
    class DummyMemory:
        def __init__(self):
            self.collection = DummyCollection()
            
    mc = MemoryConsolidator(DummyMemory())
    mc.clean_corrupted_records()
    deleted = mc.memory.collection.deleted_ids
    assert "1" in deleted # there is heijan
    assert "2" in deleted # there is a message created
    assert "3" in deleted # [protocol: var
    assert "4" in deleted # users, var (it will be deleted because it is shorter than 15 words, but as per the rule, it must be caught from the beginning)
    assert "5" in deleted # kisa yazi, 15 kelimeden az
    assert "6" not in deleted # normal, guvenli metin
