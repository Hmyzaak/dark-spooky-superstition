# AI Agent

Jednoduchý konzolový AI agent v Pythonu. Projekt slouží jako praktický základ pro pochopení fungování AI agenta: komunikuje s jazykovým modelem, podle potřeby volá dostupné nástroje a ukládá historii konverzace do SQLite.

Aktuální implementace používá provider-neutrální datový kontrakt. Agent proto nepracuje přímo s formátem API Groq nebo Ollama; převod zajišťují samostatné adaptéry.

## Stav projektu

**Implementováno:**

- konzolová konverzace v češtině;
- Agent Loop s omezeným počtem rozhodovacích kroků;
- volání nástrojů `calculator`, `list_files` a `read_file`;
- samostatný limit počtu volání nástrojů;
- interní datový kontrakt založený na `dataclass`;
- adaptéry pro Groq Chat Completions API a lokální Ollama API;
- simulovaný LLM klient pro deterministické testování;
- dlouhodobé ukládání uživatelských a finálních odpovědí do SQLite.

**Prakticky ověřeno v rámci vývoje:**

- přímá odpověď modelu přes Groq;
- použití kalkulačky a zpracování jejího výsledku;
- dvě volání nástroje v jednom rozhodovacím cyklu;
- výpis souborů a čtení `workspace/example.txt`;
- uchování historie po ukončení a opětovném spuštění aplikace.

**Známé omezení:** při testu dvou navazujících výpočtů agent provedl oba výpočty správně, ale v konečné odpovědi uvedl pouze druhý výsledek. Provedení nástrojů tedy samo o sobě nezaručuje úplnost závěrečné odpovědi modelu.

## Požadavky

- Python 3.12 nebo novější;
- pro výchozí režim `groq` API klíč Groq;
- pro režim `ollama` lokálně nainstalovaná a spuštěná Ollama a stažený model `qwen3:4b`.

Projekt používá pouze standardní knihovnu Pythonu. Nevyžaduje instalaci externích Python balíčků. Soubor `requirements.txt` proto neobsahuje další závislosti.

## Instalace – Windows / PowerShell

V kořenové složce projektu vytvoř virtuální prostředí a aktivuj ho:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Není nutné instalovat další balíčky. Pokud PowerShell blokuje aktivaci skriptu, lze postupovat podle nastavení Execution Policy ve Windows; není potřeba měnit zdrojový kód aplikace.

## Konfigurace a spuštění

### Groq – výchozí poskytovatel

Nastav API klíč v prostředí PowerShell. Klíč nevkládej přímo do zdrojového kódu ani do verzovacího systému:

```powershell
$env:GROQ_API_KEY = "tvuj_api_klic"
python main.py
```

Výchozí model je `openai/gpt-oss-120b`. Model lze změnit proměnnou prostředí:

```powershell
$env:GROQ_MODEL = "openai/gpt-oss-120b"
```

Proměnné prostředí nastavené příkazem `$env:` platí pro aktuální relaci PowerShellu. Po otevření nového terminálu je případně nastav znovu.

### Ollama – lokální alternativa

Nastav poskytovatele:

```powershell
$env:LLM_PROVIDER = "ollama"
python main.py
```

Ollama musí být spuštěná a model `qwen3:4b` musí být stažený. Výchozí adresa API je `http://localhost:11434/api/chat`.

### Ukončení aplikace

V konzoli napiš `exit`, `quit` nebo `konec`. Aplikaci lze ukončit také pomocí `Ctrl+C`.

## Používání nástrojů

Agent má aktuálně k dispozici tři nástroje:

| Nástroj | Účel | Příklad požadavku |
|---|---|---|
| `calculator` | Sčítání, odčítání, násobení a dělení | „Vypočítej 125 * 48.“ |
| `list_files` | Výpis souborů v pracovním prostoru | „Vypiš dostupné soubory.“ |
| `read_file` | Čtení textového souboru z pracovního prostoru | „Přečti example.txt.“ |

Pracovní prostor je adresář `workspace/` v kořenové složce projektu. Čtení souborů je omezeno na tento adresář, odmítá absolutní cesty a cesty obsahující `..`, kontroluje symbolické odkazy a omezuje velikost souboru na 100 000 bajtů. Čtení je v UTF-8.

Agent nespouští libovolný Python kód ani příkazy operačního systému. Dostupné operace jsou omezené na nástroje registrované v `agent/tools.py`.

## Testování

V kořenové složce projektu spusť:

```powershell
python -m unittest discover -s tests -v
```

Kontrola syntaxe a kompilace:

```powershell
python -m compileall -q agent tests main.py config.py
```

Testy používají `MockLLMClient` nebo simulované HTTP odpovědi. Nevyžadují skutečný API klíč ani běžící Ollama. Úspěšný běh automatických testů proto ověřuje především interní logiku a převody dat; sám o sobě nepotvrzuje dostupnost externí služby.

Při přípravě této dokumentace bylo v dodaném projektovém archivu spuštěno 35 jednotkových testů; všechny prošly. Kompilace uvedeným příkazem také prošla. Ruční testy s Groq a soubory jsou popsány výše jako vývojářem provedené ověření.

## Struktura projektu

```text
 dark-spooky-superstition/
 ├── agent/
 │   ├── __init__.py
 │   ├── agent.py
 │   ├── groq_client.py
 │   ├── llm_client.py
 │   ├── memory.py
 │   ├── mock_llm_client.py
 │   ├── models.py
 │   └── tools.py
 ├── tests/
 │   ├── test_agent.py
 │   ├── test_llm_clients.py
 │   └── test_tools.py
 ├── workspace/
 │   └── example.txt
 ├── config.py
 ├── main.py
 ├── requirements.txt
 ├── README.md
 └── ARCHITECTURE.md
```

Databáze `agent_memory.db` se vytvoří automaticky při prvním spuštění. Není součástí zdrojové struktury a její obsah je lokální stav aplikace.

## Další dokumentace

- [`ARCHITECTURE.md`](ARCHITECTURE.md) – technický popis komponent, datového kontraktu a toku požadavku.

## Aktuální hranice projektu

Projekt je výukovým základem jednoho AI agenta, nikoliv hotovým multiagentním systémem. Zatím neobsahuje koordinátora více agentů, plánovač úloh, webové rozhraní, GUI ani automatické spouštění testů vytvořeného softwaru. Tyto možnosti patří do budoucího rozvoje a nejsou součástí aktuálně ověřené funkčnosti.
