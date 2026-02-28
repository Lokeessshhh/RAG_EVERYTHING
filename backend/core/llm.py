import os
import json
from typing import Generator
import httpx
from backend.config import LLM


class LLMWrapper:
    def __init__(self):
        self.worker_url = os.getenv("CLOUDFLARE_WORKER_URL", "").rstrip("/")
        if not self.worker_url:
            raise RuntimeError("CLOUDFLARE_WORKER_URL environment variable is not set")
        self.max_tokens = LLM["max_tokens"]
        self.temperature = LLM["temperature"]
        self.stream = LLM["stream"]

    def generate_stream(
        self,
        system_prompt: str,
        user_message: str
    ) -> Generator[str, None, None]:
        """Generate streaming response from Cloudflare Llama 8B."""
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True
        }

        url = f"{self.worker_url}/chat"
        print(f"[LLM] Starting stream to {url}", flush=True)
        
        # Track if we're inside a thinking block
        in_thinking = False
        thinking_buffer = ""
        
        try:
            with httpx.Client(timeout=120.0) as client:
                print("[LLM] Client created, sending request...", flush=True)
                with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    print(f"[LLM] Response status: {response.status_code}", flush=True)
                    chunk_count = 0
                    for line in response.iter_lines():
                        if not line:
                            continue
                        # Cloudflare AI streaming format
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                # Cloudflare AI format: {"response": "text"} or OpenAI format
                                raw_text = ""
                                if "response" in data:
                                    raw_text = data["response"]
                                elif "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    raw_text = delta.get("content", "")
                                
                                if raw_text:
                                    # Filter out thinking blocks
                                    filtered = self._filter_thinking(raw_text, in_thinking, thinking_buffer)
                                    in_thinking = filtered["in_thinking"]
                                    thinking_buffer = filtered["buffer"]
                                    text = filtered["text"]
                                    
                                    if text:
                                        chunk_count += 1
                                        yield text
                            except json.JSONDecodeError:
                                # Raw text response
                                if data_str and data_str != "[DONE]":
                                    filtered = self._filter_thinking(data_str, in_thinking, thinking_buffer)
                                    in_thinking = filtered["in_thinking"]
                                    thinking_buffer = filtered["buffer"]
                                    if filtered["text"]:
                                        chunk_count += 1
                                        yield filtered["text"]
                        else:
                            # Handle raw text lines (non-SSE format)
                            try:
                                data = json.loads(line)
                                if "response" in data:
                                    filtered = self._filter_thinking(data["response"], in_thinking, thinking_buffer)
                                    in_thinking = filtered["in_thinking"]
                                    thinking_buffer = filtered["buffer"]
                                    if filtered["text"]:
                                        chunk_count += 1
                                        yield filtered["text"]
                            except json.JSONDecodeError:
                                if line.strip():
                                    filtered = self._filter_thinking(line, in_thinking, thinking_buffer)
                                    in_thinking = filtered["in_thinking"]
                                    thinking_buffer = filtered["buffer"]
                                    if filtered["text"]:
                                        chunk_count += 1
                                        yield filtered["text"]
                    print(f"[LLM] Stream complete, {chunk_count} chunks", flush=True)
        except Exception as e:
            print(f"[LLM] Stream error: {e}", flush=True)
            yield f"[Error: {e}]"
    
    def _filter_thinking(self, text: str, in_thinking: bool, buffer: str) -> dict:
        """Filter out thinking/reasoning blocks from LLM output.
        
        Handles formats like:
        - <think>...</think>
        - <thinking>...</thinking>
        - ### Thinking: ... ### Response:
        """
        result_text = ""
        
        # Check for thinking tags
        if "<think>" in text or "<thinking>" in text:
            in_thinking = True
        
        if in_thinking:
            # Accumulate in buffer while in thinking mode
            buffer += text
            
            # Check for end of thinking
            if "</think>" in buffer or "</thinking>" in buffer:
                # Extract text after thinking block
                for end_tag in ["</think>", "</thinking>"]:
                    if end_tag in buffer:
                        idx = buffer.find(end_tag) + len(end_tag)
                        result_text = buffer[idx:].strip()
                        buffer = ""
                        in_thinking = False
                        break
            # Still in thinking, don't output
        else:
            # Not in thinking block, output directly
            # But check if we're starting one
            for start_tag in ["<think>", "<thinking>"]:
                if start_tag in text:
                    idx = text.find(start_tag)
                    result_text = text[:idx]  # Output text before thinking
                    in_thinking = True
                    buffer = text[idx:]
                    break
            else:
                # No thinking tag, output as-is
                result_text = text
        
        return {"text": result_text, "in_thinking": in_thinking, "buffer": buffer}

    def generate(
        self,
        system_prompt: str,
        user_message: str
    ) -> str:
        """Generate non-streaming response (for testing)."""
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False
        }

        url = f"{self.worker_url}/chat"
        
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            # Worker returns plain text for non-streaming
            return response.text
