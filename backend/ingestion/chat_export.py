import os
import json
import re
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from backend.ingestion.base import BaseIngester, Chunk
from backend.config import CHUNKING

_MAX_CHUNK_CHARS = 1200  # max chars per chat chunk (Q+A pairs can be long)


class ChatExportIngester(BaseIngester):
    def __init__(self):
        self.chunk_size = CHUNKING["chat"]["size"]
        self.overlap = CHUNKING["chat"]["overlap"]
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=_MAX_CHUNK_CHARS,
            chunk_overlap=100,
            separators=["\n\n", "\n", ". ", " "]
        )

    def ingest(self, source_path: str) -> List[Chunk]:
        """Ingest chat exports from various platforms."""
        filename = os.path.basename(source_path)
        ext = os.path.splitext(source_path)[1].lower()
        
        if ext == ".json":
            return self._parse_json_export(source_path, filename)
        elif ext == ".md":
            return self._parse_markdown_export(source_path, filename)
        
        return []

    def _parse_json_export(self, source_path: str, filename: str) -> List[Chunk]:
        """Parse JSON chat exports (OpenAI, Claude, Gemini formats)."""
        chunks = []
        
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Detect platform format
        platform = self._detect_platform(data)
        
        if platform == "openai":
            chunks = self._parse_openai_format(data, filename)
        elif platform == "claude":
            chunks = self._parse_claude_format(data, filename)
        elif platform == "gemini":
            chunks = self._parse_gemini_format(data, filename)
        else:
            # Generic JSON parsing
            chunks = self._parse_generic_json(data, filename)
        
        return chunks

    def _detect_platform(self, data: dict) -> str:
        """Detect which platform the export is from."""
        if "mapping" in data:
            return "openai"
        elif "conversations" in data:
            return "claude"
        elif "history" in data or "contents" in data:
            return "gemini"
        return "generic"

    def _parse_openai_format(self, data: dict, filename: str) -> List[Chunk]:
        """Parse OpenAI conversation export format."""
        chunks = []
        
        # OpenAI exports have a 'mapping' structure
        mapping = data.get("mapping", {})
        title = data.get("title", "Untitled")
        
        # Extract messages in order
        messages = []
        for node_id, node in mapping.items():
            message = node.get("message")
            if message:
                role = message.get("author", {}).get("role", "")
                content_parts = message.get("content", {}).get("parts", [])
                content = " ".join([p for p in content_parts if isinstance(p, str)])
                
                if role in ["user", "assistant"]:
                    messages.append({
                        "role": "user" if role == "user" else "assistant",
                        "content": content
                    })
        
        # Merge consecutive same-role messages
        messages = self._merge_consecutive_roles(messages)
        
        # Create Q+A turn pairs
        chunks = self._create_turn_pairs(messages, filename, "openai", title)
        
        return chunks

    def _parse_claude_format(self, data: dict, filename: str) -> List[Chunk]:
        """Parse Claude conversation export format."""
        chunks = []
        
        conversations = data.get("conversations", [])
        
        for conv in conversations:
            conv_name = conv.get("name", "Untitled")
            messages = conv.get("chat_messages", [])
            
            formatted_messages = []
            for msg in messages:
                role = "user" if msg.get("sender") == "human" else "assistant"
                content = msg.get("text", "")
                formatted_messages.append({
                    "role": role,
                    "content": content
                })
            
            formatted_messages = self._merge_consecutive_roles(formatted_messages)
            conv_chunks = self._create_turn_pairs(
                formatted_messages, filename, "claude", conv_name
            )
            chunks.extend(conv_chunks)
        
        return chunks

    def _parse_gemini_format(self, data: dict, filename: str) -> List[Chunk]:
        """Parse Gemini conversation export format."""
        chunks = []
        
        # Gemini can have 'history' or 'contents'
        history = data.get("history", data.get("contents", []))
        
        messages = []
        for entry in history:
            role = entry.get("role", "")
            parts = entry.get("parts", [])
            content = " ".join([
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in parts
            ])
            
            if role in ["user", "model"]:
                messages.append({
                    "role": "user" if role == "user" else "assistant",
                    "content": content
                })
        
        messages = self._merge_consecutive_roles(messages)
        chunks = self._create_turn_pairs(messages, filename, "gemini", "Gemini Chat")
        
        return chunks

    def _parse_generic_json(self, data: dict, filename: str) -> List[Chunk]:
        """Parse generic JSON chat format."""
        chunks = []
        
        # Try to find message-like structures
        if isinstance(data, list):
            messages = []
            for item in data:
                if isinstance(item, dict):
                    role = item.get("role", item.get("sender", "user"))
                    content = item.get("content", item.get("text", item.get("message", "")))
                    
                    if role in ["user", "human", "me"]:
                        role = "user"
                    elif role in ["assistant", "ai", "bot", "claude", "gpt"]:
                        role = "assistant"
                    
                    if content:
                        messages.append({"role": role, "content": str(content)})
            
            if messages:
                messages = self._merge_consecutive_roles(messages)
                chunks = self._create_turn_pairs(messages, filename, "generic", "Chat")
        
        return chunks

    def _parse_markdown_export(self, source_path: str, filename: str) -> List[Chunk]:
        """Parse markdown chat exports (Claude format)."""
        chunks = []
        
        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Pattern for Claude markdown: "**Human**:" or "**Assistant**:"
        pattern = r'\*\*(Human|Assistant)\*\*:\s*(.*?)(?=\*\*(?:Human|Assistant)\*\*:|$)'
        
        matches = re.findall(pattern, content, re.DOTALL)
        
        messages = []
        for role, text in matches:
            role = "user" if role == "Human" else "assistant"
            messages.append({"role": role, "content": text.strip()})
        
        messages = self._merge_consecutive_roles(messages)
        chunks = self._create_turn_pairs(messages, filename, "claude", filename)
        
        return chunks

    def _merge_consecutive_roles(self, messages: List[dict]) -> List[dict]:
        """Merge consecutive messages with the same role."""
        if not messages:
            return messages
        
        merged = [messages[0]]
        
        for msg in messages[1:]:
            if msg["role"] == merged[-1]["role"]:
                merged[-1]["content"] += "\n\n" + msg["content"]
            else:
                merged.append(msg)
        
        return merged

    def _create_turn_pairs(
        self,
        messages: List[dict],
        filename: str,
        platform: str,
        conversation_id: str
    ) -> List[Chunk]:
        """Create Q+A turn pairs as chunks."""
        chunks = []
        
        i = 0
        turn_index = 0
        
        while i < len(messages):
            msg = messages[i]
            
            if msg["role"] == "user":
                # Find the assistant response
                user_content = msg["content"]
                assistant_content = ""
                
                if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                    assistant_content = messages[i + 1]["content"]
                    i += 2
                else:
                    i += 1
                
                # Format as Q+A turn
                turn_text = f"Human: {user_content}\nAssistant: {assistant_content}"

                # Split if oversized
                texts = self._splitter.split_text(turn_text) if len(turn_text) > _MAX_CHUNK_CHARS else [turn_text]
                for t in texts:
                    if t.strip():
                        chunks.append(Chunk(
                            text=t,
                            source_type="chat",
                            source_name=filename,
                            metadata={
                                "platform": platform,
                                "conversation_id": conversation_id,
                                "turn_index": turn_index,
                                "date": self._get_timestamp(),
                                "ingested_at": self._get_timestamp()
                            }
                        ))
                turn_index += 1
            else:
                i += 1
        
        return chunks
