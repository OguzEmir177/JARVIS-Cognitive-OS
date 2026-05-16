"""
J.A.R.V.I.S. Ghost Mode Launcher
Terminal penceresi GÖSTERMEDEN GUI'yi başlatır.
Bu dosya pythonw.exe ile çalıştırılmalıdır.
"""
import sys
import os

# Proje kökünü yola ekle
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# GUI'yi başlat
from gui.interface import launch_gui
launch_gui()
