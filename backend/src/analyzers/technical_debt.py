from typing import List, Dict, Any
from collections import defaultdict
from src.models import CodeSmell, BugReport, TechnicalDebtReport


def calculate_technical_debt(
    smells: List[CodeSmell],
    bugs: List[BugReport],
    total_lines: int,
    file_count: int,
) -> TechnicalDebtReport:
    """
    Score 0-100 (higher = more debt).
    Weights: critical bug=15, high=8, medium=4, low=1
    Normalised against codebase size so small repos aren't unfairly penalised.
    """
    weights = {"critical": 15, "high": 8, "medium": 4, "low": 1}

    raw = 0
    high = medium = low = 0

    for b in bugs:
        raw += weights.get(b.severity, 1)
        if b.severity in ("critical", "high"):
            high += 1
        elif b.severity == "medium":
            medium += 1
        else:
            low += 1

    for s in smells:
        raw += weights.get(s.severity, 1)
        if s.severity == "high":
            high += 1
        elif s.severity == "medium":
            medium += 1
        else:
            low += 1

    # Normalise: 1 issue per 100 LOC = baseline
    baseline = max(total_lines / 100, 1)
    score = min(100.0, round((raw / baseline) * 10, 1))

    if score <= 10:
        grade = "A"
    elif score <= 25:
        grade = "B"
    elif score <= 45:
        grade = "C"
    elif score <= 65:
        grade = "D"
    else:
        grade = "F"

    # Top files by issue count
    file_issues: Dict[str, int] = defaultdict(int)
    for b in bugs:
        file_issues[b.file_path] += weights.get(b.severity, 1)
    for s in smells:
        file_issues[s.file_path] += weights.get(s.severity, 1)

    top_files = sorted(
        [{"file": k, "score": v} for k, v in file_issues.items()],
        key=lambda x: x["score"],
        reverse=True,
    )[:5]

    total = len(bugs) + len(smells)
    summary = (
        f"Grade {grade} — {total} total issues ({high} high, {medium} medium, {low} low) "
        f"across {file_count} files and {total_lines:,} lines of code."
    )

    return TechnicalDebtReport(
        score=score,
        grade=grade,
        total_issues=total,
        high_severity=high,
        medium_severity=medium,
        low_severity=low,
        top_files=top_files,
        summary=summary,
    )
