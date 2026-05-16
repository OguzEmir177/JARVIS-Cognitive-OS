import pytest
from unittest.mock import MagicMock
from core.pattern_extractor import PatternExtractor

@pytest.fixture
def mock_memory():
    memory = MagicMock()
    # Mock collection
    memory.collection = MagicMock()
    return memory

def test_extract_patterns_creates_rule(mock_memory):
    # Setup mock data for 2 failed APP_OPEN discord calls
    # side_effect listesi: 
    #   1. get() çağrısı: episodic çekimi (extract_patterns listeleme için)
    #   2. get() çağrısı: kural zaten var mı diye kontrol çekimi (already_exists)
    mock_memory.collection.get.side_effect = [
        # First call (episodic listesi)
        {
            "documents": [
                "Görev: APP_OPEN discord. Sonuç: failure. Hata: uygulama bulunamadı.",
                "Görev: APP_OPEN discord. Sonuç: failure. Hata: beklenmeyen hata.",
                "Görev: WEB_OPEN google.com. Sonuç: success" # Should ignore success
            ],
            "metadatas": [
                {"outcome": "failure", "tool_used": "APP_OPEN", "memory_type": "episodic"},
                {"outcome": "failure", "tool_used": "APP_OPEN", "memory_type": "episodic"},
                {"outcome": "success", "tool_used": "WEB_OPEN", "memory_type": "episodic"}
            ]
        },
        # Second call (hali hazırda rules kontrolü)
        {
            "documents": [],
            "metadatas": []
        }
    ]

    extractor = PatternExtractor(memory=mock_memory)
    extractor.extract_patterns()

    # extract_patterns, doc'tan "discord" hedef olarak çıkarıp len=2 failed bulduktan sonra 
    # rule oluşturmalı ve self.save_pattern() ile kaydetmeli.
    expected_rule = "APP_OPEN ile 'discord' açma 2 kez başarısız oldu. Alternatif: WEB_OPEN discord.com"
    
    mock_memory.save_memory.assert_called_once()
    args, kwargs = mock_memory.save_memory.call_args
    # 1. parametre kural test, 2. parametre "pattern_rule", 3. parametre metadata olmalı
    assert expected_rule == args[0]
    assert args[1] == "pattern_rule"
    
    metadata = args[2] if len(args) > 2 else kwargs.get("metadata")
    assert metadata["auto_generated"] is True
    assert metadata["importance"] == 0.95

def test_extract_patterns_no_duplicate_rule(mock_memory):
    # Setup mock data (Kural önceden öğrenilmişse tekrar öğrenmemeli)
    mock_memory.collection.get.side_effect = [
        # İlk episodic araması
        {
            "documents": [
                "Görev: APP_OPEN spotify. Sonuç: failure.",
                "Görev: APP_OPEN spotify. Sonuç: failure."
            ],
            "metadatas": [
                {"outcome": "failure", "tool_used": "APP_OPEN"},
                {"outcome": "failure", "tool_used": "APP_OPEN"}
            ]
        },
        # İkinci rule araması: zatan var olduğunu varsayalım
        {
            "documents": [
                "APP_OPEN ile 'spotify' açma 2 kez başarısız oldu. Alternatif: WEB_OPEN spotify.com"
            ],
            "metadatas": [{"memory_type": "pattern_rule", "importance": 0.95}]
        }
    ]

    extractor = PatternExtractor(memory=mock_memory)
    extractor.extract_patterns()

    # Daha önce kural çıkarılmış, kayıt yapılmamalı
    mock_memory.save_memory.assert_not_called()

def test_get_active_patterns(mock_memory):
    # Setup data
    mock_memory.collection.get.return_value = {
        "documents": ["Kural 1: Test kural", "Kural 2: İkinci kural"],
        "metadatas": [{"memory_type": "pattern_rule"}, {"memory_type": "pattern_rule"}]
    }

    extractor = PatternExtractor(memory=mock_memory)
    result = extractor.get_active_patterns()

    assert "Kural 1: Test kural" in result
    assert "Kural 2: İkinci kural" in result
    
    mock_memory.collection.get.assert_called_with(where={"memory_type": "pattern_rule"})
