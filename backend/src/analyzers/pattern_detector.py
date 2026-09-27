import ast
import os
from typing import List
from src.models import DesignPattern


class PatternDetector:
    """Detect GoF design patterns using AST analysis."""

    def detect_in_directory(self, directory: str) -> List[DesignPattern]:
        patterns = []
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "venv", ".venv", "node_modules"}]
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                            src = fh.read()
                        tree = ast.parse(src)
                        patterns.extend(self._detect(tree, path))
                    except Exception:
                        pass
        return patterns

    def _detect(self, tree: ast.AST, path: str) -> List[DesignPattern]:
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                found.extend(self._check_singleton(node, path))
                found.extend(self._check_factory(node, path))
                found.extend(self._check_observer(node, path))
                found.extend(self._check_decorator_pattern(node, path))
                found.extend(self._check_strategy(node, path))
                found.extend(self._check_template_method(node, path))
        return found

    def _method_names(self, cls: ast.ClassDef) -> List[str]:
        return [n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    def _check_singleton(self, cls: ast.ClassDef, path: str) -> List[DesignPattern]:
        methods = self._method_names(cls)
        # Look for _instance class variable + getInstance / __new__ override
        has_instance_var = any(
            isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and "_instance" in t.id for t in n.targets
            )
            for n in cls.body
        )
        has_new = "__new__" in methods or "get_instance" in methods or "getInstance" in methods
        if has_instance_var and has_new:
            return [DesignPattern(
                name="Singleton",
                confidence="high",
                file_path=path,
                line_number=cls.lineno,
                description=f"`{cls.name}` restricts instantiation to a single instance via `_instance` + `__new__`/`get_instance`.",
            )]
        return []

    def _check_factory(self, cls: ast.ClassDef, path: str) -> List[DesignPattern]:
        methods = self._method_names(cls)
        factory_keywords = {"create", "make", "build", "factory", "produce", "get"}
        matches = [m for m in methods if any(k in m.lower() for k in factory_keywords)]
        if matches and ("Factory" in cls.name or "Creator" in cls.name or len(matches) >= 2):
            return [DesignPattern(
                name="Factory",
                confidence="medium",
                file_path=path,
                line_number=cls.lineno,
                description=f"`{cls.name}` appears to be a Factory — it has creation methods: {', '.join(matches[:3])}.",
            )]
        return []

    def _check_observer(self, cls: ast.ClassDef, path: str) -> List[DesignPattern]:
        methods = self._method_names(cls)
        has_subscribe = any(m in methods for m in ("subscribe", "attach", "register", "add_listener", "on"))
        has_notify = any(m in methods for m in ("notify", "emit", "dispatch", "publish", "fire"))
        if has_subscribe and has_notify:
            return [DesignPattern(
                name="Observer",
                confidence="high",
                file_path=path,
                line_number=cls.lineno,
                description=f"`{cls.name}` implements the Observer pattern with subscribe/notify methods.",
            )]
        return []

    def _check_decorator_pattern(self, cls: ast.ClassDef, path: str) -> List[DesignPattern]:
        # Decorator pattern: wraps another object of the same base type
        bases = [b.id if isinstance(b, ast.Name) else "" for b in cls.bases]
        has_wrapped = any(
            isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and ("wrapped" in t.id or "component" in t.id or "_inner" in t.id)
                for t in n.targets
            )
            for n in ast.walk(cls)
        )
        if has_wrapped and bases:
            return [DesignPattern(
                name="Decorator",
                confidence="medium",
                file_path=path,
                line_number=cls.lineno,
                description=f"`{cls.name}` wraps another object (Decorator pattern).",
            )]
        return []

    def _check_strategy(self, cls: ast.ClassDef, path: str) -> List[DesignPattern]:
        methods = self._method_names(cls)
        # Abstract base with single execute/run/process method
        has_abstract = any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and
            any(isinstance(d, ast.Name) and d.id == "abstractmethod" for d in ast.walk(n))
            for n in cls.body
        )
        strategy_methods = {"execute", "run", "process", "perform", "handle", "apply", "compute"}
        has_strategy_method = any(m in strategy_methods for m in methods)
        if has_abstract and has_strategy_method:
            return [DesignPattern(
                name="Strategy",
                confidence="medium",
                file_path=path,
                line_number=cls.lineno,
                description=f"`{cls.name}` defines an abstract strategy interface.",
            )]
        return []

    def _check_template_method(self, cls: ast.ClassDef, path: str) -> List[DesignPattern]:
        # Template method: has a public method that calls several private methods
        for node in cls.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                private_calls = [
                    n for n in ast.walk(node)
                    if isinstance(n, ast.Call) and
                    isinstance(n.func, ast.Attribute) and
                    n.func.attr.startswith("_")
                ]
                if len(private_calls) >= 3:
                    return [DesignPattern(
                        name="Template Method",
                        confidence="medium",
                        file_path=path,
                        line_number=cls.lineno,
                        description=f"`{cls.name}.{node.name}` orchestrates multiple private steps — Template Method pattern.",
                    )]
        return []
