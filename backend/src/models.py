from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class RepositoryInput(BaseModel):
    repo_url: str
    branch: str = "main"
    languages: List[str] = ["python", "javascript"]


class CodeChunk(BaseModel):
    file_path: str
    content: str
    language: str
    start_line: int
    end_line: int
    chunk_type: str
    name: Optional[str] = None
    description: Optional[str] = None


class CodeEntity(BaseModel):
    name: str
    type: str
    file_path: str
    line_number: int
    description: Optional[str] = None
    dependencies: List[str] = []
    is_public: bool = True


class ArchitectureComponent(BaseModel):
    name: str
    type: str
    files: List[str]
    entities: List[CodeEntity]
    dependencies: List[str] = []


class ArchitectureSummary(BaseModel):
    components: List[ArchitectureComponent]
    entry_points: List[CodeEntity]
    dependencies: Dict[str, List[str]]
    total_lines_of_code: int
    file_count: int


class QAQuery(BaseModel):
    question: str
    repo_id: str
    context_depth: int = 5


class QAResponse(BaseModel):
    question: str
    answer: str
    relevant_chunks: List[CodeChunk]
    confidence: float
    learning_resources: List[Dict[str, str]] = []


class CodeSmell(BaseModel):
    type: str
    severity: str          # low | medium | high
    file_path: str
    line_number: int
    description: str
    suggestion: Optional[str] = None


class BugReport(BaseModel):
    type: str
    severity: str          # low | medium | high | critical
    file_path: str
    line_number: int
    description: str
    suggestion: Optional[str] = None


class DesignPattern(BaseModel):
    name: str              # Singleton, Factory, Observer …
    confidence: str        # high | medium | low
    file_path: str
    line_number: int
    description: str


class TechnicalDebtReport(BaseModel):
    score: float           # 0-100  (higher = more debt)
    grade: str             # A-F
    total_issues: int
    high_severity: int
    medium_severity: int
    low_severity: int
    top_files: List[Dict[str, Any]]
    summary: str


class UnitTestSuite(BaseModel):
    repo_id: str
    entity_name: str
    language: str
    test_code: str
    framework: str


class AnalysisReport(BaseModel):
    repo_url: str
    analyzed_at: str
    architecture: ArchitectureSummary
    code_smells: List[CodeSmell]
    bugs: List[BugReport]
    design_patterns: List[DesignPattern]
    technical_debt: TechnicalDebtReport
    total_entities: int
