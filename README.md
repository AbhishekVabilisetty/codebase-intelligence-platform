# AI Codebase Intelligence Platform

A FastAPI and browser-based tool that clones public GitHub repositories, parses Python and JavaScript/TypeScript code, indexes code for semantic search, and reports static-analysis findings.

## Features (MVP)

### Phase 1: Core Understanding
- **Code Parsing** - Extract structure from Python/JavaScript codebases
- **Embeddings** - Convert code into vector representations for semantic search
- **Q&A System** - Answer questions like "Where is authentication?", "What does this module do?"
- **Architecture Summary** - Identify key components and dependencies

### Phase 2: Analysis & Insights
- **Code Smell Detection** - Identify common anti-patterns
- **Pattern Recognition** - Detect design patterns used in codebase
- **Dependency Graph** - Visualize module relationships

### Phase 3: Developer Experience
- **Refactoring Suggestions** - AI-powered code improvement recommendations
- **Unit Test Generation** - Auto-generate tests from code structure
- **Architecture Diagrams** - Visual representation of codebase structure

## Project Structure

```
├── backend/
│   ├── src/
│   │   ├── analyzers/        # Code analysis & parsing
│   │   ├── embeddings/       # Embedding generation & storage
│   │   ├── rag/              # RAG system for Q&A
│   │   ├── api.py            # FastAPI backend
│   │   └── models.py         # Data models
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── README.md
```

## Tech Stack

**Backend:**
- FastAPI - REST API
- Python AST & JavaScript parsing
- NVIDIA Nemotron embeddings and Gemini for RAG answers
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

# Create .env file with your NVIDIA API key (PowerShell)
Copy-Item .env.example .env
# Then set NVIDIA_API_KEY in .env

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

## Configuration

Copy `backend/.env.example` to `backend/.env`, then set both required keys:

- `NVIDIA_API_KEY` for code embeddings
- `GEMINI_API_KEY` for AI answers and summaries

Never commit `backend/.env`; it is excluded by `.gitignore`.

## Runtime notes

- Generated repositories, vector data, and cached reports live in `backend/temp_repos/`, `backend/chroma_db/`, and `backend/cache/`. They are intentionally ignored by Git.
- Code is indexed with NVIDIA `nvidia/nemotron-3-embed-1b` in `passage` mode; questions use `query` mode.
- After changing embedding models, re-analyze each repository so stored vectors match the query model.

## MVP Goals

1. ✅ Parse a GitHub repo (Python/JS)
2. ✅ Generate embeddings for code chunks
3. ✅ Build semantic Q&A system
4. ✅ Simple web interface for queries
5. ✅ Show codebase architecture/structure

## Progress

### Phase 1: MVP (✅ COMPLETED)
- [x] Project setup & structure
- [x] Code parser (Python AST)
- [x] Embeddings system (NVIDIA + ChromaDB)
- [x] RAG Q&A system (NVIDIA integration)
- [x] Backend API (FastAPI)
- [x] Frontend UI (HTML/CSS/JS)
- [x] Code smell detection (basic)
- [x] Docker setup
- [x] Installation guide

### Phase 2: Enhancements (🚧 IN PROGRESS)
- [ ] JavaScript/TypeScript support
- [ ] Architecture diagram generation
- [ ] Advanced code smell patterns
- [ ] Unit test generation
- [ ] Performance profiling integration
- [ ] Caching & optimization
- [ ] User authentication

### Phase 3: Future Features
- [ ] VS Code extension
- [ ] IDE integrations
- [ ] Multi-language support
- [ ] Graph database for complex queries
- [ ] Real-time collaboration
- [ ] Machine learning model fine-tuning
