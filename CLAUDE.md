# Инструкции для AI-ассистентов (Claude Code / Codex / Cursor)

Этот файл — **протокол работы** AI-ассистента с проектом. Claude Code автоматически подхватывает `CLAUDE.md` при открытии репозитория; Codex делает то же самое с `AGENTS.md`.

---

## TL;DR

Всё, что связано с 1С:Предприятие (запросы, метаданные, BSL, БСП, граф зависимостей) — **делается через MCP-сервер `onec-mcp-universal`** по адресу `http://localhost:8080/mcp`.

**Не пиши BSL и не выдумывай имена функций из памяти. Сначала вызывай MCP-инструменты. Если инструмент недоступен — честно скажи об этом пользователю.**

---

## Распознавание намерения — когда маршрутизировать сюда

**Фразы, пинящие сессию на этот MCP:**
- «1С / 1C / онек / onec», «используем 1С `<имя_базы>`», «работаем с 1С `<имя>`», «подключись к 1С `<имя>`», «в базе 1С `<имя>`», «switch to 1C `<name>`».

**1С-терминология — любой маркер ниже → этот MCP:**
BSL / язык 1С, Справочник / Документ / Регистр / Перечисление / Отчёт / Обработка / БизнесПроцесс / ПланВидов\*, Конфигурация, БСП, ИТС, 1С:Напарник, MCPToolkit.epf, строки подключения вида `Srvr=...;Ref=...;` или `File=...`.

**Типовые имена баз:** `Z01`, `Z02`, `ZUP*`, `ERP*`, `БП*`, `УТ*`, `КА*`, `Розница`, `TST_*`.

**Что делать, когда пользователь назвал базу** («используем 1С Z01»):
1. `list_databases` — если `Z01` есть → `switch_database name=Z01`.
2. Если нет — спросить у пользователя строку подключения и вызвать `connect_database`. Не угадывать.

**Если пользователь сказал просто «база X»** без явного указания системы — вызови `list_databases` здесь; если `X` есть — работаем с ним, если нет — честно сообщи «в 1С-MCP такой базы нет» и попроси уточнения. Не выдумывай подключение.

---

## Правила

### 1. Перед любой задачей по 1С

1. `get_server_status` — убедиться, что шлюз и бэкенды живы.
2. `list_databases` — узнать активную БД. Если БД не подключена, не придумывать — сказать пользователю «открой `1c/MCPToolkit/build/MCPToolkit.epf` в 1С и нажми Подключиться».

### 2. Перед написанием BSL, вызывающего существующий API

1. `symbol_explore` или `bsl_search_tool` — найти функцию по имени/фрагменту.
2. `hover` / `definition` — прочитать точную сигнатуру и doc-комментарий.
3. **Только после этого** — писать код.

### 3. Перед выполнением запроса к 1С

1. `get_metadata` — убедиться, что объекты и реквизиты существуют.
2. `validate_query` — ловит синтаксические ошибки без отправки в 1С.
3. `execute_query` — сам запрос. Если сомневаешься в размере выборки — добавляй `ВЫБРАТЬ ПЕРВЫЕ N`.

### 4. Перед редактированием BSL-модуля

1. `document_diagnostics uri=file:///projects/<path>` — посмотреть текущие предупреждения.
2. `write_bsl` — запись в рабочий каталог (автоматически триггерит reindex + обновление графа).
3. Не редактируй BSL-файлы напрямую — LSP и полнотекстовый индекс не увидят правку вовремя.

### 5. Вопрос про БСП / ИТС

1. Если `its_search` доступен (настроен `NAPARNIK_API_KEY`) — вызвать **первым**. Это официальная ИТС / 1С:Напарник.
2. `bsl_search_tool` по имени общего модуля БСП (`ОбщегоНазначения`, `РаботаСФайлами`…) — примеры использования в текущей конфигурации.
3. `hover` / `definition` на конкретной функции БСП — описание из doc-комментария.
4. Собрать ответ из реального кода, а не из памяти.

### 6. Граф зависимостей / анализ влияния

- `graph_search` + `graph_related` — найти объект и его связи.
- Пользователь может открыть визуализатор: `http://localhost:8888/`.
- В одной базе данных одновременно — связи внутри БД, межбазовых связей нет.

### 7. Работа с конфигурацией без прямого подключения

- Скиллы для Codex в `skills/*/SKILL.md` — DB-операции, сборка EPF, редактирование конфигурации через XML. Работают через локальные скрипты (вызов `1cv8 DESIGNER`), не через MCP.
- Если ты в Claude Code — используй MCP-инструменты (`write_bsl`, `export_bsl_sources`, `reindex_bsl`). Прямой запуск shell-скриптов из `skills/` нужен только для Codex slash-команд.

### 8. Когда MCP не помогает

- Вопрос про синтаксис языка 1С (типы, операторы) — `get_bsl_syntax_help` или встроенный ресурс `syntax_1c.txt`.
- Если запрос касается 1С-платформенного API, которого нет ни в ИТС ни в подключённой конфигурации — **честно скажи**: «я не нашёл упоминаний X ни в рабочем каталоге, ни в ИТС — уточните версию платформы / БСП / где видели это». Не фантазируй.

---

## Категории инструментов

