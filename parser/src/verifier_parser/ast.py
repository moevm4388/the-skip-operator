"""Public AST model. All source spans use zero-based, half-open offsets [start, end)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class Span:
    start: int
    end: int
    line: int
    column: int

@dataclass
class Expr:
    kind: str
    value: Any = None
    args: list["Expr"] = field(default_factory=list)
    span: Span | None = None

@dataclass
class Parameter:
    type_name: str
    name: str
    span: Span | None = None

@dataclass
class Stmt:
    kind: str
    span: Span | None = None
    data: dict[str, Any] = field(default_factory=dict)

@dataclass
class Program:
    inputs: list[Parameter]
    input_condition: Expr | None
    body: list[Stmt]
    outputs: list[Parameter]
    output_condition: Expr | None
    span: Span | None = None


def span_to_dict(span: Span | None) -> Any:
    if span is None:
        return None
    return {
        "start": span.start,
        "end": span.end,
        "line": span.line,
        "column": span.column,
    }


def parameter_to_dict(parameter: Parameter) -> dict[str, Any]:
    return {
        "type_name": parameter.type_name,
        "name": parameter.name,
        "span": span_to_dict(parameter.span),
    }


def expr_to_dict(expr: Expr | None) -> Any:
    if expr is None:
        return None

    return {
        "kind": expr.kind,
        "value": expr.value,
        "args": [expr_to_dict(arg) for arg in expr.args],
        "span": span_to_dict(expr.span),
    }


def program_to_dict(program: Program) -> dict[str, Any]:
    def serialize_value(value):
        if isinstance(value, Expr):
            return expr_to_dict(value)

        if isinstance(value, Stmt):
            return stmt_to_dict(value)

        if isinstance(value, Parameter):
            return parameter_to_dict(value)

        if isinstance(value, Span):
            return span_to_dict(value)

        if isinstance(value, list):
            return [serialize_value(item) for item in value]

        if isinstance(value, dict):
            return {
                key: serialize_value(item)
                for key, item in value.items()
            }

        return value

    def stmt_to_dict(statement: Stmt) -> dict[str, Any]:
        return {
            "kind": statement.kind,
            "span": span_to_dict(statement.span),
            **{
                key: serialize_value(value)
                for key, value in statement.data.items()
            },
        }

    return {
        "inputs": [
            parameter_to_dict(p) for p in program.inputs
        ],
        "input_condition": expr_to_dict(program.input_condition),
        "body": [
            stmt_to_dict(s) for s in program.body
        ],
        "outputs": [
            parameter_to_dict(p) for p in program.outputs
        ],
        "output_condition": expr_to_dict(program.output_condition),
        "span": span_to_dict(program.span),
    }
