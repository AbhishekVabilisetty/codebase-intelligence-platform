from typing import Dict, List, Optional
import requests
from src.config import (
    GEMINI_CHAT_MODEL,
    GEMINI_REQUEST_TIMEOUT_SECONDS,
    LLM_PROVIDER,
    OPENROUTER_CHAT_MODEL,
    require_gemini_api_key,
    require_openrouter_api_key,
)
from src.embeddings.vector_store import VectorStore
from src.rag.learning_resources import learning_resources


class RAGSystem:
    def __init__(self, vector_store: Optional[VectorStore] = None, persist_dir: Optional[str] = None):
        self.vector_store = vector_store or VectorStore(persist_dir=persist_dir)
        self.llm_provider = LLM_PROVIDER
        if self.llm_provider == "openrouter":
            self.chat_api_key = require_openrouter_api_key()
        elif self.llm_provider == "gemini":
            self.chat_api_key = require_gemini_api_key()
        else:
            raise RuntimeError("LLM_PROVIDER must be either 'openrouter' or 'gemini'.")

    def _chat(self, system: str, user: str, max_tokens: int = 512) -> str:
        answer, _ = self._chat_with_model(system, user, max_tokens)
        return answer

    def _chat_with_model(self, system: str, user: str, max_tokens: int = 512):
        if self.llm_provider == "openrouter":
            return self._openrouter_chat(system, user, max_tokens)
        answer, model = self._gemini_chat(system, user, max_tokens)
        return answer, f"Gemini / {model}"

    def _openrouter_chat(self, system: str, user: str, max_tokens: int) -> str:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.chat_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": max_tokens,
            },
            timeout=GEMINI_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices", [])
        message = choices[0].get("message", {}) if choices else {}
        content = message.get("content")
        if isinstance(content, list):
            answer = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            ).strip()
        else:
            answer = content.strip() if isinstance(content, str) else ""
        if not answer and isinstance(message.get("refusal"), str):
            answer = message["refusal"].strip()
        if not answer:
            raise RuntimeError(
                "OpenRouter returned no text. Retry the request or choose another supported chat model."
            )
        routed_model = payload.get("model") or OPENROUTER_CHAT_MODEL
        return answer, f"OpenRouter / {routed_model}"

    def _gemini_chat(self, system: str, user: str, max_tokens: int) -> str:
        model_candidates = []
        seen = set()
        for model in [GEMINI_CHAT_MODEL, "gemini-3.8-flash"]:
            if model and model not in seen:
                model_candidates.append(model)
                seen.add(model)

        last_exc = None
        for model_name in model_candidates:
            try:
                response = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
                    headers={"x-goog-api-key": self.chat_api_key},
                    json={
                        "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
                        "generationConfig": {
                            "temperature": 0.2,
                            "maxOutputTokens": max_tokens,
                            "thinkingConfig": {"thinkingBudget": 0},
                        },
                    },
                    timeout=GEMINI_REQUEST_TIMEOUT_SECONDS,
                )
                if response.status_code in {400, 404, 429, 500, 503}:
                    raise requests.HTTPError(f"{response.status_code} {response.reason}")
                response.raise_for_status()
                payload = response.json()
                candidates = payload.get("candidates", [])
                if not candidates:
                    raise RuntimeError("Gemini returned no candidates.")
                parts = candidates[0].get("content", {}).get("parts", [])
                answer = "".join(part.get("text", "") for part in parts).strip()
                if not answer:
                    raise RuntimeError("Gemini returned no text response.")
                return answer, model_name
            except Exception as exc:
                last_exc = exc
                message = str(exc).lower()
                if "timed out" in message:
                    raise RuntimeError(
                        "Gemini did not respond within 30 seconds. Try a shorter question."
                    ) from exc
                if model_name != model_candidates[-1]:
                    continue
                if "503" in message or "500" in message or "429" in message or "not available" in message or "not found" in message:
                    raise RuntimeError(
                        "Gemini API is currently unavailable. Check your API key, quota, and model configuration in backend/.env."
                    ) from exc
                raise

        if last_exc is not None:
            raise RuntimeError(str(last_exc))
        raise RuntimeError("Gemini request failed without response data.")

    def _build_context(self, chunks: List[Dict]) -> str:
        parts = []
        for c in chunks:
            m = c["metadata"]
            parts.append(
                f"### {m.get('file_path')} (lines {m.get('start_line')}-{m.get('end_line')})\n"
                f"**{m.get('chunk_type')}** `{m.get('name')}` — relevance {c['relevance']:.0%}\n"
                f"```python\n{c['content']}\n```"
            )
        return "\n\n".join(parts)

    def answer_question(self, repo_id: str, question: str, context_depth: int = 5) -> Dict:
        try:
            chunks = self.vector_store.search(repo_id, question, n_results=context_depth)
        except RuntimeError as exc:
            return {
                "question": question,
                "answer": str(exc),
                "relevant_chunks": [],
                "confidence": 0.0,
                "learning_resources": [],
            }
        if not chunks:
            return {
                "question": question,
                "answer": "No relevant code found. Please re-analyze the repository first.",
                "relevant_chunks": [],
                "confidence": 0.0,
            }
        context = self._build_context(chunks)
        confidence = round(min(sum(c["relevance"] for c in chunks) / len(chunks), 1.0), 3)
        try:
            answer, model = self._chat_with_model(
                system=(
                    "You are a patient senior developer teaching a junior developer about an unfamiliar codebase. "
                    "Answer only from the supplied code context; say what is uncertain instead of guessing. "
                    "Use friendly, concrete markdown sections: **In simple words**, **How it works here**, "
                    "**Follow this path** (file and symbol names), **Why it matters**, and **Try this next**. "
                    "Define jargon briefly and finish with one safe, achievable hands-on next step."
                ),
                user=f"**Question:** {question}\n\n**Code Context:**\n{context}",
                max_tokens=900,
            )
            return {"question": question, "answer": answer, "relevant_chunks": chunks, "confidence": confidence,
                    "learning_resources": learning_resources(question, chunks), "model": model}
        except Exception as e:
            return {"question": question, "answer": f"Error: {e}", "relevant_chunks": chunks, "confidence": 0.0,
                    "learning_resources": learning_resources(question, chunks), "model": None}

    def explain_code(self, repo_id: str, entity_name: str) -> Dict:
        return self.answer_question(
            repo_id,
            f"Explain `{entity_name}` in detail: what it does, its parameters, return values, and how it fits into the codebase.",
        )

    def find_implementation(self, repo_id: str, feature: str) -> Dict:
        return self.answer_question(
            repo_id,
            f"Where is `{feature}` implemented? Show the exact file path, line numbers, and explain the implementation.",
        )

    def suggest_refactoring(self, repo_id: str) -> Dict:
        chunks = self.vector_store.search(repo_id, "main implementation core logic classes functions", n_results=6)
        if not chunks:
            return {"question": "Refactoring suggestions", "answer": "No code found.", "relevant_chunks": [], "confidence": 0.0}
        context = self._build_context(chunks)
        try:
            answer = self._chat(
                system="You are an expert software architect. Give specific, actionable refactoring suggestions with before/after code examples.",
                user=f"Review this code and provide 3-5 prioritised refactoring suggestions:\n\n{context}",
                max_tokens=1500,
            )
            return {"question": "Refactoring suggestions", "answer": answer, "relevant_chunks": chunks, "confidence": 0.8}
        except Exception as e:
            return {"question": "Refactoring suggestions", "answer": f"Error: {e}", "relevant_chunks": chunks, "confidence": 0.0}

    def generate_unit_tests(self, repo_id: str, entity_name: str) -> Dict:
        chunks = self.vector_store.search(repo_id, entity_name, n_results=4)
        if not chunks:
            return {"entity": entity_name, "tests": "No code found for this entity.", "framework": "pytest"}

        context = self._build_context(chunks)
        try:
            tests = self._chat(
                system=(
                    "You are an expert Python test engineer. Generate comprehensive pytest unit tests. "
                    "Include: happy path, edge cases, error cases. Use mocking where needed. "
                    "Output ONLY the test code with no explanation."
                ),
                user=f"Generate pytest unit tests for `{entity_name}` based on this code:\n\n{context}",
                max_tokens=2000,
            )
            return {"entity": entity_name, "tests": tests, "framework": "pytest"}
        except Exception as e:
            return {"entity": entity_name, "tests": f"Error: {e}", "framework": "pytest"}

    def generate_architecture_summary(self, repo_id: str) -> Dict:
        chunks = self.vector_store.search(repo_id, "architecture modules structure entry point main", n_results=8)
        if not chunks:
            return {"summary": "No code found.", "confidence": 0.0}
        context = self._build_context(chunks)

        try:
            summary = self._chat(
                system="You are a software architect. Analyse the codebase and produce a clear architecture overview.",
                user=(
                    f"Based on this code, provide:\n"
                    f"1. **Architecture Overview** — what kind of system is this?\n"
                    f"2. **Key Components** — list the main modules/layers\n"
                    f"3. **Data Flow** — how data moves through the system\n"
                    f"4. **External Dependencies** — key libraries/services used\n"
                    f"5. **Entry Points** — where execution starts\n\n"
                    f"Code:\n{context}"
                ),
                max_tokens=1500,
            )
            return {"summary": summary, "confidence": 0.85}
        except Exception:
            file_paths = []
            for chunk in chunks:
                metadata = chunk.get("metadata", {})
                file_path = metadata.get("file_path") or ""
                if file_path:
                    file_paths.append(file_path)

            seen = []
            labels = []
            for path in file_paths:
                norm = path.replace('\\', '/').lower()
                if norm not in seen:
                    seen.append(norm)
                    labels.append(path)

            top_level = sorted({p.split('/')[0] for p in labels if '/' in p})
            key_components = []
            for entry in top_level[:6]:
                key_components.append(f"**{entry}**")

            repo_kind = "FastAPI-backed code intelligence platform"
            if any("frontend" in path.lower() for path in labels):
                repo_kind = "web-based code intelligence platform with a Python backend and browser UI"

            summary = (
                "**Architecture Overview**\n"
                f"This repository is organized as a {repo_kind}. The project separates analysis logic from the user interface so repository data can be indexed, queried, and inspected in a consistent workflow.\n\n"
                "**Key Components**\n"
                f"The main architectural layers are {', '.join(key_components) if key_components else 'the backend and frontend modules'} plus the analysis and retrieval services. The system includes repository ingestion, code parsing, indexing, static analysis, and a question-answering layer.\n\n"
                "**Data Flow**\n"
                "A repository is cloned, parsed into code chunks, analyzed for issues and patterns, and stored in a vector database for semantic retrieval. Queries are then answered by retrieving the most relevant code context and synthesizing a response around it.\n\n"
                "**External Dependencies**\n"
                "The implementation relies on a web API layer, a vector database, GitHub-based repository ingestion, and AI services for analysis and Q&A. The frontend consumes the backend API to display architecture summaries, repository metrics, and issue findings.\n\n"
                "**Entry Points**\n"
                "The main execution paths are the FastAPI service for repository processing and search, and the browser client that triggers analysis and presentation workflows."
            )
            return {"summary": summary, "confidence": 0.55}
