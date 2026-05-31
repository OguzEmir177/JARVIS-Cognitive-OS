import os

with open('gui/interface.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if 'self.copyright_lbl.configure(text=strings["copyright"])' in line:
        insert_idx = i + 1
        break

if insert_idx != -1:
    injection = '''
        # Update vision_lbl if it is currently showing the waiting placeholder
        current_vision = self.vision_lbl.cget("text")
        if current_vision in (LANG["en"]["waiting"], LANG["tr"]["waiting"]):
            self.vision_lbl.configure(text=strings["waiting"])
            
        # Re-apply the current status translation
        if hasattr(self, '_status'):
            self._update_status(self._status)
'''
    lines.insert(insert_idx, injection)
    with open('gui/interface.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('Patched _apply_language successfully!')
else:
    print('Failed to patch _apply_language')
