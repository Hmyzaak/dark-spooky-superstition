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
- dlouhodobé ukládání uživatelských a finálních odpovědí do SQLite;
- pokračování agenta i při nedostupnosti SQLite paměti s upozorněním uživatele;
- atomické ukládání uživatelského vstupu a odpovědi v jedné transakci;
- zachytávání neočekávaných chyb LLM klienta a nástrojů;
- ověřování struktury odpovědi modelu před zpracováním volání nástrojů;
- převod síťových chyb poskytovatelů na společnou výjimku `LLMError`;
- omezené opakování dočasných HTTP a síťových chyb;
- respektování hlavičky `Retry-After` a exponenciální prodlevy s horním limitem;
- pravidla system promptu pro práci s nejistotou, faktickými tvrzeními a výsledky nástrojů;
- upozornění uživatele, že agent nemá internetové vyhledávání ani externí ověřování.

**Prakticky ověřeno v rámci vývoje:**

- přímá odpověď modelu přes Groq;
- použití kalkulačky a zpracování jejího výsledku;
- dvě volání nástroje v jednom rozhodovacím cyklu;
- výpis souborů a čtení `workspace/example.txt`;
- uchování historie po ukončení a opětovném spuštění aplikace.

**Známé omezení:** při testu dvou navazujících výpočtů agent provedl oba výpočty správně, ale v konečné odpovědi uvedl pouze druhý výsledek. Provedení nástrojů tedy samo o sobě nezaručuje úplnost závěrečné odpovědi modelu.

## Kvalita odpovědí a ověřování

System prompt v `config.py` vede model k tomu, aby nepřítomnost znalostí nezakrýval domněnkami, nevymýšlel si zdroje a rozlišoval fakta od odhadů. Pokud uživatel upozorní na chybu, model má odpověď znovu posoudit, nikoliv automaticky obhajovat předchozí tvrzení nebo bez posouzení přijmout novou informaci.

Agent nemá internetové vyhledávání. Nemůže proto nezávisle ověřovat aktuální události, málo známé osoby, pořady, produkty ani jiné externí skutečnosti. V těchto případech má přiznat nejistotu a požádat o důvěryhodný zdroj nebo upřesnění. Samotná instrukce v system promptu ale halucinace neodstraní a není zárukou faktické správnosti.

Ověření se v této verzi opírá o omezené a konkrétní mechanismy:

- `calculator` vrací deterministicky vypočtený výsledek; model má převzít jeho hodnotu, nikoliv ji odhadovat;
- `read_file` poskytuje skutečný obsah souboru; tvrzení o něm mají vycházet z tohoto výstupu;
- při více voláních nástrojů jsou všechny jejich výsledky předány modelu v kontextu a system prompt požaduje jejich úplné vyhodnocení;
- automatické testy ověřují, že výsledky nástrojů byly do dalšího požadavku modelu skutečně vloženy.

To není nezávislé ověřování libovolných faktických tvrzení. Model může i přes instrukce vynechat výsledek nebo vytvořit nesprávné tvrzení. Stav `completed` znamená, že model vrátil konečnou textovou odpověď; neznamená, že její fakta byla nezávisle ověřena.

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

Aplikace načítá API klíč z proměnné prostředí `GROQ_API_KEY`. Pokud je klíč uložen v uživatelských nebo systémových proměnných prostředí Windows, není potřeba žádný `.env` soubor ani knihovna `python-dotenv`. Po změně proměnných prostředí otevři nový terminál nebo znovu spusť PyCharm.

Pro jednorázové nastavení pouze v aktuálním okně PowerShellu lze použít:

```powershell
$env:GROQ_API_KEY = "tvuj_api_klic"
python main.py
```

Klíč nikdy nevkládej přímo do zdrojového kódu ani do verzovacího systému.

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

Pracovní prostor je adresář `workspace/` v kořenové složce projektu. Čtení souborů je omezeno na tento adresář, odmítá absolutní cesty a cesty obsahující `..`, kontroluje symbolické odkazy a načte nejvýše 100 000 bajtů. Výpis souborů vrací nejvýše 500 položek a informuje, pokud byl seznam zkrácen. Čtení je v UTF-8.

Lokální databáze `agent_memory.db` obsahuje historii konverzace. Je proto uvedena v `.gitignore` společně se soubory SQLite journal/WAL. Pokud už byla databáze dříve přidána do Gitu, samotné `.gitignore` ji z verzování neodstraní; lze ji přestat sledovat příkazem `git rm --cached agent_memory.db` (lokální soubor zůstane zachován).

SQLite paměť je doplňková. Pokud se ji nepodaří inicializovat, načíst nebo do ní uložit výměnu, agent pokračuje bez historie a výsledek obsahuje samostatné pole `memory_warning`. Chyba paměti nemění stav ani text odpovědi modelu. Dvojice uživatelská zpráva + odpověď se ukládá v jedné SQLite transakci.

Chyby komunikace s LLM klientem a neočekávané chyby nástrojů jsou zachyceny na hranici příslušné komponenty. Agent vrací bezpečnou, uživatelsky srozumitelnou zprávu; technické podrobnosti zapisuje standardní modul `logging` do lokálního souboru `agent.log` v kořenové složce projektu. Tento soubor je v `.gitignore`. Neplatná struktura odpovědi modelu je odmítnuta před dalším zpracováním.

Klienti Groq a Ollama opakují pouze dočasné chyby: HTTP 408, 429 a 5xx a síťové chyby typu `OSError`. Výchozí počet opakování je 2 (tedy nejvýše 3 pokusy); povolené nastavení je 0 až 5 opakování. Prodleva používá exponenciální růst od 1 sekundy a je omezena na 30 sekund. Pokud server pošle `Retry-After`, klient tuto hodnotu respektuje, nejvýše však 30 sekund. Chyby 4xx mimo 408 a 429 a chybná JSON data se neopakují. Timeout 60 sekund pro Groq a 120 sekund pro Ollama se vztahuje na jednotlivý HTTP požadavek; konstruktor nedovolí nastavit více než 300 sekund. Nejde o celkový časový limit celého běhu agenta. Opakování síťové chyby může v krajním případě vytvořit další generaci a spotřebovat další API usage, proto je počet opakování omezen.

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

Sada obsahuje 61 jednotkových testů. Testy používají dočasné soubory a simulované odpovědi; skutečné chování Groq a Ollama je nutné ověřovat samostatně. Test system promptu ověřuje přítomnost pravidel kvality odpovědí; nemůže prokázat, že se jimi jazykový model vždy řídí.

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
│   ├── retry.py
 │   ├── models.py
 │   └── tools.py
 ├── tests/
 │   ├── test_agent.py
 │   ├── test_llm_clients.py
 │   └── test_tools.py
 ├── workspace/
 │   ├── example.txt
 │   └── example_pi.txt
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
