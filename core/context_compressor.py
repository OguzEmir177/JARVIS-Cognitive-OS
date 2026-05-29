"""
[V11.1] J.A.R.V.I.S. Context Compression Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Manages context window efficiently by compressing, summarizing,
and scoring relevance of conversation history.

Features:
- Automatic chat history trimming
- Relevance scoring for memory context
- Semantic compression of long outputs
- Token-aware windowing
"""

import logging
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger("JARVIS.ContextCompression")


class ContextCompressor:
    """
    Manages LLM context window to prevent overflow and maintain relevance.
    """
    def __init__(self, max_history_messages: int = 20, max_chars_per_message: int = 2000):
        self.max_history = max_history_messages
        self.max_chars = max_chars_per_message

    def compress_chat_history(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Compresses chat history to fit within context limits.
        
        Strategy:
        1. Always keep system prompt (first message)
        2. Always keep last N messages
        3. Summarize/trim middle messages
        4. Truncate very long messages
        """
        if len(messages) <= self.max_history:
            return self._truncate_messages(messages)
        
        # Keep system prompt + last N messages
        system_msgs = [m for m in messages[:2] if m.get("role") == "system"]
        recent = messages[-self.max_history:]
        
        # Build summary of dropped messages
        dropped = messages[len(system_msgs):-(self.max_history)]
        if dropped:
            summary = self._summarize_dropped(dropped)
            compressed = system_msgs + [summary] + recent
        else:
            compressed = system_msgs + recent
        
        return self._truncate_messages(compressed)

    def compress_memory_context(self, memory_text: str, max_chars: int = 1500) -> str:
        """
        Compresses memory retrieval results to essential information.
        Removes redundancy and keeps only high-value content.
        """
        if not memory_text or len(memory_text) <= max_chars:
            return memory_text
        
        lines = memory_text.split('\n')
        
        # Score each line by information density
        scored = []
        seen_content = set()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Dedup check
            normalized = re.sub(r'\s+', ' ', line.lower())
            if normalized in seen_content:
                continue
            seen_content.add(normalized)
            
            score = self._score_line(line)
            scored.append((line, score))
        
        # Sort by score, take top lines that fit
        scored.sort(key=lambda x: -x[1])
        
        result_lines = []
        total_chars = 0
        for line, score in scored:
            if total_chars + len(line) > max_chars:
                break
            result_lines.append(line)
            total_chars += len(line) + 1
        
        return '\n'.join(result_lines)

    def compress_tool_output(self, output: str, max_chars: int = 1000) -> str:
        """Compresses a tool's output for storage or context injection."""
        if not output or len(output) <= max_chars:
            return output
        
        # Keep first and last portions
        half = max_chars // 2
        compressed = output[:half] + "\n...[compressed]...\n" + output[-half:]
        return compressed

    def _truncate_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Truncates individual messages that are too long."""
        result = []
        for msg in messages:
            content = msg.get("content", "")
            if len(content) > self.max_chars:
                truncated = content[:self.max_chars] + "...[truncated]"
                result.append({**msg, "content": truncated})
            else:
                result.append(msg)
        return result

    def _summarize_dropped(self, messages: List[Dict[str, str]]) -> Dict[str, str]:
        """Creates a summary message for dropped history entries."""
        user_msgs = [m for m in messages if m.get("role") == "user"]
        topics = []
        for m in user_msgs[-5:]:  # Last 5 user messages from dropped section
            content = m.get("content", "")[:60]
            if content:
                topics.append(content)
        
        summary_text = (
            f"[Previous {len(messages)} message summarized]"
            f"Son konular: {'; '.join(topics)}"
        )
        return {"role": "system", "content": summary_text}

    def _score_line(self, line: str) -> float:
        """Scores a line's information value (higher = more valuable)."""
        score = 0.5
        
        # Personal info markers (high value)
        personal = ["ordinary", "isim", "age", "beloved", "tercih", "birth"]
        if any(w in line.lower() for w in personal):
            score += 0.4
        
        # Action/event markers (medium value)
        action = ["successful", "hata", "kaydet", "remember", "important"]
        if any(w in line.lower() for w in action):
            score += 0.3
        
        # Longer lines tend to have more info
        words = len(line.split())
        if words > 10:
            score += 0.1
        if words > 20:
            score += 0.1
        
        # Penalize very short or generic lines
        if words < 5:
            score -= 0.2
        
        return min(1.0, max(0.0, score))
