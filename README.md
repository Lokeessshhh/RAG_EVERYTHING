# RAG Everything

A production-ready, full-stack **Retrieval-Augmented Generation (RAG)** chatbot that lets you embed and chat with virtually any type of content — PDFs, code, YouTube videos, websites, images, audio, GitHub repos, and AI chat exports.

---

## ✨ Features

- 🧠 **Smart Context Resolution** — resolves pronouns like "it", "that", "this" from conversation history before searching
- 💬 **Conversation Memory** — tracks last 6 messages so follow-up questions work naturally
- 🔍 **Semantic Search + Reranking** — vector search (top-50) → Voyage AI rerank (top-10) → LLM answer
- 📚 **11 Source Types** — ingest anything, ask anything
- 🌐 **Multilingual** — English, Hindi, and Hinglish support
- ⚡ **Streaming Responses** — real-time token-by-token streaming
- 🗃️ **Library Management** — view, search, and delete ingested sources
- 📎 **Embed from Chat** — paperclip button lets you embed content directly from the chat page
- 🌙 **Dark / Light Mode** — theme toggle built in
- 🎙️ **Voice Input** — speak your queries

---

## 🗂️ Supported Source Types

| Type | What it ingests |
|---|---|
| **File Upload** | PDF, TXT, MD, CSV, Python, JS, TS, Java, Go, C/C++, and more |
| **GitHub Repo** | Any public repository (code + docs) |
| **YouTube** | Video transcripts (Hindi, English, any language) |
| **Website** | Crawls pages via sitemap + Crawl4AI |
| **Image** | Gemini 1.5 Flash vision analysis + pytesseract OCR |
| **Audio / Voice** | Transcribed via Google Web Speech API |
| **Paste Text** | Direct text input with a source name |
| **AI Chat** | ChatGPT, Claude, Gemini, Grok, Perplexity shared links |

---

## 🏗️ Architecture

```
User Query
    │
    ▼
LLM resolves context (last 6 messages) → final search query
    │
    ▼
Jina Embeddings (1024-dim) → Zilliz Vector DB search (top-50)
    │
    ▼
Voyage AI Rerank (top-10) → LLM (Cloudflare Llama 8B) → Streaming response
```

---

## 🛠️ Tech Stack

### Backend
| Layer | Technology |
|---|---|
| Framework | FastAPI (Python) |
| Embeddings | Jina AI v5-text-small (1024-dim) |
| Vector DB | Zilliz Cloud (Milvus) |
| LLM | Cloudflare Workers (Llama 8B) |
| Reranking | Voyage AI rerank-2 |
| AI Parsing | Groq Llama 4 Scout 17B |
| Image Analysis | Google Gemini 1.5 Flash |
| Web Crawling | Crawl4AI |
| Caching | Upstash Redis |
| Deployment | Render |

### Frontend
| Layer | Technology |
|---|---|
| Framework | React + TypeScript |
| Build Tool | Vite |
| Styling | Tailwind CSS |
| Animations | Framer Motion |
| Icons | Lucide React |
| Deployment | Vercel |

---

## 🚀 Quick Start (Local)

### Prerequisites
- Python 3.10+
- Node.js 18+
- All API keys listed in `.env.example`

### 1. Clone the repo
```bash
git clone https://github.com/Lokeessshhh/RAG_EVERYTHING.git
cd RAG_EVERYTHING
```

### 2. Backend setup
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt

cp .env.example .env
# Fill in all API keys in .env

uvicorn backend.main:app --reload --port 8000
```

### 3. Frontend setup
```bash
cd frontend
npm install
cp .env.example .env.local
# Set VITE_API_URL=http://localhost:8000/api in .env.local

npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

---

## 🔑 Environment Variables

Copy `.env.example` to `.env` and fill in the following:

