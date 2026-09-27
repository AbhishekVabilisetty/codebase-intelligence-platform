import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import shutil
import stat
import subprocess
from datetime import datetime
from dotenv import load_dotenv

from src.models import (
    RepositoryInput, QAQuery, QAResponse, ArchitectureSummary,
    AnalysisReport,
)
from src.analyzers.code_parser import CodebaseAnalyzer
from src.analyzers.code_smell_detector import CodeSmellDetector
from src.analyzers.bug_detector import BugDetector
from src.analyzers.pattern_detector import PatternDetector
from src.analyzers.technical_debt import calculate_technical_debt
from src.embeddings.vector_store import VectorStore
from src.rag.qa_system import RAGSystem
from src.utils import save_analysis_cache, load_analysis_cache

load_dotenv()

app = FastAPI(
    title="AI Codebase Intelligence Platform",
    description="GitHub + Cursor + SonarQube + ChatGPT for your codebase",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
TEMP_DIR  = os.path.join(BASE_DIR, "temp_repos")

vector_store = VectorStore()
rag_system   = RAGSystem(vector_store=vector_store)
smell_detector   = CodeSmellDetector()
bug_detector     = BugDetector()
pattern_detector = PatternDetector()

analyzed_repos: dict = {}


def _safe_rmtree(path: str):
    """Windows-safe recursive delete — clears read-only flags before removing."""
    def _on_error(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass
    if os.path.exists(path):
        shutil.rmtree(path, onerror=_on_error)


def _load_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)
    for fn in os.listdir(CACHE_DIR):
        if fn.endswith(".json"):
            rid = fn[:-5]
            data = load_analysis_cache(rid, CACHE_DIR)
            if data:
                analyzed_repos[rid] = data

_load_cache()


def _require_repo(repo_id: str):
    if repo_id not in analyzed_repos:
        raise HTTPException(404, f"Repository '{repo_id}' not found. Analyze it first.")


# ── Health ──────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "running", "version": "3.0.0", "repos_loaded": len(analyzed_repos)}


# ── Analyze ─────────────────────────────────────────────────────
@app.post("/analyze")
async def analyze_repository(repo_input: RepositoryInput, background_tasks: BackgroundTasks):
    repo_id  = repo_input.repo_url.rstrip("/").split("/")[-1]
    temp_dir = os.path.join(TEMP_DIR, repo_id)

    # Reuse completed reports when a user retries the same repository instead
    # of repeating a clone and one embedding request per code chunk.
    cached = analyzed_repos.get(repo_id)
    if cached and cached.get("url", "").rstrip("/") == repo_input.repo_url.rstrip("/"):
        debt = cached.get("debt", {})
        return {
            "status": "cached", "repo_id": repo_id,
            "entities_found": cached.get("entity_count", 0),
            "chunks_indexed": cached.get("chunk_count", 0),
            "bugs_found": len(cached.get("bugs", [])),
            "smells_found": len(cached.get("smells", [])),
            "patterns_found": len(cached.get("patterns", [])),
            "debt_grade": debt.get("grade", "?"), "debt_score": debt.get("score", 0),
            "architecture": cached.get("architecture", {}),
        }

    if os.path.exists(temp_dir):
        _safe_rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    # Clone
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "-b", repo_input.branch, repo_input.repo_url, temp_dir],
            check=True, capture_output=True, timeout=120,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(400, f"Clone failed: {e.stderr.decode()}")
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "Clone timed out")

    try:
        # Parse
        analyzer = CodebaseAnalyzer(temp_dir)
        entities, chunks = analyzer.analyze()
        if not chunks:
            raise HTTPException(400, "No supported source files found (Python / JS / TS)")

        total_loc = sum(len(c.content.splitlines()) for c in chunks)
        file_count = len(set(e.file_path for e in entities))

        # Embed
        vector_store.add_chunks(repo_id, chunks)

        # Static analysis
        py_files = []
        for root, dirs, files in os.walk(temp_dir):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "venv", ".venv", "node_modules"}]
            for f in files:
                if f.endswith(".py"):
                    fp = os.path.join(root, f)
                    try:
                        with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                            py_files.append({"file_path": fp, "content": fh.read()})
                    except Exception:
                        pass

        smells   = smell_detector.detect_in_codebase(py_files)
        bugs     = bug_detector.detect_in_directory(temp_dir)
        patterns = pattern_detector.detect_in_directory(temp_dir)
        debt     = calculate_technical_debt(smells, bugs, total_loc, file_count)

        architecture = ArchitectureSummary(
            components=[],
            entry_points=analyzer.find_entry_points(),
            dependencies=analyzer.get_architecture_graph(),
            total_lines_of_code=total_loc,
            file_count=file_count,
        )

        metadata = {
            "url":          repo_input.repo_url,
            "analyzed_at":  datetime.now().isoformat(),
            "entity_count": len(entities),
            "chunk_count":  len(chunks),
            "architecture": architecture.model_dump(),
            "smells":       [s.model_dump() for s in smells],
            "bugs":         [b.model_dump() for b in bugs],
            "patterns":     [p.model_dump() for p in patterns],
            "debt":         debt.model_dump(),
        }
        analyzed_repos[repo_id] = metadata
        save_analysis_cache(repo_id, metadata, CACHE_DIR)

        background_tasks.add_task(_safe_rmtree, temp_dir)

        return {
            "status":         "success",
            "repo_id":        repo_id,
            "entities_found": len(entities),
            "chunks_indexed": len(chunks),
            "bugs_found":     len(bugs),
            "smells_found":   len(smells),
            "patterns_found": len(patterns),
            "debt_grade":     debt.grade,
            "debt_score":     debt.score,
            "architecture":   architecture,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))


