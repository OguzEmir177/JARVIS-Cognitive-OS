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
    profile = cm.get_profile("Görünmez Adam")
    assert profile["unknown"] is True
    assert profile["phone"] == ""

@pytest.mark.asyncio
async def test_whatsapp_tool_unknown_contact():
    tool = WhatsAppTool()
    
    # Mock resolve_phone_number
    tool._resolve_phone_number = lambda recipient: recipient
    
    result = await tool.execute({"target": "Görünmez Adam|selam"})
    assert result.success is False
    assert result.next_action == "REQUEST_CONTACT_NUMBER"
    assert "unknown_name" in result.data
    assert result.data["unknown_name"] == "Görünmez Adam"

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
                    "oluşturulan mesaj",
                    "[protocol: app_open] whatsapp",
                    "kullanıcı, bir seyler demek istiyorsa falan filan",
                    "kisa yazi",
                    "bu metin on bes kelimeden cok daha uzun olmali ki test basarili bir sekilde gecsin degil mi gercekten on bes kelimeyi astik"
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
    assert "1" in deleted # heijan var
    assert "2" in deleted # oluşturulan mesaj var
    assert "3" in deleted # [protocol: var
    assert "4" in deleted # kullanıcı, var (15 kelimeden kisa oldugu icin de silinir ama kural geregi bastan da yakalanmali)
    assert "5" in deleted # kisa yazi, 15 kelimeden az
    assert "6" not in deleted # normal, guvenli metin
