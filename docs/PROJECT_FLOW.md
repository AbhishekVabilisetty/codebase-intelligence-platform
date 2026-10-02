# Project Flow

## Purpose

Codebase Intelligence Platform analyzes a public GitHub repository and turns its source code into searchable, explainable engineering insights.

## End-to-end pipeline

```text
Browser dashboard
       |
       v
FastAPI API (`backend/src/api.py`)
       |
       +--> Clone repository to temporary workspace
       |
       +--> Parse source (`analyzers/code_parser.py`, `analyzers/js_analyzer.py`)
       |      └--> code entities + code chunks
       |
       +--> Static analysis (`analyzers/`)
       |      └--> bugs, smells, patterns, technical-debt score
       |
       +--> Retrieval index (`embeddings/vector_store.py`)
       |      └--> NVIDIA embeddings stored in ChromaDB
       |
       +--> Code graph (`graphrag/code_graph.py`)
       |      └--> files, symbols, and usage relationships
       |
       +--> RAG service (`rag/qa_system.py`)
              └--> grounded answers, explanations, summaries, refactoring advice, test drafts
```

## Directory map

```text
codebase-intelligence-platform/
├── frontend/                       # Reviewer/user dashboard
│   ├── index.html                  # UI structure
│   ├── styles.css                  # UI presentation
│   └── app.js                      # API calls and rendering
├── backend/
│   ├── src/
│   │   ├── api.py                  # Pipeline orchestrator and REST endpoints
│   │   ├── models.py               # Request/response and analysis models
│   │   ├── config.py               # Environment-driven provider configuration
│   │   ├── analyzers/              # Parse source and run static checks
│   │   ├── embeddings/             # Generate/store/search vector embeddings
│   │   ├── graphrag/               # Build and traverse the code graph
│   │   └── rag/                    # Retrieve context and generate answers
│   ├── tests/                      # Focused automated tests
│   ├── .env.example                # Safe configuration template
│   └── requirements.txt            # Python dependencies
├── docs/
│   └── PROJECT_FLOW.md             # Reviewer-oriented architecture guide
├── Dockerfile                      # Backend container image
├── docker-compose.yml              # Backend + frontend local stack
└── README.md                       # Setup and project overview
```

## Suggested reviewer walkthrough

1. Open the dashboard and submit a public GitHub repository URL.
2. Explain that the API clones it only into a temporary workspace, then parses supported Python and JavaScript/TypeScript source.
3. Show the analysis outputs: entities, static-quality findings, technical-debt score, and dependency graph.
4. Ask a codebase question. Explain that semantic search finds relevant chunks, the code graph expands related symbols, and the selected LLM writes a grounded answer.
5. Show the focused graph explorer or architecture summary to demonstrate how retrieval and relationships improve explainability.

## Runtime data policy

`backend/cache/`, `backend/chroma_db/`, and `backend/temp_repos/` are generated at runtime and ignored by Git. They should not be included in a submission or demo archive; each repository can be re-analyzed to recreate them.