# ── Q&A ─────────────────────────────────────────────────────────
@app.post("/query")
async def query_codebase(qa_query: QAQuery):
    _require_repo(qa_query.repo_id)
    try:
        result = rag_system.answer_question(qa_query.repo_id, qa_query.question, qa_query.context_depth)
        return QAResponse(question=result["question"], answer=result["answer"],
                          relevant_chunks=[], confidence=result["confidence"],
                          learning_resources=result.get("learning_resources", []))
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Repositories ─────────────────────────────────────────────────
@app.get("/repositories")
async def list_repositories():
    return {
        "repositories": [
            {
                "repo_id":      rid,
                "url":          m.get("url"),
                "analyzed_at":  m.get("analyzed_at"),
                "entity_count": m.get("entity_count", 0),
                "chunk_count":  m.get("chunk_count", 0),
                "debt_grade":   m.get("debt", {}).get("grade", "?"),
            }
            for rid, m in analyzed_repos.items()
        ]
    }


@app.get("/repository/{repo_id}")
async def get_repository(repo_id: str):
    _require_repo(repo_id)
    return {"repo_id": repo_id, **analyzed_repos[repo_id]}


@app.delete("/repository/{repo_id}")
async def delete_repository(repo_id: str):
    _require_repo(repo_id)
    vector_store.clear_repository(repo_id)
    del analyzed_repos[repo_id]
    cf = os.path.join(CACHE_DIR, f"{repo_id}.json")
    if os.path.exists(cf):
        os.remove(cf)
    return {"status": "deleted", "repo_id": repo_id}


# ── Analysis endpoints ───────────────────────────────────────────
@app.get("/bugs/{repo_id}")
async def get_bugs(repo_id: str):
    _require_repo(repo_id)
    return {"repo_id": repo_id, "bugs": analyzed_repos[repo_id].get("bugs", [])}


@app.get("/smells/{repo_id}")
async def get_smells(repo_id: str):
    _require_repo(repo_id)
    return {"repo_id": repo_id, "smells": analyzed_repos[repo_id].get("smells", [])}


@app.get("/patterns/{repo_id}")
async def get_patterns(repo_id: str):
    _require_repo(repo_id)
    return {"repo_id": repo_id, "patterns": analyzed_repos[repo_id].get("patterns", [])}


@app.get("/debt/{repo_id}")
async def get_debt(repo_id: str):
    _require_repo(repo_id)
    return {"repo_id": repo_id, "debt": analyzed_repos[repo_id].get("debt", {})}


@app.get("/dependency-graph/{repo_id}")
async def get_dependency_graph(repo_id: str):
    _require_repo(repo_id)
    arch = analyzed_repos[repo_id].get("architecture", {})
    deps = arch.get("dependencies", {})
    # Build nodes + edges for frontend graph rendering
    nodes = [{"id": name, "label": name} for name in deps]
    edges = []
    for src, targets in deps.items():
        for tgt in (targets or []):
            if tgt in deps:
                edges.append({"from": src, "to": tgt})
    return {"nodes": nodes[:80], "edges": edges[:200]}


# ── AI-powered endpoints ─────────────────────────────────────────
@app.post("/explain/{repo_id}")
async def explain_entity(repo_id: str, entity_name: str):
    _require_repo(repo_id)
    result = rag_system.explain_code(repo_id, entity_name)
    return {"entity": entity_name, "explanation": result["answer"], "confidence": result["confidence"],
            "learning_resources": result.get("learning_resources", [])}


@app.post("/find/{repo_id}")
async def find_implementation(repo_id: str, feature: str):
    _require_repo(repo_id)
    result = rag_system.find_implementation(repo_id, feature)
    return {"feature": feature, "implementation": result["answer"], "confidence": result["confidence"],
            "learning_resources": result.get("learning_resources", [])}


@app.post("/refactor/{repo_id}")
async def refactor_suggestions(repo_id: str):
    _require_repo(repo_id)
    result = rag_system.suggest_refactoring(repo_id)
    return {"suggestions": result["answer"], "confidence": result["confidence"]}


@app.post("/generate-tests/{repo_id}")
async def generate_tests(repo_id: str, entity_name: str):
    _require_repo(repo_id)
    result = rag_system.generate_unit_tests(repo_id, entity_name)
    return result


@app.get("/architecture-summary/{repo_id}")
async def architecture_summary(repo_id: str):
    _require_repo(repo_id)
    result = rag_system.generate_architecture_summary(repo_id)
    return {"repo_id": repo_id, **result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
