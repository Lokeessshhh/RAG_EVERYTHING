from typing import List, Optional, AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import asyncio

from backend.core.retriever import Retriever
from backend.core.llm import LLMWrapper
from backend.core.upstash_redis import UpstashRedis
from backend.core.cache import make_cache_key

router = APIRouter(prefix="/chat", tags=["chat"])

# Initialize components
retriever = Retriever()
llm = LLMWrapper()
redis = UpstashRedis()


class Message(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str

class ChatRequest(BaseModel):
    query: str
    source_types: Optional[List[str]] = None
    conversation_history: Optional[List[Message]] = None  # Previous messages for context


class SourceInfo(BaseModel):
    source_name: str
    source_type: str
    score: float
    preview: str


def resolve_context_with_llm(query: str, conversation_history: Optional[List[Message]]) -> dict:
    """
    Use LLM to resolve context and decide if RAG is needed.
    
    Returns:
        {
            "needs_rag": bool,
            "search_query": str,  # Resolved search query (includes context if needed)
            "reasoning": str
        }
    """
    if not conversation_history or len(conversation_history) == 0:
        return {"needs_rag": True, "search_query": query, "reasoning": "No conversation history"}
    
    # Build conversation context (last 6 messages, full content)
    history = conversation_history[-6:]
    context_lines = []
    for msg in history:
        role = "User" if msg.role == "user" else "Assistant"
        context_lines.append(f"{role}: {msg.content}")
    
    conversation_context = "\n".join(context_lines)
    
    prompt = f"""Analyze the current question in the context of the recent conversation.

RECENT CONVERSATION:
{conversation_context}

CURRENT QUESTION: {query}

Your task:
1. Understand what the current question is asking about. Resolve any pronouns (it, that, this) to their actual referent from the conversation.
2. Decide if this question needs to search the knowledge base (RAG) or can be answered from general knowledge.
3. If RAG is needed, provide a clear search query that includes the resolved context.

Reply in this EXACT JSON format (no markdown, no explanation):
{{"needs_rag": true/false, "search_query": "the resolved search query with context", "reasoning": "brief reason"}}

Examples:
- If user asks "how it got solved?" after discussing RovoDev, search_query should be "how was the RovoDev log file locking problem solved"
- If user asks "what about pricing?" after discussing a product, search_query should be "pricing for [product name]"
- If user asks general question like "what is 2+2", needs_rag is false
"""
    
    try:
        response = llm.generate(
            system_prompt="You are a context analyzer. Reply ONLY with valid JSON, no markdown, no explanation.",
            user_message=prompt,
        ).strip()
        
        # Parse JSON response
        import json as json_mod
        # Remove any markdown code blocks if present
        if response.startswith("```"):
            response = response.split("\n", 1)[1] if "\n" in response else response
            response = response.rsplit("```", 1)[0] if "```" in response else response
        
        result = json_mod.loads(response)
        
        # Validate result
        if "needs_rag" not in result or "search_query" not in result:
            return {"needs_rag": True, "search_query": query, "reasoning": "Invalid LLM response format"}
        
        print(f"[DEBUG] LLM context resolution: needs_rag={result['needs_rag']}, search_query={result['search_query'][:100]}")
        return result
        
    except Exception as e:
        print(f"[DEBUG] LLM context resolution failed: {e}")
        return {"needs_rag": True, "search_query": query, "reasoning": f"Error: {e}"}


def detect_language(text: str) -> str:
    """
    Detect the primary language of the text.
    Returns: 'hindi', 'hinglish', or 'english'
    """
    # Count Devanagari Unicode chars (Hindi script range: U+0900–U+097F)
    devanagari_chars = sum(
        1 for ch in text
        if '\u0900' <= ch <= '\u097f'
    )
    total_alpha = sum(1 for ch in text if ch.isalpha())
    if total_alpha == 0:
        return 'english'

    devanagari_ratio = devanagari_chars / total_alpha

    if devanagari_ratio > 0.5:
        return 'hindi'        # Mostly Hindi script
    elif devanagari_ratio > 0.05:
        return 'hinglish'     # Mix of Hindi script + Latin (Hinglish)
    else:
        return 'english'      # Mostly Latin script


def detect_context_language(results: list) -> str:
    """Detect the primary language of retrieved context chunks."""
    all_text = " ".join(r.get("text", "") for r in results[:5])
    return detect_language(all_text)


def build_language_instruction(query_lang: str, context_lang: str) -> str:
    """
    Build an explicit language instruction for the LLM based on
    the query language and context language combination.
    """
    # Note about auto-generated captions: YouTube auto-captions sometimes produce
    # partially garbled Devanagari (missing matras). The model should still attempt
    # to interpret and answer even if some words look unusual.
    garbled_note = (
        "NOTE: The transcript may contain slightly garbled Hindi text (auto-generated captions "
        "with missing vowel marks). Do your best to interpret the meaning and answer anyway — "
        "do not refuse or say the text is unreadable.\n"
    )

    if query_lang == 'english' and context_lang == 'hindi':
        return (
            "LANGUAGE INSTRUCTION: The user asked in English but the source documents/transcripts "
            "are in Hindi (Devanagari script). You MUST:\n"
            "1. Read and understand the Hindi context thoroughly.\n"
            "2. Translate the relevant parts mentally into English.\n"
            "3. Answer ENTIRELY in clear, fluent English.\n"
            "4. Do NOT output any Hindi or Devanagari script in your response.\n"
            "5. Do NOT say you cannot read Hindi — you can and must translate it.\n"
            "6. Do NOT say the context is unavailable — use what is given.\n"
            f"{garbled_note}"
        )
    elif query_lang == 'english' and context_lang == 'hinglish':
        return (
            "LANGUAGE INSTRUCTION: The source content is in Hinglish (mixed Hindi/English). "
            "Answer ENTIRELY in clear English. Translate any Hindi portions as needed.\n"
            f"{garbled_note}"
        )
    elif query_lang == 'hindi' and context_lang in ('english', 'hinglish'):
        return (
            "LANGUAGE INSTRUCTION: The user asked in Hindi. Answer in Hindi (Devanagari script). "
            "Translate the English context to Hindi in your response.\n"
        )
    elif query_lang == 'hinglish':
        return (
            "LANGUAGE INSTRUCTION: The user is writing in Hinglish (mix of Hindi and English). "
            "Reply in the same Hinglish style — mix Hindi and English naturally, as the user does.\n"
            f"{garbled_note}"
        )
    elif query_lang == 'hindi' and context_lang == 'hindi':
        return (
            "LANGUAGE INSTRUCTION: Both the question and the source documents are in Hindi. "
            "Answer in Hindi (Devanagari script).\n"
            f"{garbled_note}"
        )
    else:
        return (
            "LANGUAGE INSTRUCTION: Answer in the same language the user used to ask the question.\n"
        )


def route_query(query: str, has_documents: bool) -> str:
    """
    Use LLM to decide if a query needs RAG (document search) or can be answered generally.
    Returns: 'RAG' or 'GENERAL'
    """
    if not has_documents:
        return "GENERAL"

    routing_prompt = (
        "You are a query router. Decide if the user's question requires searching through "
        "uploaded documents/files/knowledge base, OR if it can be answered as a general question.\n\n"
        "Reply with ONLY one word:\n"
        "- RAG → if the question is about specific documents, files, topics, people, events, or content "
        "that would be in an uploaded knowledge base\n"
        "- GENERAL → if it's a general knowledge question, math, coding help, casual chat, "
        "creative writing, or anything not requiring specific uploaded documents\n\n"
        f"User question: {query}\n\n"
        "Reply (RAG or GENERAL):"
    )

    try:
        decision = llm.generate(
            system_prompt="You are a query router. Reply with only 'RAG' or 'GENERAL'.",
            user_message=routing_prompt,
        ).strip().upper()

        # Extract just the first word in case LLM adds explanation
        first_word = decision.split()[0] if decision else "RAG"
        result = "RAG" if "RAG" in first_word else "GENERAL"
        print(f"[DEBUG] Query routed to: {result} (raw: '{decision[:50]}')")
        return result
    except Exception as e:
        print(f"[DEBUG] Routing failed ({e}), defaulting to RAG")
        return "RAG"


async def generate_general_stream(query: str, query_lang: str) -> AsyncGenerator[str, None]:
    """Generate a general (non-RAG) streaming response."""
    lang_instr = build_language_instruction(query_lang, query_lang)
    system_prompt = (
        f"You are a helpful, friendly AI assistant.\n\n{lang_instr}"
        "Answer the user's question directly and helpfully using your general knowledge. "
        "Be concise but thorough."
    )
    for chunk in llm.generate_stream(system_prompt, query):
        yield f"data: {json.dumps({'content': chunk})}\n\n"
    yield "data: [DONE]\n\n"


async def generate_stream(query: str, source_types: Optional[List[str]], conversation_history: Optional[List[Message]] = None) -> AsyncGenerator[str, None]:
    """Generate streaming response with smart RAG/General routing."""
    loop = asyncio.get_event_loop()

    # Use LLM to resolve context and decide if RAG is needed
    context_resolution = await loop.run_in_executor(None, lambda: resolve_context_with_llm(query, conversation_history))
    search_query = context_resolution.get("search_query", query)
    llm_decided_rag = context_resolution.get("needs_rag", True)
    
    print(f"[DEBUG] LLM context resolution: needs_rag={llm_decided_rag}, search_query={search_query[:80]}...")
    
    # Detect query language upfront
    query_lang = detect_language(query)
    print(f"[DEBUG] Query language detected: {query_lang}")

    # Check if this is a metadata query (asking about files, count, etc.)
    if retriever._is_metadata_query(query):
        files = await loop.run_in_executor(None, retriever.get_file_listing)
        file_list = "\n".join([f"- {f['file_path']}" for f in files])

        lang_instr = build_language_instruction(query_lang, 'english')
        system_prompt = f"You are a helpful assistant. Answer questions about files based on the provided file listing.\n\n{lang_instr}"
        user_message = f"""The user has uploaded these files:
{file_list}

Total: {len(files)} files

User question: {query}

Answer the question based on the file listing above."""

        for chunk in llm.generate_stream(system_prompt, user_message):
            yield f"data: {json.dumps({'content': chunk})}\n\n"

        yield "data: [DONE]\n\n"
        return

    # Check if we have a fully cached response for this exact query + context
    # Include last message content in key so same question in different contexts doesn't collide
    last_msg = conversation_history[-1].content if conversation_history else ""
    cache_key = make_cache_key("chat:response", f"{search_query}|{last_msg}")
    try:
        cached_response = await redis.get(cache_key)
        if cached_response:
            print("[DEBUG] Cache hit - serving cached response")
            data = json.loads(cached_response)
            # Yield cached content
            for chunk in data.get("content", "").split():
                yield f"data: {json.dumps({'content': chunk + ' '})}\n\n"
            # Yield cached sources if present
            if data.get("sources"):
                yield f"data: {json.dumps({'sources': data['sources']})}\n\n"
            yield "data: [DONE]\n\n"
            return
    except Exception:
        pass  # Fall through to normal pipeline on any cache error

    # Use LLM context resolution for routing (already decided needs_rag above)
    if not llm_decided_rag:
        print("[DEBUG] LLM decided GENERAL response (no RAG needed)")
        async for chunk in generate_general_stream(query, query_lang):
            yield chunk
        return

    # RAG path: embed query → search → rerank → answer with context
    print("[DEBUG] LLM decided RAG pipeline")
    # search_query already set from LLM context resolution above
    results = await loop.run_in_executor(None, lambda: retriever.search(search_query, source_types))

    # Build context
    if results:
        context = retriever.build_context(results)
        print(f"[DEBUG] Context built with {len(results)} results, length={len(context)} chars")

        # Truncate context for small LLMs — Llama 3 8B struggles beyond ~4000 chars of Hindi
        # Hindi Devanagari chars are multi-byte but semantically dense; 4000 chars ≈ 600-800 words
        context_lang_pre = detect_context_language(results)
        max_context_chars = 4000 if context_lang_pre == 'hindi' else 6000
        if len(context) > max_context_chars:
            context = context[:max_context_chars] + "\n...[context truncated for model capacity]"
            print(f"[DEBUG] Context truncated to {max_context_chars} chars (language={context_lang_pre})")
    else:
        context = "No relevant context found."
        print("[DEBUG] No results found, using fallback context")

    # Detect context language
    context_lang = detect_context_language(results) if results else 'english'
    print(f"[DEBUG] Context language detected: {context_lang}")

    # Build language instruction
    lang_instruction = build_language_instruction(query_lang, context_lang)
    print(f"[DEBUG] Language instruction: query={query_lang}, context={context_lang}")

    # Detect what source types are present in results
    result_source_types = set(r.get("source_type", "") for r in results) if results else set()
    has_youtube = "youtube" in result_source_types
    has_code = bool(result_source_types & {"code", "github"})
    has_only_youtube = has_youtube and len(result_source_types - {"youtube"}) == 0
    has_chat = "chat" in result_source_types
    
    print(f"[DEBUG] Source types: {result_source_types}, youtube={has_youtube}, code={has_code}, chat={has_chat}")

    # Build conversation history string for LLM awareness
    chat_history_str = ""
    if conversation_history:
        lines = []
        for msg in conversation_history[-6:]:
            role = "User" if msg.role == "user" else "Assistant"
            lines.append(f"{role}: {msg.content}")
        chat_history_str = "\n---CONVERSATION HISTORY---\n" + "\n".join(lines) + "\n---END HISTORY---\n"

    # Build a context-aware system prompt with language instruction injected
    if has_only_youtube:
        system_prompt = f"""You are a helpful multilingual assistant that answers questions based on YouTube video transcripts.

{lang_instruction}
CORE INSTRUCTIONS:
1. Answer based on the transcript excerpts provided in CONTEXT below.
2. Quote or paraphrase relevant parts of the transcript to support your answer.
3. If the transcript does not contain the answer, say so clearly.
4. Do NOT pretend you watched the video — you have the transcript text only.
5. Even if the transcript is in a different language than the question, you MUST still answer using the transcript content.
6. Do NOT repeat information already given in the conversation history."""

        user_message = f"""Here are relevant excerpts from the YouTube video transcript:

---TRANSCRIPT CONTEXT---
{context}
---END CONTEXT---
{chat_history_str}
User question: {query}

Answer based on the transcript excerpts above. Do not repeat what was already said in the conversation history. Remember to follow the language instruction."""

    elif has_youtube and has_code:
        system_prompt = f"""You are a helpful multilingual assistant with access to both code files and YouTube video transcripts.

{lang_instruction}
CORE INSTRUCTIONS:
1. The CONTEXT below may contain code snippets AND/OR YouTube transcript excerpts.
2. Answer using whichever context is most relevant to the question.
3. Quote relevant parts (code or transcript) to support your answer.
4. If the context does not contain the answer, say so clearly.
5. Do NOT repeat information already given in the conversation history."""

        user_message = f"""Here is relevant context (code and/or video transcript):

---CONTEXT---
{context}
---END CONTEXT---
{chat_history_str}
User question: {query}

Answer based on the context above. Do not repeat what was already said in the conversation history. Remember to follow the language instruction."""

    else:
        system_prompt = f"""You are a helpful multilingual assistant with access to the user's uploaded documents and code.

{lang_instruction}
CORE INSTRUCTIONS:
1. Answer based ONLY on the CONTEXT provided from the user's uploaded files.
2. When asked about a file or code, describe what it does based on the context.
3. Quote relevant snippets from the context to support your answer.
4. If no relevant context was found, say so clearly — do not make up information.
5. Do NOT repeat information already given in the conversation history."""

        user_message = f"""Here is relevant content from the user's uploaded files:

---CONTEXT---
{context}
---END CONTEXT---
{chat_history_str}
User question: {query}

Answer based ONLY on the context shown above. Do not repeat what was already said in the conversation history. Follow the language instruction."""

    # Stream LLM response and collect for caching
    full_content_parts = []
    
    print(f"[DEBUG] Starting LLM stream with {len(context)} chars context...", flush=True)
    
    # Use queue for real streaming from thread to async generator
    import queue
    import threading
    
    chunk_queue = queue.Queue()
    
    def _stream_llm():
        try:
            for chunk in llm.generate_stream(system_prompt, user_message):
                chunk_queue.put(("chunk", chunk))
            chunk_queue.put(("done", None))
        except Exception as e:
            print(f"[DEBUG] LLM stream error: {e}", flush=True)
            chunk_queue.put(("error", str(e)))
    
    # Start streaming in background thread
    thread = threading.Thread(target=_stream_llm, daemon=True)
    thread.start()
    
    # Yield chunks as they arrive
    while True:
        item_type, data = chunk_queue.get()
        if item_type == "done":
            break
        elif item_type == "error":
            yield f"data: {json.dumps({'content': f'Error: {data}'})}\n\n"
            break
        elif item_type == "chunk":
            full_content_parts.append(data)
            yield f"data: {json.dumps({'content': data})}\n\n"
    
    thread.join()

    # Send sources at the end
    sources = []
    if results:
        for r in results[:5]:  # Top 5 sources
            text = r.get("text", "")
            sources.append({
                "source_name": r.get("source_name", "Unknown"),
                "source_type": r.get("source_type", "unknown"),
                "score": round(r.get("rerank_score", 0), 4),
                "preview": text[:200] + "..." if len(text) > 200 else text
            })
        yield f"data: {json.dumps({'sources': sources})}\n\n"

    yield "data: [DONE]\n\n"

    # Store full response to cache for future identical queries
    try:
        cache_data = {
            "content": "".join(full_content_parts),
            "sources": sources
        }
        await redis.set_json(cache_key, cache_data, ttl_seconds=300)
    except Exception:
        pass  # Non-critical: don't fail if cache storage fails


@router.post("")
async def chat(request: ChatRequest):
    """Chat endpoint with streaming RAG response and conversation context."""
    return StreamingResponse(
        generate_stream(request.query, request.source_types, request.conversation_history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
