# AI Agent

Jednoduchý konzolový AI agent v Pythonu. Projekt je výukovým a experimentálním základem pro pochopení Agent Loop, volání nástrojů, komunikace s jazykovým modelem a ukládání historie do SQLite.

Agent používá provider-neutrální datový kontrakt. Rozhodovací logika proto není přímo svázána s formátem API konkrétního poskytovatele. Převod požadavků a odpovědí zajišťují samostatné adaptéry.

## Aktuální stav projektu

**Implementováno:**

- konzolové rozhraní pro konverzaci v češtině;
- Agent Loop s limitem počtu požadavků na jazykový model;
- samostatný limit počtu vykonaných volání nástrojů;
- provider-neutrální datové třídy pro zprávy, požadavky, odpovědi a volání nástrojů;
- adaptéry pro Groq Chat Completions API a lokální Ollama Chat API;
- deterministický `MockLLMClient` pro testování bez skutečného LLM;
- nástroje `calculator`, `list_files` a `read_file`;
- omezená práce se soubory v adresáři `workspace/`;
- SQLite historie konverzace;
- pokračování běhu i při nedostupnosti paměti, s upozorněním ve výsledku;
- atomické uložení uživatelského vstupu a finální odpovědi v jedné transakci;
- validace základní struktury odpovědí LLM a volání nástrojů;
- kategorizace chyb LLM a nástrojů;
- omezené opakování vybraných dočasných HTTP a síťových chyb;
- generování katalogu `CAPABILITIES.md` z konfigurace a registru nástrojů;
- automatické testy Agent Loop, adaptérů, paměti a nástrojů.

**Stav ověření tohoto archivu:**

- automatická sada: **74 testů úspěšných**;
- `python -m compileall -q agent tests main.py config.py`: dokončeno s návratovým kódem 0;
- testy používají mocky a simulované HTTP odpovědi; samy o sobě nepotvrzují aktuální dostupnost Groq ani lokální instalace Ollama.

**Známá omezení:**

- Agent je jediná instance AI agenta, nikoliv multiagentní systém (MAS).
- Nemá internetové vyhledávání ani nástroj pro nezávislé ověřování externích faktů.
- Nemá nástroj pro zápis nebo úpravu souborů.
- Nemá nástroj pro spouštění shell příkazů, Python kódu ani automatických testů jiného projektu.
- Nemá samostatný plánovač úloh, evidenci důkazů o provedených akcích ani nezávislou kontrolu splnění zadání.
- Stav `completed` znamená, že Agent Loop obdržel neprázdnou finální textovou odpověď. Neprokazuje správnost odpovědi ani úplné splnění požadavku.
- System prompt model instruuje, aby pracoval s nejistotou a výsledky nástrojů správně, ale samotná instrukce toto chování nezaručuje.

## Architektura v kostce

Hlavní části aplikace mají oddělené odpovědnosti:

- `agent/agent.py` řídí Agent Loop a sestavuje kontext konverzace.
- `agent/models.py` definuje interní datový kontrakt.
- `agent/llm_client.py` obsahuje protokol `LLMClient`, společné výjimky a adaptér Ollama.
- `agent/groq_client.py` implementuje adaptér Groq.
- `agent/tools.py` registruje a vykonává povolené nástroje.
- `agent/memory.py` ukládá historii do SQLite.
- `agent/retry.py` sjednocuje politiku opakování HTTP požadavků.
- `config.py` obsahuje konfiguraci, provozní limity a system prompt.
- `main.py` je vstupním bodem konzolové aplikace.

