"""Definice, registrace a bezpečné vykonávání nástrojů AI agenta."""

import json
import operator
import os
import stat
from heapq import nsmallest
from pathlib import Path
from typing import Any, Callable, Iterator

from agent.models import ToolDefinition
from config import MAX_FILE_SIZE, MAX_LIST_FILES, WORKSPACE_DIR


def calculator(operation: str, a: int | float, b: int | float) -> float:
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
    if relative_path.is_absolute() or relative_path.drive:
        raise PermissionError("Absolutní cesty nejsou povoleny.")
    if ".." in relative_path.parts:
        raise PermissionError("Přístup mimo workspace není povolen.")

    workspace = WORKSPACE_DIR.resolve()
    target = workspace / relative_path
    current_path = workspace
    for part in relative_path.parts:
        current_path = current_path / part
        if current_path.is_symlink():
            raise PermissionError("Symbolické odkazy nejsou povoleny.")

    resolved_target = target.resolve()
    if not resolved_target.is_relative_to(workspace):
        raise PermissionError("Přístup mimo workspace není povolen.")
    return resolved_target


def list_files() -> dict[str, Any]:
    """Vrátí omezený seznam souborů a informaci o případném zkrácení."""

    workspace = WORKSPACE_DIR.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    def iter_files() -> Iterator[str]:
        # Symbolické odkazy na adresáře neprocházíme.
        for current_dir, directory_names, file_names in os.walk(
            workspace,
            topdown=True,
            followlinks=False,
        ):
            current_path = Path(current_dir)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if not (current_path / name).is_symlink()
            )

            for name in sorted(file_names):
                file_path = current_path / name
                if file_path.is_symlink() or not file_path.is_file():
                    continue
                yield file_path.relative_to(workspace).as_posix()

    # Udržujeme pouze MAX_LIST_FILES + 1 nejmenších položek, nikoliv celý seznam.
    selected_files = nsmallest(MAX_LIST_FILES + 1, iter_files())
    truncated = len(selected_files) > MAX_LIST_FILES

    return {
        "files": selected_files[:MAX_LIST_FILES],
        "truncated": truncated,
        "max_results": MAX_LIST_FILES,
    }


def read_file(filename: str) -> str:
    """Načte nejvýše MAX_FILE_SIZE bajtů z běžného UTF-8 souboru."""

    path = _resolve_workspace_path(filename)

    # O_NOFOLLOW odmítne symbolický odkaz v poslední cestové komponentě
    # na systémech, které tento příznak podporují (typicky Linux/macOS).
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    file_descriptor = os.open(path, flags)

    with os.fdopen(file_descriptor, "rb") as file:
        file_info = os.fstat(file.fileno())

        if not stat.S_ISREG(file_info.st_mode):
            raise ValueError("Zadaná cesta neukazuje na běžný soubor.")

        # Čteme maximálně o jeden bajt navíc, abychom spolehlivě poznali
        # překročení limitu i v případě, že se soubor po kontrole změní.
        content = file.read(MAX_FILE_SIZE + 1)

    if len(content) > MAX_FILE_SIZE:
        raise ValueError("Soubor překračuje povolenou velikost.")

    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Soubor není platný UTF-8 text.") from exc


AVAILABLE_TOOLS: dict[str, Callable[..., Any]] = {
    "calculator": calculator,
    "list_files": list_files,
    "read_file": read_file,
}

# Schémata zůstávají provider-neutrální. Konkrétní adaptér je převede do svého API.
TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="calculator",
        description="Provede matematickou operaci.",
        parameters={
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
    ),
    ToolDefinition(
        name="list_files",
        description=(
            "Vypíše nejvýše 500 souborů ve workspace a oznámí, "
            "zda byl seznam zkrácen."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    ToolDefinition(
        name="read_file",
        description="Přečte textový soubor ve workspace.",
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Relativní cesta k souboru.",
                }
            },
            "required": ["filename"],
        },
    ),
]


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Ověří a vykoná nástroj; výsledek i chyby vrací jako JSON text."""

    if not isinstance(name, str) or name not in AVAILABLE_TOOLS:
        return json.dumps({"error": "Neznámý nástroj."}, ensure_ascii=False)
    if not isinstance(arguments, dict):
        return json.dumps(
            {"error": "Argumenty musí být JSON objekt."}, ensure_ascii=False
        )

    try:
        result = AVAILABLE_TOOLS[name](**arguments)
        return json.dumps(
            {"result": result}, ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError, OSError, OverflowError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