| Категория | Инструменты |
|---|---|
| Данные | `execute_query`, `execute_code`, `get_metadata`, `get_event_log`, `get_object_by_link`, `get_link_of_object`, `find_references_to_object`, `get_access_rights`, `query_stats` |
| Поиск BSL | `bsl_index`, `bsl_search_tool`, `reindex_bsl` |
| LSP-навигация | `symbol_explore`, `definition`, `hover`, `document_diagnostics`, `call_hierarchy`, `call_graph`, `project_analysis`, `code_actions`, `rename`, `prepare_rename`, `get_range_content`, `selection_range`, `did_change_watched_files`, `lsp_status` |
| Запись BSL | `write_bsl` (автопереиндексация) |
| Граф | `graph_stats`, `graph_search`, `graph_related` |
| Жизненный цикл БД | `connect_database`, `list_databases`, `switch_database`, `disconnect_database`, `export_bsl_sources`, `get_export_status` |
| Справочник платформы | `get_bsl_syntax_help` |
| ИТС / 1С:Напарник | `its_search` (появляется при `NAPARNIK_API_KEY`) |
| Прочее | `enable_anonymization`, `disable_anonymization`, `invalidate_metadata_cache`, `get_server_status` |

---

## Готовые MCP-prompts

Сервер отдаёт `prompts/list`, где есть готовые сценарии:

- **connect_and_inspect** — подключить базу и показать обзор конфигурации.
- **describe_object** (arg: `metadata_object`) — полное описание объекта 1С.
- **safe_query** (arg: `query`) — validate → explain → execute с лимитом.
- **find_usage** (arg: `symbol`) — все использования функции/объекта.
- **bsp_api** (arg: `task`) — решение через БСП с ИТС-источниками.
- **reindex_after_export** — переиндексация после выгрузки BSL.

Если работаешь в Claude Code — эти prompts доступны через слэш-меню.

---

## Частые ошибки и как их избегать

1. **Имена аргументов** — всегда читай `inputSchema` из `tools/list` перед первым вызовом. Большинство tool-level ошибок — `'X' is a required property` — означают, что ты выдумал имя аргумента.
   - `write_bsl` — `file` (не `path`), `content`.
   - `get_range_content` — плоские `start_line/start_character/end_line/end_character`, **не** объект `range`.
   - `project_analysis.analysis_type` — только из фиксированного набора: `workspace_symbols`, `document_symbols`, `references`, `definitions`, `text_search`, `workspace_analysis`, `symbol_relationships`, `file_analysis`, `pattern_analysis`.
   - `find_references_to_object` — `target_object_description` это объект (`{"fullName":"Справочник.X"}` или с `_objectRef`), `search_scope` это **массив** имён объектов метаданных, не путей файлов.
   - `get_object_by_link` / `get_link_of_object` — описание объекта должно содержать `_objectRef`, `УникальныйИдентификатор`, `ТипОбъекта`. Строка типа `"Справочник.Валюты.USD"` не принимается.
   - `did_change_watched_files` — `language` обязателен, `changes_json` — это JSON-**строка**, не массив.
   - `info` — `name` + `type` (`method` / `property` / `type`).
   - `getMembers` / `getMember` / `getConstructors` — `typeName` должен быть известным типом 1С-платформы (`СправочникМенеджер`, `Массив`…).
   - LSP `search` — `type` это LSP symbol-kind (class/function/method/variable), не произвольная строка.

2. **URI для LSP-инструментов** — у каждой БД свой LSP-контейнер; путь всегда относительный к корню выгрузки этой БД:
   - Правильно: `file:///projects/CommonModules/ZipАрхивы/Ext/Module.bsl`
   - Неправильно: `file:///projects/Z01/CommonModules/...` (префикс с именем БД не нужен).

3. **Multi-DB и concurrency** — активная база привязана к `Mcp-Session-Id`. `switch_database` делается один раз на сессию. Две параллельные сессии (Claude Code + Codex, например) могут держать **разные** активные БД одновременно — они полностью изолированы; у каждой БД свой toolkit-контейнер (порты 6100, 6101…) и свой LSP-контейнер.

4. **Сессия умерла (HTTP 404 / hang)** — gateway удаляет устаревшие сессии. Переоткрой `initialize` + `notifications/initialized`, не ретраи со старым SID.

5. **`epf_connected: false`** — EPF-обработка в 1С не запущена. Все `execute_query` / `execute_code` вернут `ERROR: EPF for database 'X' is not connected`. Не фантазируй результаты — попроси пользователя открыть MCPToolkit.epf в этой базе и нажать «Подключиться».

6. **platform-context в отдельном бэкенде** — `info/getMembers/getMember/getConstructors` работают **без** подключённой БД. Их «тип не найден» — это валидный content-ответ, а не падение шлюза.

7. **Перед деструктивом** — `update/insert/delete` через `execute_code`, массовые изменения BSL через `write_bsl` — всегда сначала покажи пользователю, что именно собираешься сделать, и дождись подтверждения. В restricted-режиме write-операции откажут на уровне 1С — переспроси, нужна ли запись.

---

## Поведение при сбоях

| Ситуация | Поведение |
|---|---|
| `get_server_status` показывает падение бэкенда | Сообщи пользователю имя бэкенда и ссылку `http://localhost:8080/dashboard#settings` |
| `list_databases` пуст | Проси открыть EPF и нажать Подключиться |
| `execute_query` возвращает timeout | Уточни у пользователя — увеличить лимит, сузить выборку, или проблема в связке 1С-сервер? |
| `its_search` отсутствует в `tools/list` | Значит не задан `NAPARNIK_API_KEY`. Сказать пользователю: «ИТС-поиск требует ключ; в `.env` задать `NAPARNIK_API_KEY=...`». |
| MCP-ошибка `Missing Authorization header` | Убедись, что gateway пересобран и `.env` содержит `DOCKER_CONTROL_TOKEN` |

---

## Подробности
- Архитектура: [`AGENTS.md`](AGENTS.md).
- Памятка для Codex: [`CODEX.md`](CODEX.md).
- Полная документация проекта — в `README.md` и дашборде `http://localhost:8080/dashboard`.
