from dataclasses import dataclass
from .ast import Span

@dataclass
class ParseIssue:
    code: str
    message: str
    span: Span

class ParseError(Exception):
    def __init__(self, issues: list[ParseIssue]):
        self.issues = issues
        super().__init__("\n".join(f"{e.code}: {e.message} (строка {e.span.line}, столбец {e.span.column})" for e in issues))
