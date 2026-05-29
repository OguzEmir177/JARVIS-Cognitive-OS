import json
import re
from deep_translator import GoogleTranslator
from concurrent.futures import ThreadPoolExecutor
import time

def protect_variables(text):
    pattern = re.compile(r'\{[^{}]*\}')
    matches = pattern.findall(text)
    
    protected_text = text
    for i, match in enumerate(matches):
        protected_text = protected_text.replace(match, f'<v{i}>')
    return protected_text, matches

def restore_variables(text, matches):
    for i, match in enumerate(matches):
        text = text.replace(f'< v{i} >', match)
        text = text.replace(f'<v{i} >', match)
        text = text.replace(f'< v{i}>', match)
        text = text.replace(f'<v{i}>', match)
    return text

def translate_single(text):
    if not text.strip():
        return text, text
        
    protected_text, variables = protect_variables(text)
    
    try:
        translated = GoogleTranslator(source='tr', target='en').translate(protected_text)
        translated = restore_variables(translated, variables)
        translated = translated.replace('Cognitive', 'Cognitive')
        return text, translated
    except Exception as e:
        return text, text

def run_fast():
    print("Loading terms...")
    try:
        with open('turkish_terms.json', 'r', encoding='utf-8') as f:
            terms = json.load(f)
    except Exception as e:
        print("Failed to load terms:", e)
        return

    CACHE_FILE = 'translation_cache.json'
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except:
        cache = {}

    missing_terms = [t for t in terms if t not in cache]
    print(f"Total terms: {len(terms)}, Already cached: {len(cache)}, Missing to translate: {len(missing_terms)}")
    
    if missing_terms:
        print(f"Translating {len(missing_terms)} terms with 15 threads...")
        with ThreadPoolExecutor(max_workers=15) as executor:
            results = list(executor.map(translate_single, missing_terms))
            
        for orig, trans in results:
            cache[orig] = trans
            
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print("Updated cache.")

if __name__ == '__main__':
    run_fast()
