"""Curated learning links selected from a question's retrieved code context."""

from typing import Dict, Iterable, List
from urllib.parse import quote_plus


def _youtube_search(title: str, query: str) -> Dict[str, str]:
    return {"title": title, "type": "YouTube playlist search",
            "url": f"https://www.youtube.com/results?search_query={quote_plus(query + ' playlist')}"}


COMMON_RESOURCES = [
    {"title": "How to read an unfamiliar codebase", "type": "Guide",
     "url": "https://www.freecodecamp.org/news/how-to-read-code/"},
    _youtube_search("Codebase walkthroughs for beginners", "how to understand a codebase for beginners"),
]

LANGUAGE_RESOURCES = {
    "python": [
        {"title": "Python Tutorial", "type": "Official documentation", "url": "https://docs.python.org/3/tutorial/"},
        _youtube_search("Python fundamentals playlists", "python programming for beginners"),
    ],
    "javascript": [
        {"title": "MDN JavaScript Guide", "type": "Documentation", "url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide"},
        _youtube_search("JavaScript fundamentals playlists", "javascript full course for beginners"),
    ],
    "typescript": [
        {"title": "TypeScript Handbook", "type": "Official documentation", "url": "https://www.typescriptlang.org/docs/handbook/intro.html"},
        _youtube_search("TypeScript beginner playlists", "typescript for beginners"),
    ],
}

TOPIC_RESOURCES = {
    "fastapi": [
        {"title": "FastAPI Tutorial", "type": "Official documentation", "url": "https://fastapi.tiangolo.com/tutorial/"},
        _youtube_search("FastAPI beginner playlists", "FastAPI tutorial for beginners"),
    ],
    "react": [
        {"title": "React Learn", "type": "Official documentation", "url": "https://react.dev/learn"},
        _youtube_search("React beginner playlists", "React JS complete course beginners"),
    ],
    "testing": [
        {"title": "pytest: Getting Started", "type": "Documentation", "url": "https://docs.pytest.org/en/stable/getting-started.html"},
        _youtube_search("Unit testing playlists", "unit testing for beginners"),
    ],
    "authentication": [
        {"title": "OWASP Authentication Cheat Sheet", "type": "Security guide", "url": "https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html"},
        _youtube_search("Authentication and JWT playlists", "authentication JWT beginners"),
    ],
}


def learning_resources(question: str, chunks: Iterable[Dict], limit: int = 4) -> List[Dict[str, str]]:
    """Return a concise set of trusted resources; never LLM-invented URLs."""
    chunks = list(chunks)
    resources: List[Dict[str, str]] = []
    languages = {str(c.get("metadata", {}).get("language", "")).lower() for c in chunks}
    haystack = question.lower() + " " + " ".join(str(c.get("content", "")).lower() for c in chunks)
    for language in ("python", "typescript", "javascript"):
        if language in languages:
            resources.extend(LANGUAGE_RESOURCES[language])
    for topic, links in TOPIC_RESOURCES.items():
        if topic in haystack:
            resources.extend(links)
    resources.extend(COMMON_RESOURCES)

    unique, seen = [], set()
    for resource in resources:
        if resource["url"] not in seen:
            unique.append(resource)
            seen.add(resource["url"])
        if len(unique) == limit:
            break
    return unique
