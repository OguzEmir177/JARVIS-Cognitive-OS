import os
for f in ['tools/browser_tool.py', 'tools/system_tool.py', 'tools/gui_tool.py']:
    if not os.path.exists(f): continue
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    content = content.replace('success=True, message=', 'success=True, verified=True, message=')
    content = content.replace('success=True, speak=', 'success=True, verified=True, speak=')
    content = content.replace('success=False, message=', 'success=False, verified=False, error="Fail", message=')
    content = content.replace('success=False, speak=', 'success=False, verified=False, error="Fail", speak=')
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)
