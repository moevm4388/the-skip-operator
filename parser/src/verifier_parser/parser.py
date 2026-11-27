
"""Recursive-descent parser for the ADR-02 annotated algorithmic language."""

from __future__ import annotations

from dataclasses import replace

from .ast import Expr, Parameter, Program, Span, Stmt
from .errors import ParseError, ParseIssue
from .lexer import Token, tokenize


TYPES = {"bool", "nat", "int", "rat", "poly"}

PRECEDENCE = {
    "->": 1,
    "||": 2,
    "&&": 3,
    "=": 4,
    "!=": 4,
    "<": 4,
    "<=": 4,
    ">": 4,
    ">=": 4,
    "+": 5,
    "-": 5,
    "*": 6,
    "/": 6,
    "%": 6,
    "^": 7,
}

BUILTINS = {
    "gcd", "mod", "abs", "div", "num",
    "denom", "frac", "deg", "coeff", "set_coeff"
}


class Parser:
    def __init__(self, source: str):
        self.source = source
        self.lines = source.splitlines(keepends=True)

        self.line_offsets = []
        pos = 0
        for line in self.lines:
            self.line_offsets.append(pos)
            pos += len(line)

        self.index = 0
        self.issues: list[ParseIssue] = []
        self.inputs: list[Parameter] = []
        self.outputs: list[Parameter] = []
        self.input_condition = None
        self.output_condition = None

    def parse(self) -> Program:
        meaningful = [
            (n, line.rstrip("\r\n"))
            for n, line in enumerate(self.lines)
            if line.strip()
        ]

        if not meaningful:
            self.error(
                "PARSE_EMPTY_PROGRAM",
                "Программа не должна быть пустой",
                Span(0, 0, 1, 1)
            )
            self.raise_if_errors()

        if meaningful[0][1].lstrip().startswith("input "):
            self.parse_header(meaningful[0][0], "input")
            self.index += 1

        body, self.index = self.parse_block(
            self.index, 0, stop_words={"output"}
        )

        if (
            self.index < len(meaningful)
            and meaningful[self.index][1].lstrip().startswith("output ")
        ):
            self.parse_header(meaningful[self.index][0], "output")
            self.index += 1

        if self.index < len(meaningful):
            n, line = meaningful[self.index]
            self.error(
                "PARSE_AFTER_OUTPUT",
                "После output не должно быть инструкций",
                self.line_span(n, line)
            )

        self.raise_if_errors()

        return Program(
            self.inputs,
            self.input_condition,
            body,
            self.outputs,
            self.output_condition,
            Span(0, len(self.source), 1, 1)
        )

    def parse_header(self, n: int, kind: str):
        line = self.lines[n].rstrip("\r\n")
        prefix = kind + " "
        stripped = line.strip()
        rest = stripped[len(prefix):]

        if ":" not in rest:
            self.error(
                "PARSE_HEADER_COLON",
                f"После {kind} ожидается ':' и предикат",
                self.line_span(n, line)
            )
            return

        decl, cond = rest.split(":", 1)
        params = []

        for item in decl.split(","):
            parts = item.strip().split()

            if len(parts) != 2 or parts[0] not in TYPES:
                self.error(
                    "PARSE_PARAMETER",
                    f"Ожидается '<тип> <имя>', получено: {item.strip()}",
                    self.line_span(n, line)
                )
                continue

            params.append(
                Parameter(parts[0], parts[1], self.line_span(n, line))
            )

        cond_text = cond.strip()
        cond_pos = line.index(":") + 1
        cond_pos += len(line[cond_pos:]) - len(line[cond_pos:].lstrip())

        condition = self.parse_expr_text(
            cond_text, n, line, cond_pos
        )

        if kind == "input":
            self.inputs = params
            self.input_condition = condition
        else:
            self.outputs = params
            self.output_condition = condition

    def parse_block(self, start: int, indent: int, stop_words: set[str]):
        meaningful = [
            (n, line.rstrip("\r\n"))
            for n, line in enumerate(self.lines)
            if line.strip()
        ]

        out = []
        i = start

        while i < len(meaningful):
            n, line = meaningful[i]
            spaces = len(line) - len(line.lstrip(" "))
            stripped = line.strip()

            if (
                spaces < indent
                or stripped.startswith("else:")
                or stripped.startswith("invariant ")
                or stripped.startswith("variant ")
                or any(stripped.startswith(w + " ") for w in stop_words)
            ):
                break

            if spaces != indent:
                self.error(
                    "PARSE_INDENT",
                    f"Ожидается отступ {indent} пробелов (получено {spaces})",
                    self.line_span(n, line)
                )
                i += 1
                continue

            if stripped.startswith("input ") or stripped.startswith("output "):
                break

            stmt, next_i = self.parse_statement(meaningful, i, indent)

            if stmt:
                out.append(stmt)

            i = max(next_i, i + 1)

        return out, i

    def parse_statement(self, lines, i: int, indent: int):
        n, line = lines[i]
        s = line.strip()
        span = self.line_span(n, line)
        line_pos = line.index(s)

        if s == "skip":
            return Stmt("skip", span), i + 1

        if s.startswith("assert "):
            text_pos = line_pos + len("assert ")
            return Stmt(
                "assert",
                span,
                {
                    "condition": self.parse_expr_text(
                        s[7:], n, line, text_pos
                    )
                }
            ), i + 1

        if s.startswith("assume "):
            text_pos = line_pos + len("assume ")
            return Stmt(
                "assume",
                span,
                {
                    "condition": self.parse_expr_text(
                        s[7:], n, line, text_pos
                    )
                }
            ), i + 1

        if s.startswith("if "):
            cond_text = s[3:].rstrip()

            if not cond_text.endswith(":"):
                self.error(
                    "PARSE_IF_COLON",
                    "После условия if ожидается ':'",
                    span
                )
                cond_text = cond_text
            else:
                cond_text = cond_text[:-1].rstrip()

            text_pos = line_pos + 3

            cond = self.parse_expr_text(
                cond_text, n, line, text_pos
            )

            then_body, j = self.parse_block(
                i + 1, indent + 4, set()
            )

            else_body = []

            if j < len(lines) and lines[j][1].strip() == "else:":
                else_body, j = self.parse_block(
                    j + 1, indent + 4, set()
                )

            return Stmt(
                "if",
                span,
                {
                    "condition": cond,
                    "then_body": then_body,
                    "else_body": else_body
                }
            ), j

        if s.startswith("while "):
            cond_text = s[6:].rstrip()

            if not cond_text.endswith(":"):
                self.error(
                    "PARSE_WHILE_COLON",
                    "После условия while ожидается ':'",
                    span
                )
            else:
                cond_text = cond_text[:-1].rstrip()

            text_pos = line_pos + 6

            cond = self.parse_expr_text(
                cond_text, n, line, text_pos
            )

            body, j = self.parse_block(
                i + 1, indent + 4, set()
            )

            invariant = None
            variant = None

            if j < len(lines) and lines[j][1].strip().startswith("invariant "):
                inv_n, inv_line = lines[j]
                inv_stripped = inv_line.strip()
                inv_text = inv_stripped[10:]
                inv_pos = inv_line.index(inv_stripped) + 10

                invariant = self.parse_expr_text(
                    inv_text, inv_n, inv_line, inv_pos
                )
                j += 1
            else:
                self.error(
                    "PARSE_MISSING_INVARIANT",
                    "Для while обязателен invariant",
                    span
                )

            if j < len(lines) and lines[j][1].strip().startswith("variant "):
                var_n, var_line = lines[j]
                var_stripped = var_line.strip()
                var_text = var_stripped[8:]
                var_pos = var_line.index(var_stripped) + 8

                variant = self.parse_expr_text(
                    var_text, var_n, var_line, var_pos
                )
                j += 1

            return Stmt(
                "while",
                span,
                {
                    "condition": cond,
                    "body": body,
                    "invariant": invariant,
                    "variant": variant
                }
            ), j

        parts = s.split(None, 2)

        if len(parts) == 3 and parts[0] in TYPES and "=" in parts[2]:
            name = parts[1]
            equal_pos = line.index("=")
            expr_text = parts[2].split("=", 1)[1].strip()

            text_pos = equal_pos + 1
            text_pos += len(line[text_pos:]) - len(line[text_pos:].lstrip())

            value = self.parse_expr_text(
                expr_text, n, line, text_pos
            )

            return Stmt(
                "assign",
                span,
                {
                    "type_name": parts[0],
                    "name": name,
                    "value": value
                }
            ), i + 1

        self.error(
            "PARSE_UNKNOWN_STATEMENT",
            f"Неизвестная инструкция: {s}",
            span
        )

        return None, i + 1

    def line_span(self, n, line):
        start = (
            self.line_offsets[n]
            if n < len(self.line_offsets)
            else len(self.source)
        )

        return Span(start, start + len(line), n + 1, 1)

    def parse_expr_text(self, text, n, line, text_pos):
        base = self.line_offsets[n] + text_pos
        base_col = text_pos + 1

        try:
            toks = tokenize(text)
            ep = ExpressionParser(toks)
            expr = ep.parse()

            shift_expr(expr, base, n + 1, base_col)

            return expr

        except ParseError as e:
            for issue in e.issues:
                span = issue.span

                shifted_span = Span(
                    base + span.start,
                    base + span.end,
                    n + 1,
                    base_col + span.column - 1
                )

                self.issues.append(
                    ParseIssue(
                        issue.code,
                        issue.message,
                        shifted_span
                    )
                )

            return Expr("error")

    def error(self, code, message, span):
        self.issues.append(ParseIssue(code, message, span))

    def raise_if_errors(self):
        if self.issues:
            raise ParseError(self.issues)


