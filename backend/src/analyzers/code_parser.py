import ast
import os
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from src.models import CodeChunk, CodeEntity

class PythonAnalyzer:
    """Analyze Python code and extract structure"""

    def __init__(self):
        self.entities: List[CodeEntity] = []
        self.chunks: List[CodeChunk] = []
        self.current_file = ""

    def analyze_file(self, file_path: str) -> Tuple[List[CodeEntity], List[CodeChunk]]:
        """Analyze a single Python file"""
        self.current_file = file_path
        self.entities = []
        self.chunks = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)
            self._visit_nodes(tree, content)
            # Only add a module chunk if no functions/classes were found
            if not self.chunks:
                self.chunks.append(CodeChunk(
                    file_path=file_path,
                    content=content[:3000],
                    language="python",
                    start_line=1,
                    end_line=len(content.split('\n')),
                    chunk_type="module",
                    name=Path(file_path).stem,
                    description=self._extract_docstring(tree)
                ))

        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")

        return self.entities, self.chunks

    def analyze_directory(self, directory: str) -> Tuple[List[CodeEntity], List[CodeChunk]]:
        """Recursively analyze all Python files in directory"""
        all_entities = []
        all_chunks = []

        for root, dirs, files in os.walk(directory):
            # Skip common non-source directories
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'venv', 'node_modules']]

            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    entities, chunks = self.analyze_file(file_path)
                    all_entities.extend(entities)
                    all_chunks.extend(chunks)

        return all_entities, all_chunks

    def _visit_nodes(self, node: ast.AST, content: str, parent_class: Optional[str] = None):
        """Recursively visit AST nodes and extract entities"""
        lines = content.split('\n')

        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef):
                self._handle_function(child, lines, parent_class)
            elif isinstance(child, ast.ClassDef):
                self._handle_class(child, lines)
            elif isinstance(child, ast.Assign):
                self._handle_assignment(child, lines)

    def _handle_function(self, node: ast.FunctionDef, lines: List[str], parent_class: Optional[str] = None):
        """Extract function information"""
        is_public = not node.name.startswith('_')
        dependencies = self._extract_dependencies(node)

        entity = CodeEntity(
            name=node.name,
            type="method" if parent_class else "function",
            file_path=self.current_file,
            line_number=node.lineno,
            description=self._get_docstring(node),
            dependencies=dependencies,
            is_public=is_public
        )
        self.entities.append(entity)

        # Create chunk for function
        end_line = node.end_lineno or node.lineno
        chunk_content = '\n'.join(lines[node.lineno-1:end_line])

        self.chunks.append(CodeChunk(
            file_path=self.current_file,
            content=chunk_content,
            language="python",
            start_line=node.lineno,
            end_line=end_line,
            chunk_type="function",
            name=node.name,
            description=self._get_docstring(node)
        ))

    def _handle_class(self, node: ast.ClassDef, lines: List[str]):
        """Extract class information and nested methods"""
        is_public = not node.name.startswith('_')
        dependencies = self._extract_dependencies(node)

        entity = CodeEntity(
            name=node.name,
            type="class",
            file_path=self.current_file,
            line_number=node.lineno,
            description=self._get_docstring(node),
            dependencies=dependencies,
            is_public=is_public
        )
        self.entities.append(entity)

        # Create chunk for class
        end_line = node.end_lineno or node.lineno
        chunk_content = '\n'.join(lines[node.lineno-1:end_line])

        self.chunks.append(CodeChunk(
            file_path=self.current_file,
            content=chunk_content,
            language="python",
            start_line=node.lineno,
            end_line=end_line,
            chunk_type="class",
            name=node.name,
            description=self._get_docstring(node)
        ))

        # Visit nested methods
        self._visit_nodes(node, '\n'.join(lines), parent_class=node.name)

    def _handle_assignment(self, node: ast.Assign, lines: List[str]):
        """Extract module-level variables"""
        for target in node.targets:
            if isinstance(target, ast.Name):
                is_public = not target.id.startswith('_')
                entity = CodeEntity(
                    name=target.id,
                    type="variable",
                    file_path=self.current_file,
                    line_number=node.lineno,
                    is_public=is_public
                )
                self.entities.append(entity)

    def _extract_dependencies(self, node: ast.AST) -> List[str]:
        """Extract dependencies (imports, function calls, etc.) from node"""
        dependencies = []

        for sub_node in ast.walk(node):
            if isinstance(sub_node, ast.Call):
                if isinstance(sub_node.func, ast.Name):
                    dependencies.append(sub_node.func.id)
                elif isinstance(sub_node.func, ast.Attribute):
                    dependencies.append(sub_node.func.attr)
            elif isinstance(sub_node, ast.Name):
                if isinstance(sub_node.ctx, ast.Load):
                    dependencies.append(sub_node.id)

        return list(set(dependencies))[:10]  # Return unique, limit to 10

    def _get_docstring(self, node: ast.AST) -> Optional[str]:
        """Extract docstring from node"""
        return ast.get_docstring(node)

    def _extract_docstring(self, node: ast.AST) -> Optional[str]:
        """Extract module-level docstring"""
        return ast.get_docstring(node)


class CodebaseAnalyzer:
    """Main analyzer for entire codebase"""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.python_analyzer = PythonAnalyzer()
        self.all_entities: List[CodeEntity] = []
        self.all_chunks: List[CodeChunk] = []

    def analyze(self) -> Tuple[List[CodeEntity], List[CodeChunk]]:
        """Analyze entire codebase"""
        from .js_analyzer import JavaScriptAnalyzer

        # Analyze Python files
        entities, chunks = self.python_analyzer.analyze_directory(self.repo_path)
        self.all_entities.extend(entities)
        self.all_chunks.extend(chunks)

        # Analyze JavaScript/TypeScript files
        js_analyzer = JavaScriptAnalyzer()
        js_entities, js_chunks = js_analyzer.analyze_directory(self.repo_path)
        self.all_entities.extend(js_entities)
        self.all_chunks.extend(js_chunks)

        return self.all_entities, self.all_chunks

    def get_architecture_graph(self) -> Dict[str, List[str]]:
        """Build dependency graph from code"""
        graph = {}

        for entity in self.all_entities:
            if entity.type in ["class", "function"]:
                graph[entity.name] = entity.dependencies

        return graph

    def find_entry_points(self) -> List[CodeEntity]:
        """Find main entry points (main functions, etc.)"""
        entry_points = []

        for entity in self.all_entities:
            if entity.name in ["main", "__main__", "run", "start", "init"]:
                entry_points.append(entity)

        return entry_points
