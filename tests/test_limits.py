"""Size limits for jeverifier's own code: files ≤ 500 lines, functions ≤ 60 lines (the same standard as the projects).

A file or function over the limit is a sign it holds more than one job; split it rather than raising the limit.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "jeverifier"
MAX_FILE = 500
MAX_FUNCTION = 60


def _sources():
    return sorted(PACKAGE.rglob("*.py"))


def _functions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node.lineno, node.end_lineno - node.lineno + 1


def test_files_within_limit():
    over = [f"{p.relative_to(PACKAGE)}: {n} lines" for p in _sources()
            if (n := len(p.read_text(encoding="utf-8").splitlines())) > MAX_FILE]
    assert not over, f"files over {MAX_FILE} lines:\n  " + "\n  ".join(over)


def test_functions_within_limit():
    over = [f"{p.relative_to(PACKAGE)}:{line} {name}(): {n} lines"
            for p in _sources() for name, line, n in _functions(p) if n > MAX_FUNCTION]
    assert not over, f"functions over {MAX_FUNCTION} lines:\n  " + "\n  ".join(over)
