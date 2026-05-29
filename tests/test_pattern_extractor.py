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
    # 1. get() call: episodic capture (for listing extract_patterns)
    # 2. get() call: check if the rule already exists (already_exists)
    mock_memory.collection.get.side_effect = [
        # First call (episodic listesi)
        {
            "documents": [
                "Task: APP_OPEN discord. Result: failure. Error: application not found.",
                "Task: APP_OPEN discord. Result: failure. Error: unexpected error.",
                "Task: WEB_OPEN google.com. Result: success" # Should ignore success
            ],
            "metadatas": [
                {"outcome": "failure", "tool_used": "APP_OPEN", "memory_type": "episodic"},
                {"outcome": "failure", "tool_used": "APP_OPEN", "memory_type": "episodic"},
                {"outcome": "success", "tool_used": "WEB_OPEN", "memory_type": "episodic"}
            ]
        },
        # Second call (currently rules control)
        {
            "documents": [],
            "metadatas": []
        }
    ]

    extractor = PatternExtractor(memory=mock_memory)
    extractor.extract_patterns()

    # extract_patterns, after extracting "discord" from the doc as target and finding len=2 failed
    # Create the rule and save it with self.save_pattern().
    expected_rule = "Opening 'discord' with APP_OPEN failed 2 times. Alternative: WEB_OPEN discord.com"
    
    mock_memory.save_memory.assert_called_once()
    args, kwargs = mock_memory.save_memory.call_args
    # 1st parameter should be rule test, 2nd parameter should be "pattern_rule", 3rd parameter should be metadata
    assert expected_rule == args[0]
    assert args[1] == "pattern_rule"
    
    metadata = args[2] if len(args) > 2 else kwargs.get("metadata")
    assert metadata["auto_generated"] is True
    assert metadata["importance"] == 0.95

def test_extract_patterns_no_duplicate_rule(mock_memory):
    # Setup mock data (If the rule has been learned before, it should not be learned again)
    mock_memory.collection.get.side_effect = [
        # First episodic search
        {
            "documents": [
                "Task: APP_OPEN spotify. Result: failure.",
                "Task: APP_OPEN spotify. Result: failure."
            ],
            "metadatas": [
                {"outcome": "failure", "tool_used": "APP_OPEN"},
                {"outcome": "failure", "tool_used": "APP_OPEN"}
            ]
        },
        # Second rule search: assume it already exists
        {
            "documents": [
                "Opening 'spotify' with APP_OPEN failed 2 times. Alternative: WEB_OPEN spotify.com"
            ],
            "metadatas": [{"memory_type": "pattern_rule", "importance": 0.95}]
        }
    ]

    extractor = PatternExtractor(memory=mock_memory)
    extractor.extract_patterns()

    # Rule has been issued before, no registration should be made
    mock_memory.save_memory.assert_not_called()

def test_get_active_patterns(mock_memory):
    # Setup data
    mock_memory.collection.get.return_value = {
        "documents": ["Kural 1: Test kural", "Rule 2: Second rule"],
        "metadatas": [{"memory_type": "pattern_rule"}, {"memory_type": "pattern_rule"}]
    }

    extractor = PatternExtractor(memory=mock_memory)
    result = extractor.get_active_patterns()

    assert "Kural 1: Test kural" in result
    assert "Rule 2: Second rule" in result
    
    mock_memory.collection.get.assert_called_with(where={"memory_type": "pattern_rule"})
