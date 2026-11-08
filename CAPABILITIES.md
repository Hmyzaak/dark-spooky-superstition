# Katalog schopností AI agenta

> Tento soubor je generován automaticky. Neupravujte jej ručně.
> Zdroj: `config.py`, `agent/tools.py` (registr a definice nástrojů).

## Stav aplikace

- Zvolený poskytovatel LLM: `groq`
- Podporovaní poskytovatelé: `groq`, `ollama`
- Architektura: jeden AI agent s Agent Loop; nejde o MAS.

## Dostupné nástroje

### `calculator`

Provede matematickou operaci.

Parametry (JSON Schema):

```json
{
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "add",
        "subtract",
        "multiply",
        "divide"
      ]
    },
    "a": {
      "type": "number"
    },
    "b": {
      "type": "number"
    }
  },
  "required": [
    "operation",
    "a",
    "b"
  ]
}
```

### `list_files`

Vypíše nejvýše 500 souborů ve workspace a oznámí, zda byl seznam zkrácen.

Parametry (JSON Schema):

```json
{
  "type": "object",
  "properties": {}
}
```

### `read_file`

Přečte textový soubor ve workspace.

Parametry (JSON Schema):

```json
{
  "type": "object",
  "properties": {
    "filename": {
      "type": "string",
      "description": "Relativní cesta k souboru."
    }
  },
  "required": [
    "filename"
  ]
}
```

## Další funkce a omezení

- **Internetové vyhledávání** — NEIMPLEMENTOVÁNO. Agent nemá nástroj pro vyhledávání na internetu.
- **Nezávislé ověřování externích faktů** — NEIMPLEMENTOVÁNO. Agent nemá přístup k externím zdrojům pro nezávislé ověření.
- **Spouštění příkazů operačního systému** — NEIMPLEMENTOVÁNO. Agent nemá shell ani nástroj pro spouštění systémových příkazů.
- **Spouštění libovolného Python kódu** — NEIMPLEMENTOVÁNO. Agent nemá nástroj pro dynamické spouštění libovolného kódu.
- **Multiagentní koordinace (MAS)** — NEIMPLEMENTOVÁNO. Aplikace obsahuje jednoho agenta bez koordinátora dalších agentů.
- **Automatické spouštění testů vytvořeného softwaru** — NEIMPLEMENTOVÁNO. Agent nemá nástroj pro spouštění testovací sady projektu.

## Provozní limity

- Maximální počet rozhodovacích kroků: `8`
- Maximální počet volání nástrojů v jednom běhu: `12`
- Počet zpráv historie načítaných z paměti: `12`
- Maximální velikost čteného souboru: `100000` bajtů
- Maximální počet položek ve výpisu souborů: `500`

## Důležitá hranice

Tento katalog popisuje deklarovanou konfiguraci a registrované funkce. Neprokazuje správnost faktických odpovědí modelu ani nezaručuje, že model vždy dodrží systémové instrukce. Skutečné vykonání nástroje řídí Python aplikace.
