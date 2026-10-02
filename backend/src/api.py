import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import re
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
from src.graphrag.code_graph import build_code_graph
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


def _validate_github_url(repo_url: str):
    from urllib.parse import urlparse
    parsed = urlparse(repo_url)
    if parsed.scheme != "https" or not re.fullmatch(r"(www\.)?github\.com", parsed.netloc or ""):
        raise HTTPException(400, "Only public https://github.com URLs are accepted.")
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise HTTPException(400, "URL must point to a GitHub repository (user/repo).")


def _clone_repository(repo_url: str, branch: str, destination: str):
    _validate_github_url(repo_url)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "-b", branch, repo_url, destination],
            check=True, capture_output=True, timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(400, f"Clone failed: {exc.stderr.decode()}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(408, "Clone timed out") from exc


def _collect_python_files(directory: str):
    python_files = []
    ignored = {".git", "__pycache__", "venv", ".venv", "node_modules"}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [name for name in dirs if name not in ignored]
        for filename in files:
            if not filename.endswith(".py"):
                continue
            file_path = os.path.join(root, filename)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as source:
                    python_files.append({"file_path": file_path, "content": source.read()})
            except OSError:
                continue
    return python_files


def _index_repository(repo_id: str, directory: str):
    analyzer = CodebaseAnalyzer(directory)
    entities, chunks = analyzer.analyze()
    if not chunks:
        raise HTTPException(400, "No supported source files found (Python / JS / TS)")
    vector_store.add_chunks(repo_id, chunks)
    total_lines = sum(len(chunk.content.splitlines()) for chunk in chunks)
    file_count = len({entity.file_path for entity in entities})
    return analyzer, entities, chunks, total_lines, file_count


def _run_repository_checks(directory: str, total_lines: int, file_count: int):
    smells = smell_detector.detect_in_codebase(_collect_python_files(directory))
    bugs = bug_detector.detect_in_directory(directory)
    patterns = pattern_detector.detect_in_directory(directory)
    debt = calculate_technical_debt(smells, bugs, total_lines, file_count)
    return smells, bugs, patterns, debt


def _save_repository_analysis(repo_input, repo_id, analyzer, entities, chunks, checks, total_lines, file_count):
    smells, bugs, patterns, debt = checks
    architecture = ArchitectureSummary(
        components=[], entry_points=analyzer.find_entry_points(),
        dependencies=analyzer.get_architecture_graph(), total_lines_of_code=total_lines, file_count=file_count,
    )
    metadata = {
        "url": repo_input.repo_url, "branch": repo_input.branch, "analyzed_at": datetime.now().isoformat(),
        "entity_count": len(entities), "chunk_count": len(chunks), "architecture": architecture.model_dump(),
        "smells": [smell.model_dump() for smell in smells], "bugs": [bug.model_dump() for bug in bugs],
        "patterns": [pattern.model_dump() for pattern in patterns], "debt": debt.model_dump(),
        "code_graph": build_code_graph(entities),
    }
    analyzed_repos[repo_id] = metadata
    save_analysis_cache(repo_id, metadata, CACHE_DIR)
    return metadata, debt, architecture


def _analysis_response(status: str, repo_id: str, metadata: dict, debt, architecture):
    return {
        "status": status, "repo_id": repo_id, "entities_found": metadata.get("entity_count", 0),
        "chunks_indexed": metadata.get("chunk_count", 0), "bugs_found": len(metadata.get("bugs", [])),
        "smells_found": len(metadata.get("smells", [])), "patterns_found": len(metadata.get("patterns", [])),
        "debt_grade": debt.get("grade", "?") if isinstance(debt, dict) else debt.grade,
        "debt_score": debt.get("score", 0) if isinstance(debt, dict) else debt.score,
        "graph_nodes": len(metadata.get("code_graph", {}).get("nodes", [])),
        "graph_edges": len(metadata.get("code_graph", {}).get("edges", [])),
        "architecture": architecture,
    }


# ── Health ──────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "running", "version": "3.0.0", "repos_loaded": len(analyzed_repos)}


# ── Analyze ─────────────────────────────────────────────────────
@app.post("/analyze")
async def analyze_repository(repo_input: RepositoryInput, background_tasks: BackgroundTasks):
    repo_id = repo_input.repo_url.rstrip("/").split("/")[-1]
    temp_dir = os.path.join(TEMP_DIR, repo_id)
    cached = analyzed_repos.get(repo_id)
    if (
        cached
        and not repo_input.force_reindex
        and cached.get("url", "").rstrip("/") == repo_input.repo_url.rstrip("/")
    ):
        return _analysis_response("cached", repo_id, cached, cached.get("debt", {}), cached.get("architecture", {}))

    if os.path.exists(temp_dir):
        _safe_rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    try:
        _clone_repository(repo_input.repo_url, repo_input.branch, temp_dir)
        analyzer, entities, chunks, total_lines, file_count = _index_repository(repo_id, temp_dir)
        checks = _run_repository_checks(temp_dir, total_lines, file_count)
        metadata, debt, architecture = _save_repository_analysis(
            repo_input, repo_id, analyzer, entities, chunks, checks, total_lines, file_count,
        )
        background_tasks.add_task(_safe_rmtree, temp_dir)
        return _analysis_response("success", repo_id, metadata, debt, architecture)
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(exc)) from exc


