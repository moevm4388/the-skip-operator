"""CLI: python -m verifier_parser path/to/program.alg"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from . import ParseError, parse, program_to_dict


def main() -> int:
    cli = argparse.ArgumentParser(description="Парсер аннотированного алгоритмического языка")
    cli.add_argument("file", type=Path, help="Путь к исходному файлу .alg")
    args = cli.parse_args()

    try:
        source = args.file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Не удалось прочитать файл: {exc}")
        return 2

    try:
        ast = parse(source)
    except ParseError as exc:
        print("Обнаружены ошибки парсинга:")
        for issue in exc.issues:
            print(
                f"{issue.code}: {issue.message} "
                f"(строка {issue.span.line}, столбец {issue.span.column}, "
                f"символы [{issue.span.start}, {issue.span.end}))"
            )
        return 1

    print(json.dumps(program_to_dict(ast), ensure_ascii=False, indent=2, default=lambda value: vars(value)))
    print("\nПарсинг завершён успешно.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
