from typing import Dict, List, Optional
import requests
from src.config import (
    GEMINI_CHAT_MODEL,
    GEMINI_REQUEST_TIMEOUT_SECONDS,
    require_gemini_api_key,
)
from src.embeddings.vector_store import VectorStore
from src.rag.learning_resources import learning_resources


class RAGSystem:
    def __init__(self, vector_store: Optional[VectorStore] = None, persist_dir: Optional[str] = None):
        self.vector_store = vector_store or VectorStore(persist_dir=persist_dir)
        self.gemini_api_key = require_gemini_api_key()

    def _chat(self, system: str, user: str, max_tokens: int = 512) -> str:
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_CHAT_MODEL}:generateContent",
                headers={"x-goog-api-key": self.gemini_api_key},
                json={
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens},
                },
                timeout=GEMINI_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            answer = "".join(part.get("text", "") for part in parts).strip()
            if not answer:
                raise RuntimeError("Gemini returned no text response.")
            return answer
        except Exception as exc:
            message = str(exc)
            if "timed out" in message.lower():
                raise RuntimeError(
                    "Gemini did not respond within 30 seconds. Try a shorter question."
                ) from exc
            raise

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
            answer = self._chat(
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
                    "learning_resources": learning_resources(question, chunks)}
        except Exception as e:
            return {"question": question, "answer": f"Error: {e}", "relevant_chunks": chunks, "confidence": 0.0,
                    "learning_resources": learning_resources(question, chunks)}

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
        except Exception as e:
            return {"summary": f"Error: {e}", "confidence": 0.0}
