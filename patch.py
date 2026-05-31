import os

with open('core/semantic_router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if 'def _update_and_write():' in line:
        insert_idx = i
        break

if insert_idx != -1:
    injection = '''
        # [FIX] Do not cache arguments for dynamic tools!
        DYNAMIC_CONTENT_TAGS = {
            "FILE_CREATE", "FILE_WRITE", "FILE_READ", "FILE_DELETE",
            "FOLDER_OPEN", "FILE_LATEST", "PYTHON_EXEC",
            "WHATSAPP_MESSAGE", "WEB_SEARCH", "GOOGLE_SEARCH", "YT_SEARCH",
            "LLM_EVAL", "YOUTUBE_STRATEGY", "REMEMBER", "STARTUP_REMINDER",
            "SCHEDULE", "MAP_SHOW", "CHART_SHOW", "SPEAK"
        }
        if tool_tag in DYNAMIC_CONTENT_TAGS:
            arguments = None

'''
    lines.insert(insert_idx, injection)
    with open('core/semantic_router.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('Patched successfully!')
else:
    print('Failed to patch')
