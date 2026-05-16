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
    """
    Şu anki saniyeye göre uykunun (60 - second) saniye olmasını test eder.
    """
    scheduler = JarvisScheduler(mock_engine)
    
    # Saat 07:59:45 olsun, beklenen uyku süresi 60 - 45 = 15 saniye.
    test_time = datetime.datetime(2026, 4, 20, 7, 59, 45)
    
    with patch('core.scheduler.datetime') as mock_dt, \
         patch('core.scheduler.asyncio.sleep') as mock_sleep:
        
        mock_dt.now.return_value = test_time
        # Döngüyü kırmak için ilk sleep çağrısında CancelledError fırlatıyoruz
        mock_sleep.side_effect = asyncio.CancelledError
        
        await scheduler.run()
        
        mock_sleep.assert_called_once_with(15)

@pytest.mark.asyncio
async def test_scheduler_trigger(mock_engine):
    """
    Doğru zamana geldiğinde görevi tetikliyor mu ve sonrasında doğru 
    sürede uykuya dalıyor mu test eder.
    """
    scheduler = JarvisScheduler(mock_engine)
    
    # Saat 08:00:30 u test ediyoruz. (60 - 30 = 30 sn uymalı ve brifing tetiklemeli)
    test_time = datetime.datetime(2026, 4, 20, 8, 0, 30)
    
    with patch('core.scheduler.datetime') as mock_dt, \
         patch('core.scheduler.asyncio.sleep') as mock_sleep:
        
        mock_dt.now.return_value = test_time
        mock_sleep.side_effect = asyncio.CancelledError
        
        await scheduler.run()
        
        # Görevin tetiklendiğinden emin olalım
        mock_engine.process_input.assert_called_with(
            "Sabah brifingi yap: Efendime günaydın de, bugünün tarihini söyle ve dünkü önemli olayları hafızandan özetle."
        )
        # Ve 30 saniye uyumalı
        mock_sleep.assert_called_once_with(30)
