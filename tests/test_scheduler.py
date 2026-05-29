import pytest
import asyncio
from unittest.mock import patch, MagicMock
import datetime

from core.scheduler import JarvisScheduler

@pytest.fixture
def mock_engine():
    engine = MagicMock()
    async def mock_process(action):
        pass
    engine.process_input = MagicMock(side_effect=mock_process)
    return engine

@pytest.mark.asyncio
async def test_scheduler_sleep_calculation(mock_engine):
    """It tests whether sleep is (60 - seconds) seconds relative to the current seconds."""
    scheduler = JarvisScheduler(mock_engine)
    
    # Let it be 07:59:45, expected sleep time is 60 - 45 = 15 seconds.
    test_time = datetime.datetime(2026, 4, 20, 7, 59, 45)
    
    with patch('core.scheduler.datetime') as mock_dt, \
         patch('core.scheduler.asyncio.sleep') as mock_sleep:
        
        mock_dt.now.return_value = test_time
        # We throw CancelledError on the first sleep call to break the loop
        mock_sleep.side_effect = asyncio.CancelledError
        
        await scheduler.run()
        
        mock_sleep.assert_called_once_with(15)

@pytest.mark.asyncio
async def test_scheduler_trigger(mock_engine):
    """Does it trigger the mission when it's the right time and then run it correctly? 
    It tests whether one falls asleep in a short time."""
    scheduler = JarvisScheduler(mock_engine)
    
    # We are testing at 08:00:30. (60 - 30 = 30 seconds should comply and briefing should be triggered)
    test_time = datetime.datetime(2026, 4, 20, 8, 0, 30)
    
    with patch('core.scheduler.datetime') as mock_dt, \
         patch('core.scheduler.asyncio.sleep') as mock_sleep:
        
        mock_dt.now.return_value = test_time
        mock_sleep.side_effect = asyncio.CancelledError
        
        await scheduler.run()
        
        # Let's make sure the task is triggered
        mock_engine.process_input.assert_called_with(
            "Have a morning briefing: Say good morning to Sir, tell him today's date, and summarize yesterday's important events from memory."
        )
        # And sleep for 30 seconds
        mock_sleep.assert_called_once_with(30)
