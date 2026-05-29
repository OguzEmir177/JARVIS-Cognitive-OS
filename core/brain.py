import os
import re
import threading
import asyncio
from groq import AsyncGroq
from dotenv import load_dotenv


class GroqBrain:
    # Registered protocols compatible with Iron Dome.
    # Tool_calls outside this set are ignored and the text is included in the response.
    VALID_PROTOCOLS = {
        "GOOGLE_SEARCH", "WEB_OPEN", "YT_SEARCH", "YT_PLAY",
        "APP_OPEN", "APP_KILL", "WHATSAPP_MESSAGE", "WHATSAPP_DELETE",
        "VISION", "STRESS_TEST", "TAB_KILL", "SPEAK",
        "FILE_READ", "FILE_SUMMARIZE", "FILE_WRITE",
        "STEAM_LAUNCH", "SYSTEM_POWER",
        "EPIC_LAUNCH", "CLOSE_LAST_TAB",
        "SYSTEM_SHUTDOWN",   # [V9.5] J.A.R.V.I.S. graceful self-shutdown
        "SCHEDULE",          # [V9.2] Timing (explicitly added to Iron Dome)
        "WEB_SEARCH",        # [V9.6] Actual search returning content
        "REMEMBER",          # [V9.7] Long-term memory recording
        "STARTUP_REMINDER",  # [V9.8] Remind me at next startup
        "MAP_SHOW",          # [V10.0] Map display
        "CHART_SHOW",        # [V10.0] Graph/Statistics display
        "GOOGLE_TRENDS",     # [V10.2] Google Trends search
        "PYTHON_EXEC",       # [V15.2] Code Interpreter
        "LLM_EVAL",          # [V15.3] Cognitive Evaluator
    }

    # System commands should NOT be sent to LLM as tools.
    _EXCLUDED_TOOL_TAGS = {"PLAN", "SCHEDULE"}
    def __init__(self, config, memory_manager=None, tool_registry=None):
        self.config = config
        self.memory_manager = memory_manager
        self.tool_registry = tool_registry
        self._lock = None
        
        load_dotenv()
        # [V8.1] Use config or env
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found.")
            
        self.client = AsyncGroq(api_key=self.api_key)
        self.model = self.config.brain_models[0]
        
        # [V6.0] System prompt is now generated dynamically
        self.system_prompt = self._build_system_prompt()
        self.chat_history = [self.system_prompt]

    def _build_system_prompt(self) -> dict:
        """[V9.0] Creates the system prompt dynamically.
        [UPDATE]: Added 'Zipline' rule that prevents VISION hallucination.
        
        Prompt structure (3 sections, separated by '---'):
            [Basic Rules] --- [Tool List] --- [Loyalty Statement]"""
        # ── CHAPTER 1: BASIC RULES (UNTOUCHABLE) ──
        base_rules = (
            "PROTOCOL OMEGA (v9.9) - ABSOLUTE OBEDIENCE ENGINE\n"
            "1. YOU ARE A SYSTEM ADMINISTRATOR AND YOUR NAME IS J.A.R.V.I.S. Every output MUST start with a protocol tag. Plain text, introductory sentences ('Understood', 'Here's your answer') or explanation texts are STRICTLY PROHIBITED.\n"
            "2. DON'T CHAT. Use ONLY [PROTOCOL: SPEAK] <message> to talk to the user. Never produce text other than [PROTOCOL: SPEAK].\n"
            "3. [PROTOCOL LEAKING PROHIBITION]: Never pronounce protocol names (e.g.: 'Please use [PROTOCOL: REMEMBER]') in answers. Don't tell the user the technical command names, just tell the result.\n"
            "4. [DEADLY RULE]: 'What's my name?', 'Which team am I on?' NEVER use [PROTOCOL: VISION] or [PROTOCOL: WEB_SEARCH] unless the answer to personal questions is already in memory. Directly say [PROTOCOL: SPEAK] 'I cannot find this information in my memory, please tell me'.\n"
            "5. WHATSAPP / MESSAGE: ONLY use [PROTOCOL: WHATSAPP_MESSAGE] <person>|<message> for WhatsApp requests such as 'Text my sister' or 'Say hi to my dad'.\n"
            "6. APPLICATION MANAGEMENT: ONLY use [PROTOCOL: APP_KILL/OPEN] when prompted to 'Close WhatsApp' or 'Open YouTube'.\n"
            "7. MULTI-STEP TASKS (AGGRESSIVE PLANNING): If there is more than one verb or conjunction, always use the [PLAN] ... [/PLAN] structure. Every step should be a protocol.\n"
            "8. CLEAN PROTOCOL IN THE PLAN: Do not use the [PROTOCOL:] prefix in the plan block, just write the protocol name.\n"
            "9. [ARMORED RULE]: NEVER make up fictitious tools like 'GOOGLE_SUMMARY'.\n"
            "10. [DATA TRANSFER]: The results of the previous steps (Ex: WEB_SEARCH results) are automatically saved in the system. There is ABSOLUTELY NO NEED for you to write tags like [STEP:WEB_SEARCH]. Just use [PROTOCOL: LLM_EVAL] to read and interpret data.\n"
            "11. VISION RESTRICTION: VISION CANNOT BE USED IN 'Search and send via WhatsApp' missions.\n"
            "12. [V9.0 - STEEL LINE]: NEVER USE VISION to get the system time or find past memory records."
            "Date and time information is already given to you automatically in the [SYSTEM STATUS] block. If a past task you were asked about is not in [LONG TERM MEMORY],"
            "never search; Just say 'Not in my history records' and stop.\n"
            "13. APPLICATION OPENING RULE: Use ONLY [PROTOCOL: APP_OPEN] X in commands such as 'Open X', 'Start X', 'Run X'."
            "Even if names like WhatsApp, Discord, Spotify are mentioned, try APP_OPEN first."
            "Sending a message clearly requires verbs such as 'message', 'write', 'tell'.\n"
            "14. REMINDER RULE: Schedule like 'remind me in X minutes/hours', 'set an alarm', 'set a reminder'"
            "ONLY use [PROTOCOL: SCHEDULE] minute|message format in your commands."
            "Example: 'Remind me to take a break in 5 minutes' → [PROTOCOL: SCHEDULE] 5|take a break."
            "DO NOT USE APP_OPEN or other protocol.\n"
            "15. FILE/DIRECTORY RULE: Use ONLY [PROTOCOL: FILE_READ] <path> in commands such as 'list files', 'show documents', 'files on desktop', 'open folder'."
            "Examples:"
            "'list documents on desktop' → [PROTOCOL: FILE_READ] desktop,"
            "'list documents folder' → [PROTOCOL: FILE_READ] documents,"
            "'C:/Users/show files' → [PROTOCOL: FILE_READ] C:/Users."
            "It is PROHIBITED to say 'understood' with SPEAK, be sure to call FILE_READ.\n"
            "16. RESEARCH + MESSAGE RULE: Like 'Research and send it to my sister/someone'"
            "ALWAYS use the [PLAN] block in multi-step commands. However, NEVER use WHATSAPP_MESSAGE unless it is CLEARLY stated TO WHOM it will be sent (e.g. just 'can you research and tell me')! Use WEB_SEARCH only."
            "[CRITICAL] In the 'Search and send/message' flow, use WEB_SEARCH, NOT GOOGLE_SEARCH."
            "Example 1: 'Research X and send to my sister' →"
            "[PLAN] 1. WEB_SEARCH X 2. WHATSAPP_MESSAGE ablam|[STEP:WEB_SEARCH] [/PLAN] "
            "Example 2: 'Can you research X and tell me' → Just [PROTOCOL: WEB_SEARCH] X"
            "USING Function calling produces plain text [PLAN] block.\n"
            "17. STEAM RULE: Use [PROTOCOL: STEAM_LAUNCH] game_name in the 'Open X from Steam', 'Launch X game' commands.\n"
            "18. POWER RULE: Use [PROTOCOL: SYSTEM_POWER] shut down/restart for PHYSICAL shutdown of the COMPUTER, such as 'turn off computer', 'turn off PC', 'shut down Windows', 'restart'. Do not operate without approval.\n"
            "19. EPIC GAMES RULE: Use [PROTOCOL: EPIC_LAUNCH] game_name in commands such as 'Open Rocket League', 'Start Fortnite'.\n"
            "20. TAB CLOSING RULE: Use [PROTOCOL: CLOSE_LAST_TAB] in the 'Close the tab you just opened', 'Close the search tab' commands.\n"
            "21. [CRITICAL] JARVIS SELF SHUTDOWN RULE: J.A.R.V.I.S. rules such as 'shut down yourself', 'turn off J.A.R.V.I.S.', 'close program', 'close see you', 'log out', 'close application', 'terminate self'. ONLY use [PROTOCOL: SYSTEM_SHUTDOWN] in commands targeting your PROGRAM."
            "NOTE: SYSTEM_POWER=physical shutdown of the computer. SYSTEM_SHUTDOWN=J.A.R.V.I.S. The program closes itself. NO parameters required.\n"
            "22. [DEADLY RULE - CLOSING TAG]: MUST end the [PLAN] block with exactly [/PLAN]."
            "FAKE closing tags such as [/PROTOCOL], [/PROTOCOL: PLAN], [/PROTOCOL PLAN], ./PROTOCOL PLAN, /PROTOCOL PLAN, [PLAN_END] are STRICTLY PROHIBITED."
            "Incorrect labeling will cause the system to malfunction. The only valid closing is ONLY 7 CHARACTERS: [/PLAN]\n"
            "23. [INVISIBLE MODE vs VISIBLE MODE RULE]:\n"
            "a) User 'How old is Messi?', 'How is the weather?' or asks you for information, ALWAYS use [PROTOCOL: WEB_SEARCH] <query> running in the background. This tool is invisible and provides data directly to you.\n"
            "b) If the user SPECIFICALLY says 'search on Google', 'open in browser', 'show on screen' ONLY then use [PROTOCOL: GOOGLE_SEARCH] <query>. This tool opens a visible tab.\n"
            "Opening unnecessary tabs (GOOGLE_SEARCH) is STRICTLY PROHIBITED.\n"
            "24. LONG-TERM MEMORY AND START REMINDER RULE:\n"
            "A) When the user provides permanent information about themselves, their likes, their preferences, or their life ('memorize this'), use [PROTOCOL: REMEMBER] <information> to EXPRESSLY record it. Example: 'My name is Oğuz' -> [PROTOCOL: REMEMBER] The user's name is Oğuz. Save only important personal information. CAUTION: If the user asks you to SAY only the information in your memory ('what do you know about me', 'tell me about me') NEVER USE [PROTOCOL: REMEMBER]! Just speak the information with [PROTOCOL: SPEAK].\n"
            "B) If the user wants a reminder for the next session, such as 'Remind me this the next time you boot', 'tell me this when I boot you tomorrow', use [PROTOCOL: STARTUP_REMINDER] <message>. Example: 'Remind me to clean house next time I start up' -> [PROTOCOL: STARTUP_REMINDER] You must clean house.\n"
            "25. MAP RULE: When the user asks where a location is, requests its coordinates, or says 'show on map', ONLY use [PROTOCOL: MAP_SHOW] <lat>|<lon>|<title>|<zoom>."
            "Example: 'Where is Istanbul?' -> [PROTOCOL: MAP_SHOW] 41.0082|28.9784|Istanbul|10."
            "If you don't know the coordinates, find them first with WEB_SEARCH.\n"
            "26. CHART RULE: When the user asks for statistical data or wants a comparison, use [PROTOCOL: CHART_SHOW] <json_data>|<title>|<type> to visualize the data."
            "Type must be one of the following: 'bar', 'line', 'pie', 'area'. JSON schema: {\"labels\": [\"A\", \"B\"], \"values\": [10, 20], \"ylabel\": \"Birim\"}."
            "Example: 'Chart the last 3 days of the dollar' -> [PROTOCOL: CHART_SHOW] {\"labels\":[\"Pzt\",\"Sal\",\"Çar\"],\"values\":[32,32.5,33],\"ylabel\":\"TL\"}|Dollar Rate|line\n"
            "27. GOOGLE TRENDS RULE: When the user specifically asks 'how trending' something is, 'how popular is it', or 'search it on Google Trends', ONLY use [PROTOCOL: GOOGLE_TRENDS] <query>. Example: 'how trendy is bed wars' -> [PROTOCOL: GOOGLE_TRENDS] bed wars.\n"
            "28. [SELF AWARENESS RULE]: NEVER use any search (GOOGLE_SEARCH, WEB_SEARCH etc.) for commands that question your SELF-existence and characteristics such as 'What can you do', 'What are your talents', 'Who are you'! Just read the LOYALTY AND TALENT MAP listed below and summarize it in your own words with [PROTOCOL: SPEAK].\n"
            "29. [CALCULATION RULE]: You have TWO different tools for math and calculation tasks:\n"
            "A) If you are going to extract data from the internet (WEB_SEARCH) and perform calculations/logic on this data, DEFINITELY use [PROTOCOL: LLM_EVAL] <question>. Don't use PYTHON_EXEC! Example:\n"
            "[PLAN]\n"
            "1. WEB_SEARCH Messi current goal count\n"
            "2. WEB_SEARCH Ronaldo current age\n"
            "3. LLM_EVAL Add Messi's goal and Ronaldo's age\n"
            "[/PLAN]\n"
            "B) If the user wants an instant CALCULATION from you ("What is 5+3?", "Find prime numbers") → use [PROTOCOL: PYTHON_EXEC] directly:\n"
            "Example: 'Add 27 to 15' → [PROTOCOL: PYTHON_EXEC] print(15+27)\n"
            "Example: 'Fibonacci series' → [PROTOCOL: PYTHON_EXEC] a,b=0,1\\nfor _ in range(10): print(a,end=' '); a,b=b,a+b\n"
            "[DEADLY RULES FOR PYTHON_EXEC]:\n"
            "- NEVER USE `input()`! Input cannot be received from the user in this environment.\n"
            "- Always write the result to the screen with `print()`.\n"
            "30. [DEADLY RULE - WRITING A PROGRAM/APPLICATION]: If the user asks you to CREATE an APPLICATION, PROGRAM or INTERFACE (GUI) ("make a calculator", \"write a program\", \"create a tool\", \"make a game\") →\n"
            "You CANNOT do this with PYTHON_EXEC! PYTHON_EXEC is for hidden math calculations only.\n"
            "To create a program, you MUST use [PROTOCOL: FILE_WRITE] and write a running Python file to your Desktop. Example:\n"
            "User: 'Make a calculator'\n"
            "Your Answer: [PROTOCOL: FILE_WRITE] C:/Users/proog/OneDrive/Desktop/hesap_makinesi.py|import tkinter as tk\\nroot=tk.Tk()\\nroot.title('Calculator')\\n#... (interface codes) ...\\nroot.mainloop()\n"
            "31. [TIME AWARENESS RULE]: When using WEB_SEARCH, IF the user uses words like 'current', 'currently', 'today', add '2026' to the query. IF the user has already specified a past year (e.g. 2011, 2015), NEVER add 2026 to the query, just use that past year (e.g. '2011 dollar rate').\n"
            "32. [FILE EDITING RULE]: NEVER show the code just in chat when the user asks you to change, edit or fix an existing file!\n"
            "Update the file directly as [PROTOCOL: FILE_WRITE] file_path|new_full_code. Don't write the code in the chat, write it in the file!\n"
            "Example: 'let transcripter.py work with URL only' → [PROTOCOL: FILE_WRITE] C:/Users/proog/OneDrive/Desktop/transkripter.py|import tkinter...\n"
            "33. [PYTHON CODING AND TRANSCRIPT RULE]: ALWAYS follow these two rules when writing Python interfaces or scripts (GUI):\n"
            "A) 'pytube' module is BROKEN, DO NOT use it! Always use 'youtube-transcript-api' for YouTube transcripts or videos.\n"
            "B) To prevent programs from closing suddenly when double-clicked, include all codes in a try-except block. If an error occurs, write it to the file named 'error_log.txt' and inform the user via tkinter messagebox.\n"
        )
        
        # ── CHAPTER 2: DYNAMIC VEHICLE LIST ──
        if self.tool_registry and self.tool_registry.count > 0:
            tools_section = self.tool_registry.get_tools_prompt()
        else:
            tools_section = (
                "LOYALTY AND TALENT MAP (EXTERNAL TALKING PROHIBITED):\n"
                "- Google: [PROTOCOL: GOOGLE_SEARCH] <sorgu>\n"
                "- YouTube: [PROTOCOL: YT_SEARCH] <sorgu> / [PROTOCOL: YT_PLAY] <video>\n"
                "- Web: [PROTOCOL: WEB_OPEN] <url>\n"
                "- Uygulama: [PROTOCOL: APP_OPEN] <isim> / [PROTOCOL: APP_KILL] <isim>\n"
                "- Vision: [PROTOCOL: VISION]\n"
                "- Filesystem: [PROTOCOL: FILE_READ/WRITE/SUMMARIZE]\n"
            )
        
        # ── SECTION 3: LOYALTY NOTIFICATION ──
        loyalty = "Just process Master Oğuz Emir's commands with absolute accuracy."
        
        # Merge while preserving the '---' structure
        return {
            "role": "system",
            "content": f"{base_rules}-----------------------------------\n{tools_section}\n-----------------------------------\n{loyalty}"
        }
    async def think(self, user_input: str, bypass_history: bool = False) -> str:
        if self._lock is None:
            self._lock = asyncio.Lock()
            # [V10.1] Set Locale only once, on startup (Windows noise reduction)
            import locale
            try:
                # On some Windows systems, Turkish_Turkey.1254 or "tr_TR" may be required instead of tr_TR.UTF-8.
                # Try silently, if not, continue with system default.
                locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
            except:
                try:
                    locale.setlocale(locale.LC_TIME, 'turkish')
                except:
                    pass

        #1. Memory and History Preparation (Under Lock)
        async with self._lock:
            memory_context = ""
            if self.memory_manager:
                # [V14.1] Dinamik Threshold
                is_personal = any(q in user_input.lower() for q in ["benim", "about me", "biliyorsun", "kimim", "what's my name", "remember"])
                # We set the threshold for very broad searches to 0.90!
                dynamic_threshold = 0.90 if is_personal else 0.35
                
                raw_memory = await asyncio.get_running_loop().run_in_executor(
                    None,
                    self.memory_manager.retrieve_context,
                    user_input,
                    10,
                    dynamic_threshold
                )
                
                print(f"\n[BRAIN LOG] RAW Memory Returned from ChromaDB:\n{raw_memory}\n")
                
                # [V14.0] KEYWORD RELEVANCE FILTER
                if raw_memory:
                    # IF IT IS A PERSONAL QUESTION, NEVER USE THE FILTER, PROVIDE RAW DATA DIRECTLY!
                    if is_personal:
                        memory_context = raw_memory
                        print(f"\n[BRAIN LOG] Personal question detected. Filter skipped. Text to go to LLM:\n{memory_context}\n")
                    else:
                        memory_context = self._filter_relevant_memory(user_input, raw_memory)
                        print(f"\n[BRAIN LOG] Filtered Memory:\n{memory_context}\n")
            
            from datetime import datetime
            now_str = datetime.now().strftime("%d %B %Y, %A - %H:%M")

            system_injection = f"[SYSTEM STATUS]\nCurrent date and time: {now_str}\n\n[LONG TERM MEMORY]\n"
            if memory_context and memory_context.strip():
                system_injection += f"{memory_context}\n"
                system_injection += "SYSTEM WARNING: The above memory records are ACCURATE AND TRUE. If the user is asking what's in your memory OR asking something about themselves (name, passion, etc.), DEFINITELY use the [LONG TERM MEMORY] text above! Don't say 'I don't know'!\n"
            else:
                system_injection += "SYSTEM WARNING: MEMORY IS EMPTY or NO RELEVANT RECORD FOUND! If it asks for the user's personal information (name, etc.), say 'I couldn't find this information in my memory, please tell me'.\n"
            system_injection += "[/MEMORY]\n"

            if hasattr(self.memory_manager, 'pattern_extractor'):
                patterns = self.memory_manager.pattern_extractor.get_active_patterns()
                if patterns:
                    system_injection += f"[LEARNED RULES]\n{patterns}\n"

            # [V14.0] Inject learned strategies
            if hasattr(self, '_adaptive_learner_ref') and self._adaptive_learner_ref:
                learned_rules = self._adaptive_learner_ref.get_learned_rules_prompt(limit=8)
                if learned_rules:
                    system_injection += f"\n{learned_rules}\n"

            if bypass_history:
                messages = [self.system_prompt]
            else:
                messages = list(self.chat_history)
            
            messages.insert(1, {
                "role": "system",
                "content": system_injection
            })
            messages.append({"role": "user", "content": user_input})

        #2. Groq API Call (Outside Lock - Long running process)
        if memory_context:
            print(f"\n[BRAIN LOG] Data Retrieved from Memory (Threshold 0.25, Filtered):\n{memory_context}\n")

        api_kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": getattr(self.config, "max_tokens", 2048),
            "temperature": getattr(self.config, "temperature", 0.3),
        }

        use_tools = getattr(self.config, "function_calling_enabled", False)
        if use_tools and self.tool_registry and self.tool_registry.count > 0:
            tools_payload = []
            for tool in self.tool_registry._tools.values():
                if tool.protocol_tag in self._EXCLUDED_TOOL_TAGS:
                    continue
                properties = {}
                for k, v in tool.parameters.items():
                    if isinstance(v, dict):
                        properties[k] = {"type": v.get("type", "string"), "description": str(v.get("description", ""))}
                    else:
                        properties[k] = {"type": "string", "description": str(v)}
                
                tools_payload.append({
                    "type": "function",
                    "function": {
                        "name": tool.protocol_tag,
                        "description": tool.description,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": list(properties.keys())
                        }
                    }
                })
            if tools_payload:
                api_kwargs["tools"] = tools_payload
                api_kwargs["tool_choice"] = "auto"

        # Groq API Call — Rate Limit / Fallback protected loop
        choice = None
        response = None
        last_error = None
        
        from groq import RateLimitError, APIConnectionError, APIError
        import groq

        for i, current_model in enumerate(self.config.brain_models):
            api_kwargs["model"] = current_model
            
            # [V15.5] Aggressively trim history when dropping to smaller models
            #8b model has Groq free tier TPM limit 6000 — to fit
            if "8b" in current_model:
                # Leave only system prompt + system_injection (memory) + last 2 messages + new user input
                trimmed = [messages[0]]  # system prompt
                
                # messages[1] always contains system_injection (memory). Be sure to add it too.
                if len(messages) > 1 and messages[1].get("role") == "system":
                    trimmed.append(messages[1])
                
                # Trim past messages (get last 2 messages)
                if len(messages) > 4:
                    trimmed += messages[-3:-1]  # last user+assistant pair (if user input is not already at the end)
                
                trimmed.append(messages[-1])  # yeni user input (zaten son eleman)
                # Duplicate check
                seen = set()
                unique = []
                for m in trimmed:
                    key = m.get("content", "")[:50]
                    if key not in seen:
                        seen.add(key)
                        unique.append(m)
                api_kwargs["messages"] = unique
                api_kwargs["max_tokens"] = min(api_kwargs.get("max_tokens", 2048), 1024)
                print(f"[BRAIN LOG] 8b fallback: history {len(messages)} → {len(unique)} msg, max_tokens=1024")
            
            try:
                response = await self.client.chat.completions.create(**api_kwargs)
                choice = response.choices[0]
                break # Exit the loop if successful
            except RateLimitError as e:
                last_error = e
                continue
            except (APIConnectionError, APIError) as e:
                last_error = e
                continue
            except Exception as e:
                raise e

        # If no model was successful
        if choice is None:
            print(f"[BRAIN LOG] All fallback models are sold out. Last error: {last_error}")
            return "RATE_LIMIT_ALL"

        # 3. Process Response and Update History (Under Lock Again)
        async with self._lock:
            import json
            if getattr(choice.message, "tool_calls", None):
                tool_call = choice.message.tool_calls[0]
                tag = tool_call.function.name

                if tag not in self.VALID_PROTOCOLS:
                    fallback_content = getattr(choice.message, "content", None) or ""
                    if fallback_content.strip():
                        reply = fallback_content
                    else:
                        retry_kwargs = api_kwargs.copy()
                        # To prevent the fallback content from generating the fake tag over and over again when it is empty:
                        # When we try again, we go through the same list and try our luck,
                        # but in practice this fallback is rarely desired.
                        try:
                            retry_resp = await self.client.chat.completions.create(**retry_kwargs)
                            reply = retry_resp.choices[0].message.content or ""
                        except Exception:
                            reply = "[PROTOCOL: SPEAK] Sir, I didn't know how to meet this request."
                else:
                    try:
                        args_dict = json.loads(tool_call.function.arguments)
                        if tag == "WHATSAPP_MESSAGE" and "kisi" in args_dict and "mesaj" in args_dict:
                            arg_str = f"{args_dict['kisi']}|{args_dict['mesaj']}"
                        else:
                            arg_str = " ".join(str(v) for v in args_dict.values())
                    except Exception:
                        arg_str = ""
                    reply = f"[PROTOCOL: {tag}] {arg_str}".strip()
            else:
                reply = choice.message.content or ""

            #4. Update Chat History
            if not bypass_history:
                self.chat_history.append({"role": "user", "content": user_input})
                self.chat_history.append({"role": "assistant", "content": reply})
                
                # [V10.2 FIX] Limit History (Prevents Payload Too Large Error)
                # [V15.5] Token saving — Aggressive trimming for Groq free tier TPM limit
                if len(self.chat_history) > 7:
                    self.chat_history = [self.chat_history[0]] + self.chat_history[-6:]
            
            return reply

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [V14.0] MEMORY RELEVANCE FILTER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _filter_relevant_memory(user_input: str, memory_text: str) -> str:
        """[V14.0] Anti-Memory Poisoning
        
        Keyword overlap each line retrieved from memory with user input.
        passes it under control. It discards lines that have no words in common.
        
        This prevents old WhatsApp tasks or irrelevant episodic recordings from being deleted.
        prevents it from poisoning the current context."""
        if not memory_text or not user_input:
            return memory_text
        
        # Extract meaningful words from user input (3+ characters)
        stop_words = {
            'bir', 'bir', 'bu', 'This', 'da', 'de', 'mi', 'Is it', 'mu', 'Is it',
            've', 'ile', 'for', 'ben', 'sen', 'bana', 'sana', 'beni', 'seni',
            'var', 'yok', 'ne', 'How', 'Please', 'eder', 'olur', 'olan',
            'the', 'is', 'are', 'and', 'or', 'can', 'you', 'this', 'that',
            'gibi', 'kadar', 'daha', 'A lot', 'her', 'none', 'ama', 'fakat',
            'sonra', 'before', 'Now', 'thing', 'biraz', 'named', 'judicial',
        }
        
        input_words = set()
        for word in re.findall(r'[\wçğıöşüÇĞİÖŞÜ]+', user_input.lower()):
            if len(word) >= 3 and word not in stop_words:
                input_words.add(word)
        
        if not input_words:
            return memory_text
            
        # [HACK] If user directly asks for self or memory, bypass filter
        self_queries = ["benim", "about me", "biliyorsun", "kimim", "what's my name", "remember"]
        if any(q in user_input.lower() for q in self_queries):
            return memory_text
        
        # Check each memory line
        filtered_lines = []
        for line in memory_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            line_words = set()
            for word in re.findall(r'[\wçğıöşüÇĞİÖŞÜ]+', line.lower()):
                if len(word) >= 3:
                    line_words.add(word)
            
            # There must be at least 1 common meaningful word
            overlap = input_words & line_words
            if overlap:
                filtered_lines.append(line)
        
        return '\n'.join(filtered_lines) if filtered_lines else ""

    async def check_connection(self) -> bool:
        """[V5.9] Tests whether the API connection is healthy."""
        try:
            model_to_test = getattr(self.config, "ping_model", None) or self.model
            # A very simple test call
            await self.client.chat.completions.create(
                model=model_to_test,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                timeout=3.0
            )
            return True
        except Exception as e:
            import logging
            logging.getLogger("JARVIS.Brain").error(f"Critical API Connection Error: {e}")
            return False