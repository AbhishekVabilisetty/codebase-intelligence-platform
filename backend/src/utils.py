import os
import json
from typing import Dict, Any


def _serialize_for_json(value):
    if hasattr(value, 'dict'):
        return value.dict()
    if isinstance(value, dict):
        return {k: _serialize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_for_json(v) for v in value]
    return value


def save_analysis_cache(repo_id: str, data: Dict, cache_dir: str = "./cache"):
    os.makedirs(cache_dir, exist_ok=True)
    with open(os.path.join(cache_dir, f"{repo_id}.json"), 'w', encoding='utf-8') as f:
        json.dump(_serialize_for_json(data), f, indent=2)


def load_analysis_cache(repo_id: str, cache_dir: str = "./cache") -> Dict:
    path = os.path.join(cache_dir, f"{repo_id}.json")
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}
