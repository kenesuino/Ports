"""Report unused imports in the package (no external dependency)."""

from __future__ import annotations

import ast
from pathlib import Path


def unused_imports(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    imported[alias.asname or alias.name] = node.lineno
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
    body = "\n".join(
        line for line in source.splitlines()
        if not line.strip().startswith(("from ", "import ")))
    return [f"{name}:{line}" for name, line in imported.items()
            if name not in body]


def main() -> int:
    found = False
    for path in sorted(Path("ports").glob("*.py")):
        unused = unused_imports(path)
        if unused:
            found = True
            print(f"{path.name}: {', '.join(unused)}")
    if not found:
        print("No unused imports found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
