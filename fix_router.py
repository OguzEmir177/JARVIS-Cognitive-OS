import os

with open('core/semantic_router.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''        # Argument type safety
        if not isinstance(arguments, (dict, str, list)):
            arguments = {}

        def _update_and_write():'''

replacement = '''        # Argument type safety
        if not isinstance(arguments, (dict, str, list)):
            arguments = {}

        DYNAMIC_CONTENT_TAGS = {
            "FILE_CREATE", "FILE_WRITE", "FILE_READ", "FILE_DELETE",
            "FOLDER_OPEN", "FILE_LATEST", "PYTHON_EXEC",
            "WHATSAPP_MESSAGE", "WEB_SEARCH", "GOOGLE_SEARCH", "YT_SEARCH",
            "LLM_EVAL", "YOUTUBE_STRATEGY", "REMEMBER", "STARTUP_REMINDER",
            "SCHEDULE", "MAP_SHOW", "CHART_SHOW", "SPEAK"
        }
        if tool_tag in DYNAMIC_CONTENT_TAGS:
            arguments = None

        def _update_and_write():'''

if target in content:
    content = content.replace(target, replacement)
    with open('core/semantic_router.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Replaced successfully')
else:
    print('Target not found')