| Variable | Service | Get it at |
|---|---|---|
| `JINA_API_KEY` | Jina AI Embeddings | [jina.ai](https://jina.ai) |
| `GROQ_API_KEY` | Groq (AI Parser) | [console.groq.com](https://console.groq.com/keys) |
| `VOYAGE_API_KEY` | Voyage AI Reranking | [voyageai.com](https://www.voyageai.com) |
| `ZILLIZ_URI` | Zilliz Vector DB | [cloud.zilliz.com](https://cloud.zilliz.com) |
| `ZILLIZ_TOKEN` | Zilliz Vector DB | [cloud.zilliz.com](https://cloud.zilliz.com) |
| `CLOUDFLARE_WORKER_URL` | LLM Inference | Your Cloudflare Worker URL |
| `GEMINI_API_KEY` | Image Analysis | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| `UPSTASH_REDIS_REST_URL` | Redis Cache | [upstash.com](https://upstash.com) |
| `UPSTASH_REDIS_REST_TOKEN` | Redis Cache | [upstash.com](https://upstash.com) |

**Frontend only (Vercel):**

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://your-backend.onrender.com/api` |

---

## ☁️ Deployment

### Backend → Render

1. Push repo to GitHub
2. Create a new **Web Service** on [Render](https://render.com)
3. Connect your GitHub repo — Render auto-detects `render.yaml`
4. Add all environment variables in the Render dashboard
5. Deploy — start command is:
   ```
   uvicorn backend.main:app --host 0.0.0.0 --port $PORT
   ```

### Frontend → Vercel

1. Import your GitHub repo on [Vercel](https://vercel.com)
2. Set **Root Directory** to `frontend`
3. Add environment variable:
   - `VITE_API_URL` = `https://your-backend.onrender.com/api`
4. Deploy — Vercel auto-detects Vite via `vercel.json`

---

## 📡 API Endpoints

### Ingestion
| Endpoint | Method | Description |
|---|---|---|
| `/api/ingest/upload` | POST | Upload files (PDF, TXT, CSV, code, etc.) |
| `/api/ingest/github` | POST | Ingest a GitHub repo |
| `/api/ingest/youtube` | POST | Ingest YouTube transcript |
| `/api/ingest/website` | POST | Crawl and ingest a website |
| `/api/ingest/image` | POST | Ingest an image |
| `/api/ingest/audio` | POST | Ingest audio/voice file |
| `/api/ingest/text` | POST | Ingest plain text |
| `/api/ingest/ai-chat` | POST | Ingest AI chat share link |

### Chat & Library
| Endpoint | Method | Description |
|---|---|---|
| `/api/chat` | POST | Streaming RAG chat |
| `/api/library` | GET | List all ingested sources |
| `/api/library` | DELETE | Delete a source |
| `/api/stats` | GET | Embedding usage stats |

---

## 📁 Project Structure

```
RAG_EVERYTHING/
├── backend/
│   ├── main.py               # FastAPI app entry point
│   ├── config.py             # All configuration constants
│   ├── routers/
│   │   ├── chat.py           # Chat endpoint + RAG pipeline
│   │   └── ingest.py         # All ingestion endpoints
│   ├── core/
│   │   ├── embedder.py       # Jina AI embeddings
│   │   ├── vector_store.py   # Zilliz/Milvus operations
│   │   ├── retriever.py      # Search + rerank logic
│   │   ├── llm.py            # Cloudflare LLM wrapper
│   │   ├── cache.py          # Redis caching
│   │   ├── upstash_redis.py  # Redis client
│   │   └── rate_limit.py     # IP rate limiting
│   └── ingestion/
│       ├── text.py           # Text ingester
│       ├── pdf.py            # PDF ingester
│       ├── csv_ingest.py     # CSV ingester
│       ├── code.py           # Code ingester
│       ├── github_repo.py    # GitHub ingester
│       ├── youtube.py        # YouTube ingester
│       ├── website.py        # Website crawler
│       ├── image.py          # Image ingester
│       ├── voice.py          # Audio/voice ingester
│       ├── chat_export.py    # Chat export ingester
│       └── ai_chat_parsers/  # ChatGPT/Claude/Gemini/Grok/Perplexity parsers
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── ChatPage.tsx      # Main chat interface
│   │   │   ├── UploadPage.tsx    # Upload/ingest page
│   │   │   ├── LibraryPage.tsx   # Source library
│   │   │   └── LandingPage.tsx   # Landing page
│   │   ├── components/
│   │   │   ├── IngestModal.tsx   # Embed from chat modal
│   │   │   ├── AppShell.tsx      # Layout shell
│   │   │   └── Toast.tsx         # Notifications
│   │   └── services/
│   │       └── api.ts            # API client
│   ├── vercel.json               # Vercel deployment config
│   └── .env.example              # Frontend env vars
├── render.yaml                   # Render deployment config
├── requirements.txt              # Python dependencies
└── .env.example                  # All env vars documented
```

---

## 🧩 Chunking Strategy

| Source | Chunk Size | Overlap |
|---|---|---|
| Text | 600 chars | 80 |
| PDF | 700 chars | 100 |
| CSV | per row batch | 0 |
| Code | 800 chars | 0 |
| GitHub | 800 chars | 0 |
| YouTube | 200 words | 30 words |
| Website | 800 chars | 100 |
| Image | 800 chars | 100 |
| Voice | 400 chars | 60 |
| AI Chat | 1200 chars | 100 |

---

## 📄 License

MIT
