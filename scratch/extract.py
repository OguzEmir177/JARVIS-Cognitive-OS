import os
import tokenize
import json
import re
from io import BytesIO

def contains_turkish(text):
    turkish_chars = set('ığüşöçİĞÜŞÖÇ')
    if any(c in turkish_chars for c in text):
        return True
    
    # Check for common Turkish words
    words = re.findall(r'\b\w+\b', text.lower())
    common_tr = {'ve', 'bir', 'için', 'bu', 'ile', 'de', 'da', 'olarak', 'gibi', 'en', 'çok', 'daha', 'olan', 'var', 'yok', 'tamam', 'başlat', 'hata', 'sistem', 'modül', 'kontrol', 'ediliyor', 'edildi'}
    if any(w in common_tr for w in words):
        return True
    return False

def extract_strings_and_comments():
    extracted = set()
    root_dirs = ['core', 'memory', 'tools', 'gui', 'validation', 'tests']
    root_files = ['main.py', 'update.py', 'fix_strategies.py', 'test_brain.py']
    
    all_files = []
    
    for d in root_dirs:
        if os.path.exists(d):
            for root, _, files in os.walk(d):
                for f in files:
                    if f.endswith('.py') and f != 'ai_studio_code.py':
                        all_files.append(os.path.join(root, f))
                        
    for f in root_files:
        if os.path.exists(f) and f != 'ai_studio_code.py':
            all_files.append(f)
            
    for filepath in all_files:
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            tokens = list(tokenize.tokenize(BytesIO(content).readline))
            for tok in tokens:
                if tok.type in (tokenize.COMMENT, tokenize.STRING):
                    text = tok.string
                    if contains_turkish(text):
                        extracted.add(text)
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            
    with open('turkish_terms.json', 'w', encoding='utf-8') as f:
        json.dump(list(extracted), f, ensure_ascii=False, indent=4)
        
    print(f"Extracted {len(extracted)} terms to turkish_terms.json")

if __name__ == '__main__':
    extract_strings_and_comments()
