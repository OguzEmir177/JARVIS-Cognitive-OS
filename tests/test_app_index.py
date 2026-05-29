"""
[TEST] UniversalAppIndex - Evrensel Uygulama Bulucu Testi
"""
import sys
import os

sys.path.insert(0, r"c:\Users\proog\OneDrive\Desktop\Projects\My_Jarvis_Project")
os.chdir(r"c:\Users\proog\OneDrive\Desktop\Projects\My_Jarvis_Project")

import logging
logging.basicConfig(level=logging.WARNING)

from tools.utils.app_index import UniversalAppIndex, _normalize

print("=" * 60)
print("  UniversalAppIndex Testi")
print("=" * 60)

idx = UniversalAppIndex.instance()
idx.build_index()

print(f"\nToplam indeksli uygulama: {len(idx._index)}")

# Kaynaklar
from collections import Counter
sources = Counter(e.source for e in idx._index)
print("\nKaynaklar:")
for src, count in sorted(sources.items(), key=lambda x: -x[1]):
    print(f"  {src:20s}: {count}")

# Fuzzy arama testleri
print("\n" + "=" * 60)
print("  Fuzzy Matching Testleri")
print("=" * 60)

tests = [
    ("github",       "Should find GitHub"),
    ("whatsap",      "Should find WhatsApp (typo)"),
    ("whatsapp",     "Should find WhatsApp (correct spelling)"),
    ("discord",      "Must find Discord"),
    ("steam",        "should find Steam"),
    ("vs code",      "Should find VS Code"),
    ("vscode",       "Should find VS Code (abbreviation)"),
    ("chrome",       "Should find Chrome"),
    ("spotify",      "Must find Spotify"),
    ("notepad",      "should find Notepad"),
    ("epic",         "Must find Epic Games"),
    ("DISCORD",      "Discord - caps test"),
    ("Spotify",      "Spotify - mixed letters test"),
    ("discort",      "Discord - typo test"),
    ("googlechrome", "Chrome - cursive"),
]

print(f"\n{'Sorgu':<20} {'Bulunan':<35} {'Skor':<8} {'Kaynak'}")
print("-" * 80)
for query, desc in tests:
    hits = idx.search(query, top_k=1)
    if hits:
        score, entry = hits[0]
        flag = "[OK]" if score >= 0.70 else "[?] "
        print(f"  {flag} {query:<18} {entry.display_name:<35} {score:.2f}    {entry.source}")
    else:
        print(f"  [X] {query:<18} {'BULUNAMADI':<35} -       -")

print("\n" + "=" * 60)
print("  Normalizasyon Testi")
print("=" * 60)
norm_tests = [
    ("WhatsApp", "whatsapp"),
    ("GitHub Desktop", "githubdesktop"),
    ("Visual Studio Code", "visualstudiocode"),
    ("Epic Games", "epicgames"),
]
for raw, expected in norm_tests:
    result = _normalize(raw)
    ok = "[OK]" if result == expected else "[X]"
    print(f"  {ok} '{raw}' -> '{result}' (beklenen: '{expected}')")

print("\nTesting completed.")
