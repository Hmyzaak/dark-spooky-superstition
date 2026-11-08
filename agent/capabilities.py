"""Generování katalogu schopností z konfigurace a registru nástrojů."""

from __future__ import annotations

import json
from pathlib import Path

import config

from agent.tools import AVAILABLE_TOOLS, TOOL_DEFINITIONS


def build_capabilities_markdown() -> str:
    """Vytvoří aktuální katalog schopností bez ručně opisovaných nástrojů."""

    definition_by_name = {item.name: item for item in TOOL_DEFINITIONS}
    registered_names = set(AVAILABLE_TOOLS)
    defined_names = set(definition_by_name)
    tool_names = sorted(registered_names & defined_names)

    lines = [
        "# Katalog schopností AI agenta",
        "",
        "> Tento soubor je generován automaticky. Neupravujte jej ručně.",
        "> Zdroj: `config.py`, `agent/tools.py` (registr a definice nástrojů).",
        "",
        "## Stav aplikace",
        "",
        f"- Zvolený poskytovatel LLM: `{config.LLM_PROVIDER}`",
        "- Podporovaní poskytovatelé: "
        + ", ".join(f"`{name}`" for name in config.SUPPORTED_LLM_PROVIDERS),
        "- Architektura: jeden AI agent s Agent Loop; nejde o MAS.",
        "",
        "## Dostupné nástroje",
        "",
    ]

    if tool_names:
        for name in tool_names:
            definition = definition_by_name[name]
            lines.extend(
                [
                    f"### `{name}`",
                    "",
                    definition.description,
                    "",
                    "Parametry (JSON Schema):",
                    "",
                    "```json",
                    json.dumps(definition.parameters, ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )
    else:
        lines.extend(["V registru nejsou dostupné žádné nástroje.", ""])

    mismatches = sorted(registered_names ^ defined_names)
    if mismatches:
        lines.extend(
            [
                "## Nekonzistence registru",
                "",
                "Následující položky nejsou současně v registru implementací "
                "i v definicích předávaných LLM:",
                "",
                *[f"- `{name}`" for name in mismatches],
                "",
            ]
        )

    lines.extend(["## Další funkce a omezení", ""])
    for feature in config.CAPABILITY_FEATURES.values():
        status = "IMPLEMENTOVÁNO" if feature["enabled"] else "NEIMPLEMENTOVÁNO"
        lines.append(f"- **{feature['label']}** — {status}. {feature['details']}")

    lines.extend(
        [
            "",
            "## Provozní limity",
            "",
            f"- Maximální počet rozhodovacích kroků: `{config.MAX_AGENT_STEPS}`",
            f"- Maximální počet volání nástrojů v jednom běhu: `{config.MAX_TOOL_CALLS}`",
            f"- Počet zpráv historie načítaných z paměti: `{config.MAX_HISTORY_MESSAGES}`",
            f"- Maximální velikost čteného souboru: `{config.MAX_FILE_SIZE}` bajtů",
            f"- Maximální počet položek ve výpisu souborů: `{config.MAX_LIST_FILES}`",
            "",
            "## Důležitá hranice",
            "",
            "Tento katalog popisuje deklarovanou konfiguraci a registrované "
            "funkce. Neprokazuje správnost faktických odpovědí modelu ani "
            "nezaručuje, že model vždy dodrží systémové instrukce. Skutečné "
            "vykonání nástroje řídí Python aplikace.",
            "",
        ]
    )
    return "\n".join(lines)


def write_capabilities_file(path: Path | None = None) -> str:
    """Vygeneruje CAPABILITIES.md a vrátí přesně zapsaný obsah."""

    target = path or (config.BASE_DIR / "CAPABILITIES.md")
    content = build_capabilities_markdown()
    target.write_text(content, encoding="utf-8")
    return content


def get_agent_capabilities_context() -> str:
    """Vrátí aktuální katalog pro system message; nepoužívá zastaralý soubor."""

    return build_capabilities_markdown()
