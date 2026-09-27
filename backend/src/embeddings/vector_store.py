import os
from typing import Dict, List, Literal, Optional
import chromadb
from openai import OpenAI
from src.config import EMBED_MODEL, NVIDIA_BASE_URL, require_nvidia_api_key

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PERSIST_DIR = os.path.join(BASE_DIR, "chroma_db")


class EmbeddingGenerator:
    def __init__(self):
        self.client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=require_nvidia_api_key(),
        )

    def generate(self, text: str, input_type: Literal["passage", "query"]) -> List[float]:
        """Generate one retrieval embedding in the required NVIDIA mode."""
        text = text[:4000]
        response = self.client.embeddings.create(
            input=[text],
            model=EMBED_MODEL,
            encoding_format="float",
            extra_body={"input_type": input_type, "truncate": "END"},
        )
        return response.data[0].embedding


class VectorStore:
    def __init__(self, persist_dir: Optional[str] = None):
        self.persist_dir = persist_dir or PERSIST_DIR
        os.makedirs(self.persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.embedder = EmbeddingGenerator()

    def _collection_name(self, repo_id: str) -> str:
        return f"repo_{repo_id}".replace("/", "_").replace("-", "_")[:63]

    def get_or_create_collection(self, repo_id: str):
        return self.client.get_or_create_collection(
            name=self._collection_name(repo_id),
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, repo_id: str, chunks: List):
        if not chunks:
            return

        ids, documents, embeddings, metadatas = [], [], [], []
        for i, chunk in enumerate(chunks):
            doc = f"{chunk.chunk_type}: {chunk.name}\n{chunk.description or ''}\n{chunk.content}"
            ids.append(f"{repo_id}_{i}")
            documents.append(doc)
            # Indexed code is a passage; searches are embedded as queries.
            embeddings.append(self.embedder.generate(doc, input_type="passage"))
            metadatas.append({
                "file_path": chunk.file_path,
                "chunk_type": chunk.chunk_type,
                "name": chunk.name or "",
                "start_line": str(chunk.start_line),
                "end_line": str(chunk.end_line),
                "language": chunk.language,
            })

        # Do not discard the current index until replacement embeddings were
        # generated successfully. This keeps a repository searchable if the
        # embedding provider rejects a request or is temporarily unavailable.
        try:
            self.client.delete_collection(self._collection_name(repo_id))
        except Exception:
            pass
        collection = self.get_or_create_collection(repo_id)

        # Add in batches of 50 to avoid request size limits
        batch = 50
        for i in range(0, len(ids), batch):
            collection.add(
                ids=ids[i:i+batch],
                documents=documents[i:i+batch],
                embeddings=embeddings[i:i+batch],
                metadatas=metadatas[i:i+batch],
            )

    def search(self, repo_id: str, query: str, n_results: int = 5) -> List[Dict]:
        collection = self.get_or_create_collection(repo_id)
        count = collection.count()
        if count == 0:
            return []
        n_results = min(n_results, count)
        query_embedding = self.embedder.generate(query, input_type="query")
        try:
            results = collection.query(query_embeddings=[query_embedding], n_results=n_results)
        except Exception as exc:
            if "Embedding dimension" in str(exc):
                raise RuntimeError(
                    "This repository uses embeddings from an older model. "
                    "Re-analyze the repository to rebuild its search index."
                ) from exc
            raise
        formatted = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                dist = results["distances"][0][i]
                formatted.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i],
                    "distance": dist,
                    "relevance": round(max(0.0, 1.0 - dist), 4),
                })
        return formatted

    def clear_repository(self, repo_id: str):
        try:
            self.client.delete_collection(self._collection_name(repo_id))
        except Exception as e:
            print(f"Error clearing {repo_id}: {e}")
