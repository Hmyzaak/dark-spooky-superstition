# agent/tools.py
"""Definice, registrace a bezpečné vykonávání nástrojů AI agenta."""

import json
import operator
from pathlib import Path
from typing import Any, Callable

from config import MAX_FILE_SIZE, WORKSPACE_DIR


def calculator(
    operation: str,
    a: int | float,
    b: int | float,
) -> float:
    """Provede základní matematickou operaci."""

    operations: dict[str, Callable[..., int | float]] = {
        "add": operator.add,
        "subtract": operator.sub,
        "multiply": operator.mul,
        "divide": operator.truediv,
    }

    if not isinstance(operation, str) or operation not in operations:
        raise ValueError("Nepodporovaná matematická operace.")

    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and -1e100 <= value <= 1e100
        for value in (a, b)
    ):
        raise ValueError("Argumenty musí být platná čísla v povoleném rozsahu.")

    if operation == "divide" and b == 0:
        raise ValueError("Dělení nulou není povoleno.")

    result = operations[operation](a, b)

    if not (-1e100 < result < 1e100):
        raise ValueError("Výsledek je mimo povolený rozsah.")

    return float(result)


def _resolve_workspace_path(filename: str) -> Path:
    """Ověří, že cesta zůstává uvnitř workspace."""

    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Název souboru není platný.")

    relative_path = Path(filename)

    # Povolujeme pouze relativní cesty bez průchodu do nadřazených adresářů.
    if relative_path.is_absolute() or relative_path.drive:
        raise PermissionError("Absolutní cesty nejsou povoleny.")

    if ".." in relative_path.parts:
        raise PermissionError("Přístup mimo workspace není povolen.")

    workspace = WORKSPACE_DIR.resolve()
    target = workspace / relative_path

    # Kontrolujeme symbolické odkazy ještě před jejich rozřešením.
    current_path = workspace

    for part in relative_path.parts:
        current_path = current_path / part

        if current_path.is_symlink():
            raise PermissionError("Symbolické odkazy nejsou povoleny.")

    resolved_target = target.resolve()

    if not resolved_target.is_relative_to(workspace):
        raise PermissionError("Přístup mimo workspace není povolen.")

    return resolved_target


def list_files() -> list[str]:
    """Vrátí seznam běžných souborů v pracovním adresáři."""

    workspace = WORKSPACE_DIR.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    return sorted(
        path.relative_to(workspace).as_posix()
        for path in workspace.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def read_file(filename: str) -> str:
    """Bezpečně načte textový soubor z workspace."""

    path = _resolve_workspace_path(filename)

    if not path.is_file():
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
TOOL_SCHEMAS: list[dict[str, Any]] = [
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
                        "enum": ["add", "subtract", "multiply", "divide"],
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
    """Ověří a vykoná požadovaný nástroj. Jediné místo, které převádí chyby vykonávání nástrojů na JSON - neukončí
    tak běh agenta, ale pošle mu chybovou zprávu, na jejímž základě může agent rozhodnout, co dál."""

    if not isinstance(name, str) or name not in AVAILABLE_TOOLS:
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

    except (TypeError, ValueError, OSError, OverflowError) as exc:
        return json.dumps(
            {"error": str(exc)},
            ensure_ascii=False,
        )
