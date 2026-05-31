import os

with open('core/semantic_router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if 'is_forced_match = best_score >= 0.65' in line:
        insert_idx = i + 1
        break

if insert_idx != -1:
    injection = '''
        # [FIX] Never force dynamic tools so the LLM can parse natural language (e.g. into recipient|message)
        DYNAMIC_CONTENT_TAGS = {
            "FILE_CREATE", "FILE_WRITE", "FILE_READ", "FILE_DELETE",
            "FOLDER_OPEN", "FILE_LATEST", "PYTHON_EXEC",
            "WHATSAPP_MESSAGE", "WEB_SEARCH", "GOOGLE_SEARCH", "YT_SEARCH",
            "LLM_EVAL", "YOUTUBE_STRATEGY", "REMEMBER", "STARTUP_REMINDER",
            "SCHEDULE", "MAP_SHOW", "CHART_SHOW", "SPEAK"
        }
        if best_tag in DYNAMIC_CONTENT_TAGS:
            is_forced_match = False

'''
    lines.insert(insert_idx, injection)
    with open('core/semantic_router.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('Patched successfully!')
else:
    print('Failed to patch')
