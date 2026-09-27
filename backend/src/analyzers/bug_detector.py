import ast
import os
from typing import List
from src.models import BugReport


class BugDetector:
    """Static analysis bug detector using Python AST."""

    def detect_in_directory(self, directory: str) -> List[BugReport]:
        bugs = []
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "venv", ".venv", "node_modules"}]
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                            src = fh.read()
                        bugs.extend(self._analyze(path, src))
                    except Exception:
                        pass
        bugs.sort(key=lambda b: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(b.severity, 4))
        return bugs[:60]

    def _analyze(self, path: str, src: str) -> List[BugReport]:
        bugs: List[BugReport] = []
        try:
            tree = ast.parse(src)
        except SyntaxError:
            return bugs

        self._bare_except(tree, path, bugs)
        self._mutable_default_arg(tree, path, bugs)
        self._unused_variable(tree, path, bugs)
        self._division_by_zero(tree, path, bugs)
        self._none_comparison(tree, path, bugs)
        self._broad_exception_raise(tree, path, bugs)
        self._missing_return(tree, path, bugs)
        self._shadowed_builtin(tree, path, bugs)
        return bugs

    # ── individual checks ──────────────────────────────────────

    def _bare_except(self, tree, path, bugs):
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                bugs.append(BugReport(
                    type="bare_except",
                    severity="high",
                    file_path=path,
                    line_number=node.lineno,
                    description="Bare `except:` catches ALL exceptions including KeyboardInterrupt and SystemExit.",
                    suggestion="Use `except Exception as e:` or catch specific exception types.",
                ))

    def _mutable_default_arg(self, tree, path, bugs):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        bugs.append(BugReport(
                            type="mutable_default_argument",
                            severity="high",
                            file_path=path,
                            line_number=node.lineno,
                            description=f"Function `{node.name}` uses a mutable default argument. It is shared across all calls.",
                            suggestion="Use `None` as default and initialise inside the function body.",
                        ))

    def _unused_variable(self, tree, path, bugs):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assigned = {}
                used = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Assign):
                        for t in child.targets:
                            if isinstance(t, ast.Name) and not t.id.startswith("_"):
                                assigned[t.id] = child.lineno
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                        used.add(child.id)
                for var, lineno in assigned.items():
                    if var not in used:
                        bugs.append(BugReport(
                            type="unused_variable",
                            severity="low",
                            file_path=path,
                            line_number=lineno,
                            description=f"Variable `{var}` is assigned but never used in `{node.name}`.",
                            suggestion=f"Remove the assignment or prefix with `_` if intentionally unused.",
                        ))

    def _division_by_zero(self, tree, path, bugs):
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                if isinstance(node.right, ast.Constant) and node.right.value == 0:
                    bugs.append(BugReport(
                        type="division_by_zero",
                        severity="critical",
                        file_path=path,
                        line_number=node.lineno,
                        description="Literal division by zero detected.",
                        suggestion="Check the divisor before performing division.",
                    ))

    def _none_comparison(self, tree, path, bugs):
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                for op, comp in zip(node.ops, node.comparators):
                    if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant) and comp.value is None:
                        bugs.append(BugReport(
                            type="none_comparison",
                            severity="medium",
                            file_path=path,
                            line_number=node.lineno,
                            description="Comparing to None with `==` or `!=` instead of `is` / `is not`.",
                            suggestion="Use `x is None` or `x is not None`.",
                        ))

    def _broad_exception_raise(self, tree, path, bugs):
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and node.exc is not None:
                exc = node.exc
                name = None
                if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                    name = exc.func.id
                elif isinstance(exc, ast.Name):
                    name = exc.id
                if name == "Exception":
                    bugs.append(BugReport(
                        type="broad_exception",
                        severity="low",
                        file_path=path,
                        line_number=node.lineno,
                        description="Raising a generic `Exception`. Use a specific exception type.",
                        suggestion="Create a custom exception class or use a built-in specific one.",
                    ))

    def _missing_return(self, tree, path, bugs):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                returns = [n for n in ast.walk(node) if isinstance(n, ast.Return) and n.value is not None]
                all_returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                if returns and len(all_returns) != len(returns):
                    bugs.append(BugReport(
                        type="inconsistent_return",
                        severity="medium",
                        file_path=path,
                        line_number=node.lineno,
                        description=f"Function `{node.name}` has paths that return a value and paths that don't.",
                        suggestion="Ensure all code paths return a value or none of them do.",
                    ))

    def _shadowed_builtin(self, tree, path, bugs):
        builtins = {"list", "dict", "set", "tuple", "str", "int", "float", "bool", "type", "id", "input", "print", "open", "len", "range", "map", "filter", "zip"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args:
                    if arg.arg in builtins:
                        bugs.append(BugReport(
                            type="shadowed_builtin",
                            severity="medium",
                            file_path=path,
                            line_number=node.lineno,
                            description=f"Parameter `{arg.arg}` in `{node.name}` shadows a Python built-in.",
                            suggestion=f"Rename the parameter to avoid shadowing `{arg.arg}`.",
                        ))
