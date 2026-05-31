import os
import re

with open('gui/interface.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''        # [FIX] CustomTkinter placeholder bug: changing placeholder while focused can turn it into real text.
        # We temporarily steal focus to root, configure the placeholder, and then restore focus.
        has_focus = False
        try:
            has_focus = (self.root.focus_get() == self.text_entry._entry)
        except Exception:
            pass
            
        if has_focus:
            self.root.focus_set()
            
        self.text_entry.configure(placeholder_text=strings["text_placeholder"])
        
        # If any stuck placeholder text managed to sneak in, delete it
        current_text = self.text_entry.get()
        if current_text.startswith(LANG["en"]["text_placeholder"]):
            self.text_entry.delete(0, len(LANG["en"]["text_placeholder"]))
        if current_text.startswith(LANG["tr"]["text_placeholder"]):
            self.text_entry.delete(0, len(LANG["tr"]["text_placeholder"]))
            
        if has_focus:
            # Using after to let Tkinter process the focus_set event
            self.root.after(10, self.text_entry.focus_set)'''

replacement = '''        # [FIX] CustomTkinter placeholder bug:
        # Instead of messing with focus (which triggers CTk's FocusIn/Out events and bakes the old placeholder into real text),
        # we will directly clean the internal tkinter entry of ANY known placeholders before and after configuring.
        
        # 1. Clean any existing placeholder text from the internal entry
        internal_text = self.text_entry._entry.get()
        for lang_code in LANG:
            ph = LANG[lang_code].get("text_placeholder", "")
            if ph and internal_text.startswith(ph):
                self.text_entry._entry.delete(0, "end")
                self.text_entry._entry.insert(0, internal_text[len(ph):])
                
        # 2. Configure the new placeholder
        self.text_entry.configure(placeholder_text=strings["text_placeholder"])
        
        # 3. If the entry is NOT focused and is empty (internal text is empty), force the new placeholder to show
        has_focus = False
        try:
            has_focus = (self.root.focus_get() == self.text_entry._entry)
        except Exception:
            pass
            
        if not has_focus and not self.text_entry.get():
            self.text_entry._entry.delete(0, "end")
            self.text_entry._entry.insert(0, strings["text_placeholder"])
            self.text_entry._entry.configure(text_color=self.text_entry._placeholder_text_color)'''

if target in content:
    content = content.replace(target, replacement)
    with open('gui/interface.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched interface.py successfully")
else:
    print("Target not found in interface.py")