# ── Q&A ─────────────────────────────────────────────────────────
@app.post("/query")
async def query_codebase(qa_query: QAQuery):
    _require_repo(qa_query.repo_id)
    try:
        result = rag_system.answer_question(
            qa_query.repo_id, qa_query.question, qa_query.context_depth,
            analyzed_repos[qa_query.repo_id].get("code_graph"),
        )
        return QAResponse(question=result["question"], answer=result["answer"],
                          relevant_chunks=[], confidence=result["confidence"],
                          learning_resources=result.get("learning_resources", []),
                          model=result.get("model"))
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
                "branch":       m.get("branch", "main"),
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
    """Return the complete indexed code graph for interactive exploration."""
    _require_repo(repo_id)
    graph = analyzed_repos[repo_id].get("code_graph", {})
    source_nodes = graph.get("nodes", [])
    source_edges = graph.get("edges", [])
    if not source_nodes:
        raise HTTPException(409, "No code graph exists for this repository. Rebuild its search index first.")

    # Imports tend to create dense, low-signal graphs. Keep the view useful for
    # implementation review while retaining file-to-symbol ownership edges.
    visible_nodes = [
        node for node in source_nodes
        if node.get("kind") == "file" or node.get("entity_type") != "import"
    ]
    visible_ids = {node["id"] for node in visible_nodes}
    visible_edges = [
        edge for edge in source_edges
        if edge.get("source") in visible_ids and edge.get("target") in visible_ids
    ]

    def display_node(node):
        is_file = node.get("kind") == "file"
        return {
            "id": node["id"],
            "label": os.path.basename(node.get("file_path", "")) if is_file else node.get("name", "Unknown"),
            "kind": "file" if is_file else "symbol",
            "symbol_type": node.get("entity_type", ""),
            "file_path": node.get("file_path", ""),
            "line_number": node.get("line_number"),
        }

    return {
        "repo_id": repo_id,
        "nodes": [display_node(node) for node in visible_nodes],
        "edges": [
            {"from": edge["source"], "to": edge["target"], "type": edge.get("type", "RELATED")}
            for edge in visible_edges
        ],
        "meta": {
            "node_count": len(visible_nodes),
            "edge_count": len(visible_edges),
            "excluded_imports": len(source_nodes) - len(visible_nodes),
        },
    }


