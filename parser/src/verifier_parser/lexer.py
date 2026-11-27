"""Lexer with source locations. Indentation is handled by the line-oriented parser."""
from dataclasses import dataclass
from .ast import Span
from .errors import ParseIssue, ParseError

@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    span: Span

_MULTI = ("&&", "||", "->", "!=", ">=", "<=")
_SINGLE = set("+-*/%^=<>!&|(),:;")

def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    issues: list[ParseIssue] = []
    i = 0
    line = 1
    col = 1
    while i < len(text):
        ch = text[i]
        if ch in " \t\r":
            i += 1; col += 1
            continue
        if ch == "\n":
            i += 1; line += 1; col = 1
            continue
        start, start_line, start_col = i, line, col
        if ch.isdigit():
            i += 1; col += 1
            while i < len(text) and (text[i].isdigit() or text[i] == "."):
                i += 1; col += 1
            value = text[start:i]
            if value.count(".") > 1:
                issues.append(ParseIssue("LEX_INVALID_NUMBER", f"Некорректное число: {value}", Span(start, i, start_line, start_col)))
            tokens.append(Token("NUMBER", value, Span(start, i, start_line, start_col)))
            continue
        if ch.isalpha() or ch == "_":
            i += 1; col += 1
            while i < len(text) and (text[i].isalnum() or text[i] == "_"):
                i += 1; col += 1
            value = text[start:i]
            tokens.append(Token("IDENT", value, Span(start, i, start_line, start_col)))
            continue
        op = next((op for op in _MULTI if text.startswith(op, i)), None)
        if op:
            i += len(op); col += len(op)
            tokens.append(Token(op, op, Span(start, i, start_line, start_col)))
            continue
        if ch in _SINGLE:
            i += 1; col += 1
            tokens.append(Token(ch, ch, Span(start, i, start_line, start_col)))
            continue
        issues.append(ParseIssue("LEX_UNEXPECTED_CHAR", f"Недопустимый символ: {ch!r}", Span(start, start + 1, line, col)))
        i += 1; col += 1
    tokens.append(Token("EOF", "", Span(len(text), len(text), line, col)))
    if issues:
        raise ParseError(issues)
    return tokens
