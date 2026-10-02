# Codebase Intelligence Platform

A FastAPI and browser-based workspace for analyzing public GitHub repositories. It combines source parsing, semantic code retrieval, code-grounded Q&A, static quality checks, and repository-level summaries.

## Features

- Parse Python and JavaScript/TypeScript source into entities and code chunks.
- Embed code chunks and retrieve relevant snippets for repository questions.
- Expand semantic results through a code knowledge graph of files, symbols, and resolved usages (hybrid GraphRAG).
- Generate answers, architecture summaries, implementation explanations, refactoring suggestions, and test drafts grounded in retrieved code.
- Detect potential bugs, code smells, design patterns, and technical debt.
- Explore entity relationships in a dependency graph and review saved repository reports.
- Rebuild a repository's search index after embedding model changes.

## Project Structure

```
├── backend/
│   ├── src/
│   │   ├── analyzers/        # Parsers and static-analysis detectors
│   │   ├── embeddings/       # Embedding generation and ChromaDB retrieval
│   │   ├── rag/              # Answer generation and learning resources
│   │   ├── api.py            # FastAPI routes and repository workflow
│   │   ├── config.py         # Provider and model configuration
│   │   └── models.py         # API and analysis data models
│   ├── requirements.txt
│   └── .env.example
├── frontend/                 # Static HTML, CSS, and JavaScript dashboard
├── Dockerfile
├── docker-compose.yml
└── README.md
```

For the end-to-end pipeline, directory responsibilities, and a suggested demo order, see [docs/PROJECT_FLOW.md](docs/PROJECT_FLOW.md).
The current source flow is `analyzers` → `embeddings` + `graphrag` → `rag`, orchestrated by `api.py`; focused checks live in `backend/tests/`.

## Tech Stack

**Backend:**
- FastAPI - REST API
- Python AST & JavaScript parsing
- NVIDIA Nemotron embeddings; OpenRouter or Gemini for generated answers
- ChromaDB - vector store for embeddings

**Frontend:**
- HTML/CSS/JavaScript (simple, no frameworks initially)
- Can upgrade to React later

## Getting Started

```bash
# Setup backend
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Create the local environment file (PowerShell)
Copy-Item .env.example .env
# Then set NVIDIA_API_KEY and at least one chat-provider key in .env

# Run backend
python src/api.py
```

In a second terminal, serve the frontend:

```bash
cd frontend
python -m http.server 3000
```

Open `http://127.0.0.1:3000` in your browser. The frontend expects the API at
`http://localhost:8000`.

Run the automated checks from the `backend` directory:

```bash
python -m unittest discover -s tests -v
```

## Configuration

Copy `backend/.env.example` to `backend/.env`, then configure:

- `NVIDIA_API_KEY` for code embeddings (required)
- `OPENROUTER_API_KEY` for chat answers, or `GEMINI_API_KEY` to use Gemini
- `LLM_PROVIDER` optionally selects `openrouter` or `gemini`. If unset, the app selects OpenRouter when its key exists; otherwise it selects Gemini.
- `OPENROUTER_CHAT_MODEL` optionally selects the OpenRouter model. The default `openrouter/free` router chooses an available free model, whose availability and quotas can vary.

Never commit `backend/.env`; it is excluded by `.gitignore`.

## Runtime notes

- Generated repositories, vector data, and cached reports live in `backend/temp_repos/`, `backend/chroma_db/`, and `backend/cache/`. They are intentionally ignored by Git.
- Code is indexed with NVIDIA `nvidia/nemotron-3-embed-1b` in `passage` mode; questions use `query` mode. Query, explain, and find operations then expand the semantic matches up to two hops through the saved code graph and retrieve the connected indexed chunks.
- Re-analyze an existing repository once to create its code graph. Older cached analyses continue to use vector-only retrieval until reindexed.
- After changing embedding models, rebuild each repository's search index. Use the **Rebuild search index** action in the Repositories view; this reclones and re-embeds the source.
