import re
import os
from typing import List, Optional, Tuple
from src.models import CodeChunk, CodeEntity

class JavaScriptAnalyzer:
    """
    Simple JavaScript/TypeScript analyzer using regex patterns.
    For production, consider using a proper JS parser library.
    """

    def __init__(self):
        self.entities: List[CodeEntity] = []
        self.chunks: List[CodeChunk] = []
        self.current_file = ""

        # Regex patterns
        self.function_pattern = re.compile(
            r'(?:async\s+)?(?:function\s+)?(\w+)\s*\([^)]*\)\s*{',
            re.MULTILINE
        )
        self.class_pattern = re.compile(
            r'class\s+(\w+)(?:\s+extends\s+(\w+))?\s*{',
            re.MULTILINE
        )
        self.import_pattern = re.compile(
            r'(?:import|require)\s+(?:{([^}]+)}|(?:(?:.*\s+)?from\s+)?[\'"](.*?)[\'"])',
            re.MULTILINE
        )
        self.export_pattern = re.compile(
            r'export\s+(?:default\s+)?(?:const|let|var|function|class)\s+(\w+)',
            re.MULTILINE
        )

    def analyze_file(self, file_path: str) -> Tuple[List[CodeEntity], List[CodeChunk]]:
        """Analyze a single JavaScript/TypeScript file"""
        self.current_file = file_path
        self.entities = []
        self.chunks = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract file-level chunk
            lines = content.split('\n')
            file_name = file_path.split('/')[-1].replace('.js', '').replace('.ts', '')

            self.chunks.append(CodeChunk(
                file_path=file_path,
                content=content,
                language="javascript" if file_path.endswith('.js') else "typescript",
                start_line=1,
                end_line=len(lines),
                chunk_type="module",
                name=file_name,
                description=self._extract_module_doc(content)
            ))

            # Extract entities
            self._extract_functions(content, file_path)
            self._extract_classes(content, file_path)
            self._extract_exports(content, file_path)
            self._extract_imports(content, file_path)

        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")

        return self.entities, self.chunks

    def analyze_directory(self, directory: str) -> Tuple[List[CodeEntity], List[CodeChunk]]:
        """Recursively analyze all JS/TS files in directory"""
        all_entities = []
        all_chunks = []

        for root, dirs, files in os.walk(directory):
            # Skip common non-source directories
            dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '.venv', 'venv', 'dist', 'build']]

            for file in files:
                if file.endswith(('.js', '.ts', '.tsx', '.jsx')):
                    file_path = os.path.join(root, file)
                    entities, chunks = self.analyze_file(file_path)
                    all_entities.extend(entities)
                    all_chunks.extend(chunks)

        return all_entities, all_chunks

    def _extract_functions(self, content: str, file_path: str):
        """Extract function definitions"""
        lines = content.split('\n')

        for match in self.function_pattern.finditer(content):
            func_name = match.group(1)

            # Find line number
            line_num = content[:match.start()].count('\n') + 1

            entity = CodeEntity(
                name=func_name,
                type="function",
                file_path=file_path,
                line_number=line_num,
                description=self._extract_doc_comment(content, match.start()),
                is_public=not func_name.startswith('_')
            )

            if entity not in self.entities:  # Avoid duplicates
                self.entities.append(entity)

    def _extract_classes(self, content: str, file_path: str):
        """Extract class definitions"""
        lines = content.split('\n')

        for match in self.class_pattern.finditer(content):
            class_name = match.group(1)
            extends = match.group(2)

            # Find line number
            line_num = content[:match.start()].count('\n') + 1

            dependencies = [extends] if extends else []

            entity = CodeEntity(
                name=class_name,
                type="class",
                file_path=file_path,
                line_number=line_num,
                description=self._extract_doc_comment(content, match.start()),
                dependencies=dependencies,
                is_public=not class_name.startswith('_')
            )

            self.entities.append(entity)

    def _extract_exports(self, content: str, file_path: str):
        """Extract exported entities"""
        for match in self.export_pattern.finditer(content):
            export_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            entity = CodeEntity(
                name=export_name,
                type="export",
                file_path=file_path,
                line_number=line_num,
                description=self._extract_doc_comment(content, match.start()),
                is_public=True
            )

            if entity not in self.entities:
                self.entities.append(entity)

    def _extract_imports(self, content: str, file_path: str):
        """Extract imported dependencies"""
        imports = set()

        for match in self.import_pattern.finditer(content):
            # Try to get the module name
            if match.group(1):  # ES6 destructured import
                imports.update(x.strip() for x in match.group(1).split(','))
            elif match.group(2):  # Module path
                imports.add(match.group(2))

        # Create dependency entities
        for imp in imports:
            if imp and not imp.startswith('.'):
                entity = CodeEntity(
                    name=imp,
                    type="import",
                    file_path=file_path,
                    line_number=1,
                    dependencies=[imp],
                    is_public=False
                )
                self.entities.append(entity)

    def _extract_doc_comment(self, content: str, position: int) -> Optional[str]:
        """Extract JSDoc comment before the position"""
        # Find the last /** */ before position
        search_area = content[:position]

        # Look for JSDoc pattern
        jsdoc_pattern = re.compile(r'/\*\*\s*([\s\S]*?)\*/', re.MULTILINE)
        matches = list(jsdoc_pattern.finditer(search_area))

        if matches:
            last_match = matches[-1]
            # Check if it's close to our position
            if position - last_match.end() < 100:  # Within 100 chars
                doc = last_match.group(1)
                # Clean up the doc
                lines = doc.split('\n')
                cleaned = [line.strip().lstrip('*').strip() for line in lines]
                return ' '.join(cleaned).strip()

        return None

    def _extract_module_doc(self, content: str) -> Optional[str]:
        """Extract module-level documentation"""
        # Look for first comment block
        comment_pattern = re.compile(r'^(?://.*\n)*(?:/\*\*\s*([\s\S]*?)\*/)', re.MULTILINE)
        match = comment_pattern.search(content)

        if match:
            doc = match.group(1)
            lines = doc.split('\n')
            cleaned = [line.strip().lstrip('*').strip() for line in lines]
            return ' '.join(cleaned).strip()

        return None