def shift_expr(expr, base, line, col):
    if expr.span:
        expr.span = Span(
            base + expr.span.start,
            base + expr.span.end,
            line,
            col + expr.span.column - 1
        )

    for a in expr.args:
        shift_expr(a, base, line, col)


class ExpressionParser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0
        self.issues: list[ParseIssue] = []

    @property
    def current(self):
        return self.tokens[self.i]

    def take(self):
        t = self.current
        if self.i < len(self.tokens) - 1:
            self.i += 1
        return t

    def accept(self, kind):
        if self.current.kind == kind:
            return self.take()
        return None

    def expect(self, kind):
        t = self.accept(kind)

        if not t:
            raise ParseError([
                ParseIssue(
                    "PARSE_EXPECTED_TOKEN",
                    f"Ожидался токен {kind}",
                    self.current.span
                )
            ])

        return t

    def recover(self):
        """Пропускает токены до ближайшего места продолжения разбора."""
        while self.current.kind != "EOF":
            if (
                self.current.kind in PRECEDENCE
                or self.current.kind in (",", ")")
            ):
                return

            self.take()

    def parse(self):
        result = self.expression(0)

        if self.current.kind != "EOF":
            self.issues.append(
                ParseIssue(
                    "PARSE_TRAILING_EXPRESSION",
                    f"Лишний токен {self.current.value!r}",
                    self.current.span
                )
            )

        if self.issues:
            raise ParseError(self.issues)

        return result

    def expression(self, min_prec):
        try:
            left = self.prefix()
        except ParseError as e:
            self.issues.extend(e.issues)

            error_span = e.issues[0].span
            left = Expr("error", span=error_span)

            self.recover()

        while True:
            if self.current.kind in PRECEDENCE:
                prec = PRECEDENCE[self.current.kind]

                if prec < min_prec:
                    break

                op = self.take()

                next_min_prec = (
                    prec if op.kind in ("->", "^") else prec + 1
                )

                right = self.expression(next_min_prec)

                left = Expr(
                    "binary",
                    op.kind,
                    [left, right],
                    Span(
                        left.span.start,
                        right.span.end,
                        left.span.line,
                        left.span.column
                    )
                )
                continue

            if self.current.kind in ("NUMBER", "IDENT", "("):
                prec = PRECEDENCE["*"]

                if prec < min_prec:
                    break

                right = self.expression(prec + 1)

                left = Expr(
                    "binary",
                    "*",
                    [left, right],
                    Span(
                        left.span.start,
                        right.span.end,
                        left.span.line,
                        left.span.column
                    )
                )
                continue

            break

        return left

    def prefix(self):
        t = self.take()

        if t.kind in ("-", "!"):
            value = self.expression(7)

            return Expr(
                "unary",
                t.kind,
                [value],
                Span(
                    t.span.start,
                    value.span.end,
                    t.span.line,
                    t.span.column
                )
            )

        if t.kind == "NUMBER":
            return Expr("number", t.value, [], t.span)

        if t.kind == "IDENT":
            if t.value in ("true", "false"):
                return Expr("bool", t.value == "true", [], t.span)

            if t.value in ("forall", "exists"):
                typ = self.expect("IDENT")

                if typ.value not in TYPES:
                    raise ParseError([
                        ParseIssue(
                            "PARSE_QUANTIFIER_TYPE",
                            "Неизвестный тип переменной квантора",
                            typ.span
                        )
                    ])

                name = self.expect("IDENT")
                self.expect(":")
                self.expect("(")

                body = self.expression(0)
                end = self.expect(")")

                return Expr(
                    "quantifier",
                    t.value,
                    [
                        Expr(
                            "bound_variable",
                            (typ.value, name.value),
                            [],
                            name.span
                        ),
                        body
                    ],
                    Span(
                        t.span.start,
                        end.span.end,
                        t.span.line,
                        t.span.column
                    )
                )

            if self.accept("("):
                args = []

                if self.current.kind != ")":
                    args.append(self.expression(0))

                    while self.accept(","):
                        args.append(self.expression(0))

                end = self.expect(")")

                return Expr(
                    "call",
                    t.value,
                    args,
                    Span(
                        t.span.start,
                        end.span.end,
                        t.span.line,
                        t.span.column
                    )
                )

            return Expr("variable", t.value, [], t.span)

        if t.kind == "(":
            value = self.expression(0)
            end = self.expect(")")

            return replace(
                value,
                span=Span(
                    t.span.start,
                    end.span.end,
                    t.span.line,
                    t.span.column
                )
            )

        raise ParseError([
            ParseIssue(
                "PARSE_EXPECTED_EXPRESSION",
                "Ожидалось выражение",
                t.span
            )
        ])


def parse(source: str) -> Program:
    return Parser(source).parse()