@app.get("/change-risk/{repo_id}")
async def get_change_risk(repo_id: str, entity_id: str):
    """Return an explainable, static-analysis risk review for one indexed symbol."""
    _require_repo(repo_id)
    graph = analyzed_repos[repo_id].get("code_graph", {})
    nodes = {node.get("id"): node for node in graph.get("nodes", [])}
    selected = nodes.get(entity_id)
    if not selected or selected.get("kind") != "entity":
        raise HTTPException(404, "The selected symbol is not available in this repository graph.")

    use_edges = [edge for edge in graph.get("edges", []) if edge.get("type") == "USES"]
    dependencies = [nodes[edge["target"]] for edge in use_edges if edge["source"] == entity_id and edge["target"] in nodes]
    dependents = [nodes[edge["source"]] for edge in use_edges if edge["target"] == entity_id and edge["source"] in nodes]
    related_ids = {node["id"] for node in dependencies + dependents}
    affected_files = list(dict.fromkeys(
        [selected.get("file_path", "")] + [node.get("file_path", "") for node in dependencies + dependents]
    ))
    affected_files = [path for path in affected_files if path]
    issues = [
        issue for issue in analyzed_repos[repo_id].get("bugs", []) + analyzed_repos[repo_id].get("smells", [])
        if issue.get("file_path") in affected_files
    ]
    severity_weight = {"critical": 24, "high": 16, "medium": 8, "low": 3}
    issue_weight = min(24, sum(severity_weight.get(issue.get("severity", "low"), 3) for issue in issues))
    dependency_weight = min(36, len(dependents) * 12)
    coupling_weight = min(22, len(related_ids) * 6)
    public_weight = 10 if selected.get("is_public", True) else 0
    score = min(100, dependency_weight + coupling_weight + issue_weight + public_weight)
    level = "high" if score >= 60 else "medium" if score >= 30 else "low"

    def symbol(node):
        return {
            "id": node["id"], "name": node.get("name", "Unknown"),
            "kind": node.get("entity_type", "symbol"), "file_path": node.get("file_path", ""),
            "line_number": node.get("line_number"),
        }

    evidence = [
        {"label": "Direct callers", "value": len(dependents), "weight": dependency_weight,
         "detail": "Callers may require regression testing when this symbol changes."},
        {"label": "Connected symbols", "value": len(related_ids), "weight": coupling_weight,
         "detail": "Direct uses and dependencies increase coordination risk."},
        {"label": "Existing findings", "value": len(issues), "weight": issue_weight,
         "detail": "Open static-analysis findings exist in affected files."},
    ]
    checklist = [
        "Review the current contract and inputs for " + selected.get("name", "this symbol") + ".",
        "Add or update a focused unit test for the changed behaviour.",
    ]
    if dependents:
        checklist.append("Regression-test the " + str(len(dependents)) + " direct caller(s) identified in the graph.")
    if issues:
        checklist.append("Resolve or explicitly account for " + str(len(issues)) + " existing finding(s) in affected files.")
    checklist.append("Run the relevant test suite and validate behaviour in the configured environment.")

    return {
        "repo_id": repo_id, "selected": symbol(selected), "risk": {"score": score, "level": level},
        "evidence": evidence, "dependencies": [symbol(node) for node in dependencies],
        "dependents": [symbol(node) for node in dependents], "affected_files": affected_files[:8],
        "findings": issues[:8], "checklist": checklist,
        "scope": "Static source analysis; dynamic dispatch and runtime configuration are not included.",
    }