Podrobnosti jsou v dokumentu [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Požadavky

- Python 3.12 nebo novější.
- Pro výchozí režim `groq`: API klíč Groq.
- Pro režim `ollama`: lokálně nainstalovaná a spuštěná Ollama a stažený model `qwen3:1.7b`.

Projekt používá standardní knihovnu Pythonu. `requirements.txt` je proto prázdný a není nutné instalovat externí Python balíčky.

## Instalace – Windows / PowerShell

V kořenové složce projektu vytvoř a aktivuj virtuální prostředí:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Není nutné instalovat další balíčky.

## Konfigurace a spuštění

### Groq – výchozí poskytovatel

Výchozí poskytovatel je `groq`. API klíč se načítá z proměnné prostředí `GROQ_API_KEY`.

Pro jednorázové nastavení v aktuálním okně PowerShellu:

```powershell
$env:GROQ_API_KEY = "tvuj_api_klic"
python main.py
```

Výchozí model je `openai/gpt-oss-120b`. Lze jej změnit proměnnou prostředí:

```powershell
$env:GROQ_MODEL = "nazev_modelu"
```

API klíč nevkládej do zdrojového kódu ani do verzovacího systému. Není potřeba `.env` soubor ani knihovna `python-dotenv`.

### Ollama – lokální alternativa

Nastav poskytovatele a spusť aplikaci:

```powershell
$env:LLM_PROVIDER = "ollama"
python main.py
```

Ollama musí běžet lokálně a model `qwen3:1.7b` musí být stažený. Výchozí API endpoint je `http://localhost:11434/api/chat`.

### Ukončení

V konzoli zadej `exit`, `quit` nebo `konec`. Aplikaci lze ukončit také pomocí `Ctrl+C`.

## Dostupné nástroje

| Nástroj | Funkce | Omezení |
|---|---|---|
| `calculator` | Sčítání, odčítání, násobení a dělení | Nepodporuje mocniny ani odmocniny. |
| `list_files` | Výpis souborů ve `workspace/` | Vrací nejvýše 100 položek. |
| `read_file` | Čtení textového souboru z `workspace/` | UTF-8, nejvýše 100 000 bajtů před zkrácením výstupu. |

### Pracovní prostor a limity výstupů

Pracovní prostor je adresář `workspace/` v kořeni projektu. Nástroje odmítají absolutní cesty, průchod do nadřazených adresářů a symbolické odkazy. Výpis souborů ignoruje symbolické odkazy na soubory i adresáře.

Výstup jednoho nástroje je omezen na 8 000 znaků. Souhrnný rozpočet výstupů nástrojů v jednom běhu Agent Loop je 16 000 znaků. Dlouhý výstup může být zkrácen a opatřen informací o zkrácení. Při vyčerpání souhrnného limitu se další výstup nahradí stručnou chybovou informací.

Ochrana cest a symbolických odkazů snižuje riziko přístupu mimo workspace, ale není úplným bezpečnostním auditem. Neřeší všechny možné závody při souběžné změně adresářů jiným lokálním procesem.

### SQLite paměť

Databáze `agent_memory.db` se vytvoří automaticky v kořenovém adresáři projektu. Uchovává uživatelské zprávy a finální odpovědi asistenta. Výsledky nástrojů a mezilehlé zprávy se do databáze neukládají.

Paměť je doplňková služba. Pokud se ji nepodaří inicializovat, načíst nebo do ní uložit výměnu, agent pokračuje a vrací samostatné upozornění `memory_warning`. Historie je v této verzi společná a není rozdělena na uživatele nebo konverzační vlákna.

Databáze a soubory SQLite journal/WAL jsou uvedeny v `.gitignore`, protože mohou obsahovat soukromou historii. Pokud již byly dříve přidány do Gitu, samotné `.gitignore` je z verzování neodstraní.

## Chyby a opakování požadavků

Výsledek agenta obsahuje stav `status` a doplňující diagnostická pole:

- `completed` – model vrátil neprázdnou finální textovou odpověď;
- `error` – běh skončil chybou;
- `limit_reached` – byl dosažen limit kroků nebo volání nástrojů;
- `error_type` – diagnostická kategorie chyby, pokud je relevantní;
- `tool_errors` – počet neúspěšných výsledků nástrojů;
- `memory_warning` – upozornění na problém s pamětí.

Je možné, že `status="completed"` bude současně s `error_type="tool_execution_error"`. Znamená to, že Agent Loop doběhl do finální odpovědi, ale nejméně jeden nástroj selhal. Neznamená to, že požadavek uživatele byl splněn.

Klienti opakují pouze vybrané dočasné chyby: HTTP 408, 429, 5xx a síťové chyby `OSError`. Groq navíc rozpoznává HTTP 413 jako limit TPM pouze tehdy, když text chyby obsahuje odpovídající indikaci. Chyby validace volání nástrojů se neopakují. Výchozí `max_retries=2` znamená nejvýše tři pokusy. Prodleva je omezená a může respektovat hlavičku `Retry-After`. Timeout se vztahuje na jednotlivý HTTP požadavek, nikoliv na celý běh agenta.

## Testování

V kořenové složce projektu spusť:

```powershell
python -m unittest discover -s tests -v
```

Kontrola syntaxe a kompilace:

```powershell
python -m compileall -q agent tests main.py config.py
```

Testy využívají `MockLLMClient`, dočasné soubory a simulované HTTP odpovědi. Nepotřebují skutečný API klíč ani běžící Ollama. Ověřují interní logiku, nikoliv aktuální dostupnost externích služeb nebo spolehlivost konkrétního jazykového modelu.

Test system promptu ověřuje přítomnost instrukcí v kontextu předaném modelu. Nemůže dokázat, že se jimi model bude vždy řídit.

## Struktura projektu

```text
project-root/
├── agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── capabilities.py
│   ├── groq_client.py
│   ├── llm_client.py
│   ├── memory.py
│   ├── mock_llm_client.py
│   ├── models.py
│   ├── retry.py
│   └── tools.py
├── scripts/
│   ├── __init__.py
│   └── generate_capabilities.py
├── tests/
│   ├── test_agent.py
│   ├── test_capabilities.py
│   ├── test_llm_clients.py
│   └── test_tools.py
├── workspace/
│   ├── agent_loop_test.txt
│   ├── Plan_etapy_1.txt
│   └── security_test.txt
├── config.py
├── main.py
├── requirements.txt
├── README.md
├── ARCHITECTURE.md
└── CAPABILITIES.md
```

Databáze, log `agent.log` a další lokální provozní soubory vznikají až při běhu aplikace a nejsou součástí této struktury zdrojových souborů.

## Katalog schopností

`CAPABILITIES.md` je generovaný soubor. Vzniká z konfigurace v `config.py` a registru i definic nástrojů v `agent/tools.py`. Lze jej aktualizovat příkazem:

```powershell
python -m scripts.generate_capabilities
```

Aplikace se při spuštění pokusí katalog aktualizovat. Pokud zápis selže, může pokračovat; aktuální katalog pro model sestavuje přímo z Python zdrojů. Ruční změny v `CAPABILITIES.md` nemění oprávnění agenta.

## Hranice a další rozvoj

Tento projekt je výchozím experimentálním agentem. Není hotovým programátorským agentem a není MAS. Neumí bezpečně zapisovat a upravovat soubory, spouštět testy projektů ani ověřovat jejich výsledky. Tyto schopnosti vyžadují samostatný návrh bezpečnostních pravidel, nástrojů a evidence provedených akcí.

Budoucí rozvoj může zahrnovat bezpečný zápis souborů, řízené spouštění testů, strukturovanou evidenci volání nástrojů a důkazů, diagnostiku chyb a teprve později koordinaci specializovaných agentů. Jde o plánovaný rozvoj, nikoliv o funkce aktuální verze.

Projekt AI agenta a případné aplikace, které bude agent vyvíjet (například Magnum Opus), musí zůstat samostatnými softwarovými projekty.
