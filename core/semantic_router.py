"""

[V15.0] Semantic Router (Dynamic Embedding Cache)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Replaces the spaghetti regex/keyword router with a pure TF-IDF cosine similarity local vector model.

Lightning fast, local execution, no LLM latency.

Now features a Dynamic Embedding Cache for autonomous self-learning.

"""

import os

import json

import asyncio

import time

import logging

import numpy as np

from typing import Dict, Any, Optional

from dataclasses import dataclass



try:

    from sklearn.feature_extraction.text import TfidfVectorizer

    from sklearn.metrics.pairwise import cosine_similarity

except ImportError:

    raise SystemError("SemanticRouter requires scikit-learn. Please run 'pip install scikit-learn'.")



logger = logging.getLogger("JARVIS.SemanticRouter")



@dataclass

class RouteMatch:

    tool_tag: str

    params: Dict[str, Any]

    confidence: float

    is_forced: bool = False

    reasoning: str = ""



class SemanticRouter:

    """[V15.0] Vector Based Autonomous Router (Dynamic Embedding Cache)"""

    def __init__(self):

        logger.info("Starting SemanticRouter (TF-IDF Vector-based)...")

        self.vectorizer = TfidfVectorizer(lowercase=True, analyzer='word', ngram_range=(1, 3))

        self.cache_path = os.path.join(os.getcwd(), "memory_db", "dynamic_embeddings.json")

        self.max_custom_commands = 1000

        

        # Intent Vectors

        self.tool_definitions = {

            "APP_OPEN": ["start the application", "open the program", "run", "hungry", "open spotify", "open youtube", "open discord", "open chrome", "open app"],

            "APP_KILL": ["close the application", "end", "durdur", "close the program", "kapat", "log out"],

            "WEB_SEARCH": ["internette ara", "bilgi bul", "research", "google", "ne demek", "nedir", "kimdir", "how old"],

            "YT_SEARCH": ["search on youtube", "video bul", "youtube ara"],

            "YT_PLAY": ["play on youtube", "video izle", "open video"],

            "WHATSAPP_MESSAGE": ["send whatsapp message", "mesaj at", "mesaja yaz"],

            "SYSTEM_POWER": ["turn off the computer", "pc kapat", "reboot", "sistemi kapat", "cut power"],

            "CLOSE_LAST_TAB": ["sekmeyi kapat", "son sekmeyi kapat", "close page"],

            "FILE_READ": ["dosya oku", "file content", "what does it say", "open document"],

            "FOLDER_OPEN": ["open folder", "open directory", "open folder", "open downloads", "show folder"],

        }

        

        self.tags = []

        self.corpus = []

        self.learned_data = {}

        

        #1. Load Constant Definitions

        for tag, phrases in self.tool_definitions.items():

            for phrase in phrases:

                self.tags.append(tag)

                self.corpus.append(phrase)

                

        # 2. Autonomously Load Learnings from Disk

        self._load_learned_routes()

                

        # Train the model

        self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus)



    def _load_learned_routes(self):

        """It reads the learned cache file on the disk synchronously (Fail-Fast)."""

        if not os.path.exists(self.cache_path):

            return

            

        try:

            with open(self.cache_path, "r", encoding="utf-8") as f:

                self.learned_data = json.load(f)

            

            count = 0

            for phrase, data in self.learned_data.items():

                self.tags.append(data["tool_tag"])

                self.corpus.append(phrase)

                count += 1

                

            if count > 0:

                logger.info(f"Autonomous Cache: {count} dynamic commands were added to the vector space.")

        except json.JSONDecodeError as e:

            logger.error(f"SemanticRouter Cache (JSON) read error: File is corrupt! Detail: {e}")

            raise SystemError(f"Failed to read Dynamic Embedding Cache (JSON format error): {e}")

        except Exception as e:

            logger.error(f"SemanticRouter critical error: {e}")

            raise SystemError(f"SemanticRouter initialization failed: {e}")



    async def learn_new_route(self, user_input: str, tool_tag: str, arguments: Any = None):

        """Asynchronously saves the successful command that LLM decodes to local JSON."""

        if not user_input or len(user_input.split()) < 2 or len(user_input) > 50:

            return

            

        # Argument type safety

        if not isinstance(arguments, (dict, str, list)):

            arguments = {}




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

        def _update_and_write():

            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)

            

            pruned_key = None

            if user_input in self.learned_data:

                self.learned_data[user_input]["use_count"] += 1

                self.learned_data[user_input]["last_used"] = time.time()

                self.learned_data[user_input]["tool_tag"] = tool_tag

                self.learned_data[user_input]["arguments"] = arguments

            else:

                self.learned_data[user_input] = {

                    "tool_tag": tool_tag,

                    "arguments": arguments,

                    "use_count": 1,

                    "last_used": time.time()

                }

                

                # Pruning Logic: If the maximum limit is exceeded, delete the least used one

                if len(self.learned_data) > self.max_custom_commands:

                    sorted_keys = sorted(

                        self.learned_data.keys(), 

                        key=lambda k: (self.learned_data[k]["use_count"], self.learned_data[k]["last_used"])

                    )

                    pruned_key = sorted_keys[0]

                    del self.learned_data[pruned_key]

                    logger.info(f"Autonomous Cache Limit Exceeded: '{pruned_key}' has been pruned.")

                    

            # Fail-fast disk burning (no errors are swallowed)

            with open(self.cache_path, "w", encoding="utf-8") as f:

                json.dump(self.learned_data, f, ensure_ascii=False, indent=2)

            

            return True, pruned_key



        # Prevent event loop blocking by transferring I/O operations to ThreadPool

        loop = asyncio.get_running_loop()

        try:

            success, pruned_key = await loop.run_in_executor(None, _update_and_write)

        except Exception as e:

            logger.error(f"Cache write error: {e}")

            return

        

        if success:

            logger.info(f"Autonomous Learning Success: '{user_input}' -> {tool_tag} (Args: {arguments})")

            

            needs_refit = False

            

            # Instantly synchronize vectors in RAM (Remove deleted ones)

            if pruned_key and pruned_key in self.corpus:

                idx = self.corpus.index(pruned_key)

                self.corpus.pop(idx)

                self.tags.pop(idx)

                needs_refit = True

                

            # Add new learning

            if user_input not in self.corpus:

                self.tags.append(tool_tag)

                self.corpus.append(user_input)

                needs_refit = True

                

            if needs_refit:

                # Execute asynchronously as it is a CPU-bound operation

                self.tfidf_matrix = await loop.run_in_executor(None, self.vectorizer.fit_transform, self.corpus)



    def route(self, user_input: str, world_context: Dict[str, Any] = None, context: Dict[str, Any] = None) -> Optional[RouteMatch]:

        """Tests the command in vector space."""

        if not user_input or len(user_input.strip()) < 2:

            return None

            

        input_vec = self.vectorizer.transform([user_input])

        similarities = cosine_similarity(input_vec, self.tfidf_matrix).flatten()

        

        best_index = int(np.argmax(similarities))

        best_score = float(similarities[best_index])

        

        if best_score < 0.30:

            return None

            

        best_tag = self.tags[best_index]

        matched_phrase = self.corpus[best_index]

        

        # Above 0.65 is considered "Forced" (Exact), between 0.30-0.65 is left for confirmation/hint to LLM (is_forced=False).

        is_forced_match = best_score >= 0.65

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


        

        #1. Dynamic Learned Cache Matching

        if matched_phrase in self.learned_data:

            cached_args = self.learned_data[matched_phrase].get("arguments", {})

            params = {"query": user_input}

            

            if isinstance(cached_args, dict):

                params.update(cached_args)

            elif isinstance(cached_args, str):

                params["learned_arg"] = cached_args

                params["query"] = cached_args 

                

            logger.info(f"Router: Dynamic Embedding Match → {best_tag} (Skor: {best_score:.3f}, Forced: {is_forced_match})")

            

            if is_forced_match:

                # Update usage statistics in the background (Audit Fix: log errors)

                def _update_stats():

                    if matched_phrase in self.learned_data:

                        self.learned_data[matched_phrase]["use_count"] += 1

                        self.learned_data[matched_phrase]["last_used"] = time.time()

                try:

                    loop = asyncio.get_running_loop()



                    async def _run_stats_update():

                        try:

                            await loop.run_in_executor(None, _update_stats)

                        except Exception as _e:

                            logger.warning(f"Router statistics update error: {_e}")



                    asyncio.ensure_future(_run_stats_update())

                except RuntimeError:

                    # No event loop — run directly

                    _update_stats()

                

            return RouteMatch(

                tool_tag=best_tag,

                params=params,

                confidence=best_score,

                is_forced=is_forced_match,

                reasoning=f"Dynamic Cache Match (Score: {best_score:.3f})"

            )

            

        # 2. Static Word Group Matching

        query = user_input.lower()

        phrases_to_remove = self.tool_definitions.get(best_tag, [])

        for phrase in phrases_to_remove:

            if phrase in query:

                query = query.replace(phrase, "").strip()

                

        if not query:

            query = user_input

            

        logger.info(f"Router: Static Vector Matching → {best_tag} (Score: {best_score:.3f}, Forced: {is_forced_match})")

        return RouteMatch(

            tool_tag=best_tag, 

            params={"query": query}, 

            confidence=best_score, 

            is_forced=is_forced_match, 

            reasoning=f"Static Cosine Similarity (Score: {best_score:.3f})"

        )



    def get_tool_stats(self) -> Dict[str, Any]:

        return {

            "model": "TF-IDF (scikit-learn)", 

            "vector_count": len(self.corpus), 

            "dynamic_cache_size": len(self.learned_data)

        }



    def record_execution(self, tool_tag: str, success: bool):

        pass