@app.get("/impact-explorer/{repo_id}")
async def get_impact_explorer(repo_id: str, focus: str = "", hops: int = 1):
    """Return a small, actionable neighbourhood instead of an unreadable full graph."""
    _require_repo(repo_id)
    graph = analyzed_repos[repo_id].get("code_graph", {})
    entity_nodes = [node for node in graph.get("nodes", []) if node.get("kind") == "entity"]
    if not entity_nodes:
        raise HTTPException(409, "No code graph exists for this repository. Rebuild its search index first.")

    def describe(node):
        return {
            "id": node["id"], "name": node.get("name") or os.path.basename(node.get("file_path", "")),
            "kind": node.get("entity_type") or node.get("kind"), "file_path": node.get("file_path", ""),
            "line_number": node.get("line_number"),
        }

    candidates = sorted(
        [describe(node) for node in entity_nodes
         if node.get("entity_type") in {"function", "method", "class", "export"}
         and not node.get("name", "").startswith("_")],
        key=lambda item: (item["name"].lower(), item["file_path"], item.get("line_number") or 0),
    )[:300]
    if not candidates:
        candidates = sorted(
            [describe(node) for node in entity_nodes if node.get("entity_type") in {"function", "method", "class", "export"}],
            key=lambda item: (item["name"].lower(), item["file_path"], item.get("line_number") or 0),
        )[:300]
    focus_key = focus.strip().lower()
    selected = next((node for node in entity_nodes if node["id"] == focus), None)
    if selected is None and focus_key:
        selected = next((node for node in entity_nodes if node.get("name", "").lower() == focus_key), None)
    if selected is None:
        selected = next((node for node in entity_nodes if node["id"] == candidates[0]["id"]), entity_nodes[0])

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    use_edges = [edge for edge in graph.get("edges", []) if edge.get("type") == "USES"]
    adjacency = {}
    for edge in use_edges:
        adjacency.setdefault(edge["source"], []).append(edge["target"])
        adjacency.setdefault(edge["target"], []).append(edge["source"])

    # Bounded, undirected neighbourhood: callers and callees are both important
    # for understanding a change's impact.
    max_hops = max(1, min(hops, 2))
    included, frontier = {selected["id"]}, {selected["id"]}
    for _ in range(max_hops):
        next_frontier = {target for source in frontier for target in adjacency.get(source, [])}
        next_frontier -= included
        included.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break

    related_symbol_count = len(included) - 1
    for node_id in list(included):
        node = nodes_by_id[node_id]
        included.add(f"file:{node.get('file_path')}")
    visible_edges = [edge for edge in graph.get("edges", []) if edge.get("source") in included and edge.get("target") in included]
    dependencies = [describe(nodes_by_id[edge["target"]]) for edge in use_edges if edge["source"] == selected["id"]]
    dependents = [describe(nodes_by_id[edge["source"]]) for edge in use_edges if edge["target"] == selected["id"]]

    return {
        "selected": describe(selected), "hops": max_hops, "available_entities": candidates,
        "nodes": [describe(nodes_by_id[node_id]) for node_id in included if node_id in nodes_by_id],
        "edges": [{"from": edge["source"], "to": edge["target"], "type": edge["type"]} for edge in visible_edges],
        "dependencies": dependencies, "dependents": dependents,
        "impact": {"direct_dependents": len(dependents), "related_symbols": related_symbol_count},
    }


# ── AI-powered endpoints ─────────────────────────────────────────
@app.post("/explain/{repo_id}")
async def explain_entity(repo_id: str, entity_name: str):
    _require_repo(repo_id)
    result = rag_system.explain_code(repo_id, entity_name, analyzed_repos[repo_id].get("code_graph"))
    return {"entity": entity_name, "explanation": result["answer"], "confidence": result["confidence"],
            "learning_resources": result.get("learning_resources", []), "model": result.get("model")}


@app.post("/find/{repo_id}")
async def find_implementation(repo_id: str, feature: str):
    _require_repo(repo_id)
    result = rag_system.find_implementation(repo_id, feature, analyzed_repos[repo_id].get("code_graph"))
    return {"feature": feature, "implementation": result["answer"], "confidence": result["confidence"],
            "learning_resources": result.get("learning_resources", []), "model": result.get("model")}


@app.post("/refactor/{repo_id}")
async def refactor_suggestions(repo_id: str):
    _require_repo(repo_id)
    result = rag_system.suggest_refactoring(repo_id)
    return {"suggestions": result["answer"], "confidence": result["confidence"], "model": result.get("model")}


@app.post("/generate-tests/{repo_id}")
async def generate_tests(repo_id: str, entity_name: str):
    _require_repo(repo_id)
    result = rag_system.generate_unit_tests(repo_id, entity_name)
    return result


@app.get("/architecture-summary/{repo_id}")
async def architecture_summary(repo_id: str):
    _require_repo(repo_id)
    try:
        result = rag_system.generate_architecture_summary(repo_id)
    except RuntimeError as exc:
        if "older model" in str(exc).lower() or "embedding dimension" in str(exc).lower():
            raise HTTPException(
                409,
                "This repository's search index uses an older embedding model. "
                "Open Repositories and choose Rebuild search index, then retry the summary.",
            ) from exc
        raise HTTPException(503, str(exc)) from exc
    return {"repo_id": repo_id, **result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
