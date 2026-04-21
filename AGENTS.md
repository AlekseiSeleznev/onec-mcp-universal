# AGENTS.md

`onec-mcp-universal` — AI-agnostic MCP-шлюз для 1С:Предприятия.

## Базовые инварианты

- канонический MCP endpoint: `http://localhost:8080/mcp`
- основной bootstrap entrypoint: `./setup.sh`
- README — основная пользовательская документация
- `CODEX.md` — подробный runbook для Codex
- gateway управляет контейнерами только через `docker-control`

## Инварианты workspace и экспорта

- путь BSL workspace, заданный из дашборда, — источник истины
- `BSL_HOST_WORKSPACE` / `BSL_WORKSPACE` в `.env` определяют host export root
- host export service обязан читать актуальный `.env` или явный `output_dir` запроса
- автоиндексация после экспорта должна предпочитать gateway-visible host path и только потом fallback в LSP/container view

## Инварианты lifecycle базы

- `disconnect` останавливает runtime базы, но оставляет запись в реестре
- `remove` очищает runtime/state/graph базы, но не удаляет физические BSL-файлы
- удаление базы не должно возвращать успех до завершения runtime cleanup

## Packaging policy

- `ghcr.io/alekseiseleznev/onec-mcp-universal:latest` отслеживает `main`
- release tags публикуют semver image tags

## Совместимость

- проект нейтрален к конкретному AI-клиенту
- любой MCP-клиент может подключаться вручную к тому же endpoint

## Agent protocol (правила работы для AI-клиента)

Этот раздел — канонический протокол работы AI-ассистента с проектом вне встроенного MCP `instructions`.

Коротко:

- **Intent recognition.** Фразы «используем 1С `<имя>`», «работаем с 1С `<имя>`», «подключись к 1С `<имя>`», «1С / 1C / онек», любые 1С-термины (BSL, Справочник, Документ, Регистр, Конфигурация, БСП, ИТС, `Srvr=…;Ref=…;`, `File=…`, имена баз `Z01`/`ZUP`/`ERP`/`БП`) → **этот MCP**. При упоминании базы: `list_databases` → если есть, `switch_database`; иначе попросить connection string и `connect_database`. Если пользователь сказал «база X» без указания системы — `list_databases`; если есть — работаем, если нет — честно сказать «в 1С-MCP такой базы нет», не выдумывать.
- **Все 1С-задачи — через MCP `onec-mcp-universal`** (`http://localhost:8080/mcp`). Запросы, метаданные, BSL, БСП, граф зависимостей — только через MCP-инструменты, не из памяти LLM.
- **Цепочки инструментов:**
  - запрос → `get_metadata` → `validate_query` → `execute_query`;
  - BSL-вызов → `symbol_explore`/`bsl_search_tool` → `hover`/`definition` → `write_bsl`;
  - БСП-вопрос → `its_search` (если `NAPARNIK_API_KEY` задан) → `bsl_search_tool` → `hover`.
- **Fallback запрещён**. Если инструмент/бэкенд/БД недоступны — сообщить пользователю, не имитировать ответ.
- **MCP-сервер** возвращает при `initialize` агрегированный `instructions`-блок с теми же правилами; актуальный текст — в `gateway/gateway/mcp_server.py::AGENT_INSTRUCTIONS`.
- **Готовые сценарии** публикуются через `prompts/list`: `connect_and_inspect`, `describe_object`, `safe_query`, `find_usage`, `bsp_api`, `reindex_after_export`.
- **Скиллы** для Codex и совместимых локальных skill-runner'ов ставятся `install-skills.sh` / `install-skills.ps1`. Скрипты в `skills/*/scripts/` — Codex-first локальный automation path.

### Частые ошибки (не наступать)

- **Читай `inputSchema` из `tools/list` перед вызовом**. Большинство tool-level ошибок — `'X' is a required property` — из-за выдуманных имён аргументов. Контракты, которые чаще всего путают:
  - `write_bsl` — `file`, не `path`.
  - `get_range_content` — плоские `start_line/start_character/end_line/end_character`, не `range:{start,end}`.
  - `project_analysis.analysis_type` — enum из `workspace_symbols|document_symbols|references|definitions|text_search|workspace_analysis|symbol_relationships|file_analysis|pattern_analysis`.
  - `find_references_to_object.search_scope` — массив имён метаданных (`["Справочник.X","Документ.Y"]`), не файловые пути.
  - `get_object_by_link` / `get_link_of_object` / `find_references_to_object.target_object_description` — объект с `_objectRef`, а не строка `"Справочник.Валюты.USD"`.
  - `did_change_watched_files` — `language` обязателен, `changes_json` — JSON-строка.
  - `info` — `name` + `type` (`method`/`property`/`type`).
  - `getMembers/getMember/getConstructors` — `typeName` это тип 1С-платформы (`СправочникМенеджер`, `Массив`…).
- **LSP URI** — `file:///projects/<relative>`; у каждой БД свой LSP-контейнер, префикс с именем БД не нужен (`file:///projects/CommonModules/...`, не `file:///projects/Z01/CommonModules/...`).
- **Активная БД — per-session**. Вызови `switch_database` один раз на сессию. Разные параллельные сессии могут работать с разными БД — у каждой свой toolkit (порты 6100, 6101…) и свой LSP.
- **HTTP 404 или зависшая сессия** — переинициализируй (`initialize` + `notifications/initialized`), не ретраи со старым `Mcp-Session-Id`.
- **`epf_connected: false`** — 1С-обработка не запущена; `execute_query` вернёт `EPF for database 'X' is not connected`. Просишь пользователя открыть MCPToolkit.epf и нажать «Подключиться», ответ не выдумываешь.
- **Перед деструктивом** (`write_bsl` на существующий модуль, `execute_code` с INSERT/UPDATE/DELETE) — показать план пользователю и дождаться подтверждения.
