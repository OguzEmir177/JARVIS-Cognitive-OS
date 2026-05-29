import os
import tokenize
import json
import re
from io import BytesIO
from deep_translator import GoogleTranslator
import time

def contains_turkish(text, is_comment=False):
    turkish_chars = set('ığüşöçİĞÜŞÖÇ')
    if any(c in turkish_chars for c in text):
        return True
    
    words = set(re.findall(r'\b\w+\b', text.lower()))
    common_tr = {'ve', 'bir', 'için', 'bu', 'ile', 'de', 'da', 'olarak', 'gibi', 'en', 'çok', 'daha', 'olan', 'var', 'yok', 'tamam', 'başlat', 'hata', 'sistem', 'modül', 'kontrol', 'ediliyor', 'edildi'}
    
    if len(words.intersection(common_tr)) > 0:
        return True
    return False

def protect_variables(text):
    # Find all {} blocks
    pattern = re.compile(r'\{[^{}]*\}')
    matches = pattern.findall(text)
    
    protected_text = text
    for i, match in enumerate(matches):
        protected_text = protected_text.replace(match, f'<v{i}>')
    return protected_text, matches

def restore_variables(text, matches):
    for i, match in enumerate(matches):
        # translator might add spaces around tags
        text = text.replace(f'< v{i} >', match)
        text = text.replace(f'<v{i} >', match)
        text = text.replace(f'< v{i}>', match)
        text = text.replace(f'<v{i}>', match)
    return text

# Dictionary cache to avoid re-translating and speed up
CACHE_FILE = 'translation_cache.json'
try:
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        translation_cache = json.load(f)
except:
    translation_cache = {}

def translate_text(text):
    if not text.strip():
        return text
        
    if text in translation_cache:
        return translation_cache[text]
        
    protected_text, variables = protect_variables(text)
    
    try:
        translated = GoogleTranslator(source='tr', target='en').translate(protected_text)
        translated = restore_variables(translated, variables)
        
        # some post processing for known terms
        translated = translated.replace('Cognitive', 'Cognitive')
        
        translation_cache[text] = translated
        return translated
    except Exception as e:
        print(f"Translation error for text '{text}': {e}")
        return text

def to_char_index(lines_chars, row, col):
    # lines_chars is a precomputed list of line lengths
    return sum(lines_chars[:row-1]) + col

def process_file(filepath):
    with open(filepath, 'rb') as f:
        content_bytes = f.read()
        
    try:
        content_str = content_bytes.decode('utf-8')
    except:
        return False
        
    lines = content_str.splitlines(keepends=True)
    lines_chars = [len(line) for line in lines]
    
    try:
        tokens = list(tokenize.tokenize(BytesIO(content_bytes).readline))
    except Exception as e:
        print(f"Tokenize error in {filepath}: {e}")
        return False
        
    replacements = []
    
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            # Heuristic to avoid translating dict keys or very short strings without spaces/turkish chars
            is_comment = tok.type == tokenize.COMMENT
            original_string = tok.string
            
            # String literals might have prefixes like f"..." or r"..."
            prefix = ""
            core_str = original_string
            if tok.type == tokenize.STRING:
                m = re.match(r'^([frubFRUB]*)([\'"]{1,3})(.*)(\2)$', original_string, flags=re.DOTALL)
                if m:
                    prefix, quote, core_str, end_quote = m.groups()
                else:
                    quote = ""
                    end_quote = ""
                    
            if contains_turkish(core_str, is_comment=is_comment):
                if tok.type == tokenize.STRING and " " not in core_str and not any(c in 'ığüşöçİĞÜŞÖÇ' for c in core_str):
                    # Very likely a dict key without spaces and without explicit TR chars but maybe matched a stopword
                    continue
                    
                translated_core = translate_text(core_str)
                if translated_core != core_str:
                    if tok.type == tokenize.STRING:
                        new_string = f"{prefix}{quote}{translated_core}{end_quote}"
                    else:
                        new_string = translated_core
                        
                    start_idx = to_char_index(lines_chars, tok.start[0], tok.start[1])
                    end_idx = to_char_index(lines_chars, tok.end[0], tok.end[1])
                    replacements.append((start_idx, end_idx, new_string))

    if not replacements:
        return False
        
    # Apply replacements from bottom to top
    replacements.sort(key=lambda x: x[0], reverse=True)
    
    for start_idx, end_idx, new_string in replacements:
        content_str = content_str[:start_idx] + new_string + content_str[end_idx:]
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content_str)
        
    # Save cache periodically
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(translation_cache, f, ensure_ascii=False, indent=2)
        
    print(f"Translated {len(replacements)} items in {filepath}")
    return True

def run():
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
            
    translated_files = 0
    for i, filepath in enumerate(all_files):
        print(f"Processing {filepath} ({i+1}/{len(all_files)})...")
        if process_file(filepath):
            translated_files += 1
            
    print(f"Finished! Translated strings in {translated_files} files.")

if __name__ == '__main__':
    run()
