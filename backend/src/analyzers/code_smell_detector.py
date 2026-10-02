from typing import List
import ast
from src.models import CodeSmell

class CodeSmellDetector:
    """Detect code smells and anti-patterns"""

    def __init__(self):
        self.smells: List[CodeSmell] = []

    def detect_in_file(self, file_path: str, content: str) -> List[CodeSmell]:
        """Detect code smells in a file"""
        self.smells = []

        try:
            tree = ast.parse(content)
            self._detect_long_functions(tree, file_path, content)
            self._detect_large_classes(tree, file_path, content)
            self._detect_deep_nesting(tree, file_path, content)
            self._detect_complex_methods(tree, file_path, content)
        except SyntaxError:
            pass

        return self.smells

    def _detect_long_functions(self, tree: ast.AST, file_path: str, content: str):
        """Detect functions with too many lines"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                num_lines = (node.end_lineno or node.lineno) - node.lineno

                if num_lines > 50:
                    severity = "high" if num_lines > 100 else "medium"
                    self.smells.append(CodeSmell(
                        type="long_function",
                        severity=severity,
                        file_path=file_path,
                        line_number=node.lineno,
                        description=f"Function '{node.name}' has {num_lines} lines (threshold: 50)",
                        suggestion="Consider refactoring into smaller functions with single responsibility"
                    ))

    def _detect_large_classes(self, tree: ast.AST, file_path: str, content: str):
        """Detect classes with too many methods"""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

                if len(methods) > 15:
                    severity = "high" if len(methods) > 25 else "medium"
                    self.smells.append(CodeSmell(
                        type="large_class",
                        severity=severity,
                        file_path=file_path,
                        line_number=node.lineno,
                        description=f"Class '{node.name}' has {len(methods)} methods (threshold: 15)",
                        suggestion="Consider breaking the class into smaller, more focused classes"
                    ))

    def _detect_deep_nesting(self, tree: ast.AST, file_path: str, content: str):
        """Report the deepest block inside its owning function, not file line 1."""
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            depth, line_number = self._get_max_nesting_depth(function)
            if depth > 4:
                severity = "high" if depth > 6 else "medium"
                self.smells.append(CodeSmell(
                    type="deep_nesting", severity=severity, file_path=file_path,
                    line_number=line_number,
                    description=(f"Function '{function.name}' reaches nesting depth {depth} "
                                 f"(threshold: 4)"),
                    suggestion="Extract the nested branch around this line into a focused helper function"
                ))

    def _detect_complex_methods(self, tree: ast.AST, file_path: str, content: str):
        """Detect methods with high cyclomatic complexity"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexity = self._calculate_cyclomatic_complexity(node)

                if complexity > 10:
                    severity = "high" if complexity > 15 else "medium"
                    self.smells.append(CodeSmell(
                        type="high_complexity",
                        severity=severity,
                        file_path=file_path,
                        line_number=node.lineno,
                        description=f"Method '{node.name}' has cyclomatic complexity of {complexity} (threshold: 10)",
                        suggestion="Consider refactoring with simpler conditionals or extracting logic"
                    ))

    def _get_max_nesting_depth(self, node: ast.AST, depth: int = 0):
        """Return the deepest control-flow depth and the exact source line."""
        nesting_nodes = (ast.If, ast.While, ast.For, ast.AsyncFor, ast.With, ast.AsyncWith, ast.Try, ast.Match)
        current_depth = depth + 1 if isinstance(node, nesting_nodes) else depth
        deepest = (current_depth, getattr(node, "lineno", 1))
        for child in ast.iter_child_nodes(node):
            child_result = self._get_max_nesting_depth(child, current_depth)
            if child_result[0] > deepest[0]:
                deepest = child_result
        return deepest

    def _calculate_cyclomatic_complexity(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity"""
        complexity = 1  # Base complexity

        for sub_node in ast.walk(node):
            if isinstance(sub_node, (ast.If, ast.While, ast.For, ast.And, ast.Or, ast.ExceptHandler)):
                complexity += 1

        return complexity

    def detect_in_codebase(self, entities_with_content: List) -> List[CodeSmell]:
        """Detect smells in entire codebase"""
        all_smells = []

        for entity_with_content in entities_with_content:
            file_path = entity_with_content.get('file_path')
            content = entity_with_content.get('content')

            if file_path and content:
                smells = self.detect_in_file(file_path, content)
                all_smells.extend(smells)

        # Sort by severity
        severity_order = {"high": 0, "medium": 1, "low": 2}
        all_smells.sort(key=lambda s: severity_order.get(s.severity, 3))

        return all_smells[:50]  # Return top 50 issues
