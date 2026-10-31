import json
import operator
from pathlib import Path
from typing import Any, Callable

from config import MAX_FILE_SIZE, WORKSPACE_DIR


def calculator(
    operation: str,
    a: float,
    b: float,
) -> float:
    """Provede základní matematickou operaci."""

    operations: dict[str, Callable[[float, float], float]] = {
        "add": operator.add,
        "subtract": operator.sub,
        "multiply": operator.mul,
        "divide": operator.truediv,
    }

    if operation not in operations:
        raise ValueError("Nepodporovaná matematická operace.")

    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        for value in (a, b)
    ):
        raise ValueError("Argumenty musí být čísla.")

    if operation == "divide" and b == 0:
        raise ValueError("Dělení nulou není povoleno.")

    result = operations[operation](a, b)

    if not (-1e100 < result < 1e100):
        raise ValueError("Výsledek je mimo povolený rozsah.")

    return result


def _resolve_workspace_path(filename: str) -> Path:
    """Ověří, že cesta zůstává uvnitř workspace."""

    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Název souboru není platný.")

    workspace = WORKSPACE_DIR.resolve()
    target = (workspace / filename).resolve()

    if not target.is_relative_to(workspace):
        raise PermissionError("Přístup mimo workspace není povolen.")

    return target


def list_files() -> list[str]:
    """Vrátí seznam souborů v pracovním adresáři."""

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    return sorted(
        path.relative_to(WORKSPACE_DIR).as_posix()
        for path in WORKSPACE_DIR.rglob("*")
        if path.is_file()
        and not path.is_symlink()
    )


def read_file(filename: str) -> str:
    """Bezpečně načte textový soubor z workspace."""

    path = _resolve_workspace_path(filename)

    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError("Soubor nebyl nalezen.")

    if path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError("Soubor překračuje povolenou velikost.")

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Soubor není platný UTF-8 text.") from exc


# Registr dostupných nástrojů.
AVAILABLE_TOOLS: dict[str, Callable[..., Any]] = {
    "calculator": calculator,
    "list_files": list_files,
    "read_file": read_file,
}


# Popis nástrojů předávaný jazykovému modelu.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Provede matematickou operaci.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "add",
                            "subtract",
                            "multiply",
                            "divide",
                        ],
                    },
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["operation", "a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Vypíše soubory ve workspace.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Přečte textový soubor ve workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Relativní cesta k souboru.",
                    }
                },
                "required": ["filename"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Ověří a vykoná požadovaný nástroj."""

    if name not in AVAILABLE_TOOLS:
        return json.dumps(
            {"error": "Neznámý nástroj."},
            ensure_ascii=False,
        )

    if not isinstance(arguments, dict):
        return json.dumps(
            {"error": "Argumenty musí být JSON objekt."},
            ensure_ascii=False,
        )

    try:
        result = AVAILABLE_TOOLS[name](**arguments)

        return json.dumps(
            {"result": result},
            ensure_ascii=False,
            allow_nan=False,
        )

    except (TypeError, ValueError, OSError, PermissionError) as exc:
        return json.dumps(
            {"error": str(exc)},
            ensure_ascii=False,
        )
