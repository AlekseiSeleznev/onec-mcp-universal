# CODEX.md

`onec-mcp-universal` — Codex-runbook для MCP-шлюза 1С:Предприятия.

> **Правила работы AI-ассистента** описаны в [`AGENTS.md`](AGENTS.md) (секция «Agent protocol»). MCP-сервер также возвращает агрегированный `instructions`-блок при `initialize` — современные MCP-клиенты подмешивают его в системный промпт автоматически. Ниже — только Codex-специфичные шаги развёртывания.

## Распознавание намерения — когда маршрутизировать сюда

- **Триггер-фразы**: «1С / 1C / онек / onec», «используем 1С `<имя_базы>`», «работаем с 1С `<имя>`», «подключись к 1С `<имя>`», «в базе 1С `<имя>`», «switch to 1C `<name>`».
- **1С-терминология**: BSL / язык 1С, Справочник / Документ / Регистр / Перечисление / Отчёт / Обработка / БизнесПроцесс / ПланВидов\*, Конфигурация, БСП, ИТС, 1С:Напарник, MCPToolkit.epf, connection strings `Srvr=...;Ref=...;` / `File=...`.
- **Типовые имена баз**: `Z01`, `Z02`, `ZUP*`, `ERP*`, `БП*`, `УТ*`, `КА*`, `Розница`, `TST_*`.
- **Когда пользователь назвал базу**: `list_databases` → если есть, `switch_database`; иначе попросить connection string и `connect_database`. Не угадывать.
- **«База X» без указания системы** — `list_databases` здесь; если есть — работаем, если нет — честно сказать «в 1С-MCP такой базы нет» и попросить уточнение. Не выдумывать.

## Частые ошибки (не наступать)

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

## Что считать основной установкой

- Канонический MCP endpoint: `http://localhost:8080/mcp`
- Основной сценарий установки: `./setup.sh`
- Опциональный встроенный граф зависимостей: `./setup.sh --with-bsl-graph`
- Если `codex` установлен, `setup.sh` автоматически регистрирует `onec-universal`
- gateway управляет Docker-контейнерами через внутренний sidecar `docker-control`, а не через прямой `docker.sock`
- `docker-control` принимает только `GET /health` без auth; все `/api/*` закрыты bearer token из `DOCKER_CONTROL_TOKEN`
- `ANONYMIZER_SALT` хранит стабильный salt для маскировки ПД и тоже маскируется в редакторе `.env`

## Требования

### Linux

- Docker 24+ и `docker compose`
- запущенный Docker daemon
- `git`
- `codex` для автоматической регистрации MCP
- установленная платформа 1С в `/opt/1cv8/x86_64/...`, если нужен `platform-context` и host-side BSL export
- `systemd --user`, если нужен автозапуск `onec-export-service.service`

### Windows

- Docker Desktop с WSL2 backend
- Git for Windows или WSL2
- `codex` для автоматической регистрации MCP
- Python 3.10+ для host-side BSL export
- установленная платформа 1С на хосте Windows

## Установка под Codex

### Linux

```bash
git clone https://github.com/AlekseiSeleznev/onec-mcp-universal.git
cd onec-mcp-universal
./setup.sh
```

С графом зависимостей:

```bash
./setup.sh --with-bsl-graph
```

Что делает `setup.sh`:

1. проверяет `git`, Docker, `docker compose`, доступность daemon и наличие `codex`
2. создаёт `.env` из `.env.example`, если файла ещё нет
3. автоопределяет путь к платформе 1С на Linux
4. создаёт placeholder-директории `data/empty-*`
5. гарантирует наличие `DOCKER_CONTROL_TOKEN` и `ANONYMIZER_SALT` в `.env`
6. при включённом `bsl-lsp-bridge` собирает локальный `mcp-lsp-bridge-bsl`
7. запускает Docker stack
8. ждёт health gateway, `docker-control` и, если включён, `bsl-graph`
9. регистрирует `onec-universal` в Codex
10. устанавливает skills в `~/.codex/skills`
11. ставит host export service как user-level `systemd` unit на Linux или Scheduled Task на Windows

### Windows

Запуск из Git Bash:

```bash
git clone https://github.com/AlekseiSeleznev/onec-mcp-universal.git
cd onec-mcp-universal
./setup.sh
```

С графом:

```bash
./setup.sh --with-bsl-graph
```

Windows-специфика:

- `setup.sh` создаёт `docker-compose.override.yml` из `docker-compose.windows.yml`
- gateway работает через bridge-сеть; host-side export идёт через `host.docker.internal`, а `docker-control` доступен внутри сети как `http://docker-control:8091`
- BSL export идёт через host-side Python service
- skills ставятся в `~/.codex/skills`

## Проверка установки

### Linux

```bash
./verify-install.sh
codex mcp list
curl -sf http://127.0.0.1:8080/health
curl -sf http://127.0.0.1:8091/health
curl -sf http://127.0.0.1:8082/health
curl -sf http://127.0.0.1:8888/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/api/docker/system
```

### Windows

```powershell
.\verify-install.ps1
codex mcp list
```

Ожидаемый результат:

- gateway отвечает на `http://localhost:8080/health`
- на Linux `docker-control` отвечает на `http://localhost:8091/health`
- на Linux `docker-control` возвращает `401` на `http://localhost:8091/api/docker/system` без bearer token
- на Windows проверка sidecar выполняется через `verify-install.ps1` изнутри `onec-mcp-gw`; host port `8091` не публикуется
- `codex mcp list` содержит `onec-universal`
- export-host-service отвечает на `http://localhost:8082/health`
- при опциональном графе `http://localhost:8888/health` отвечает успешно

## Тесты

Из-за PEP 668 на свежем Linux используйте виртуальное окружение:

```bash
python3 -m venv .venv
.venv/bin/pip install -r gateway/requirements-dev.txt
cd gateway
../.venv/bin/python -m pytest tests -q
```

Или:

```bash
cd gateway
../.venv/bin/bash ./scripts/test.sh
```

## Переустановка с нуля

### Удалить локальную установку

```bash
codex mcp remove onec-universal || true
systemctl --user disable --now onec-export-service.service || true
docker ps -a --format '{{.Names}}' | rg '^(onec-mcp-gw|onec-mcp-platform|onec-mcp-toolkit|onec-bsl-graph|onec-toolkit-|mcp-lsp-)' | xargs -r docker rm -f
docker volume ls --format '{{.Name}}' | rg '^onec-mcp-universal_' | xargs -r docker volume rm
docker network ls --format '{{.Name}}' | rg '^onec-mcp-universal_' | xargs -r docker network rm
rm -rf ~/.config/onec-gateway ~/.local/state/onec-export
find ~/.codex/skills -maxdepth 1 -type l -print0 | while IFS= read -r -d '' link; do
  target="$(readlink -f "$link")"
  case "$target" in
    */onec-mcp-universal/skills/*) rm "$link" ;;
  esac
done
```

### Поднять заново

```bash
git clone https://github.com/AlekseiSeleznev/onec-mcp-universal.git
cd onec-mcp-universal
./setup.sh --with-bsl-graph
./verify-install.sh
```

## Диагностика

- `docker compose logs`
- `docker ps --format '{{.Names}} {{.Status}}'`
- `codex mcp list`
- `systemctl --user status onec-export-service.service`
- `curl http://localhost:8080/health`
- `curl -H "Authorization: Bearer $(grep '^DOCKER_CONTROL_TOKEN=' .env | cut -d= -f2-)" http://localhost:8091/api/docker/system`
- `curl http://localhost:8080/dashboard`

## Инварианты

- путь BSL workspace, заданный из дашборда, — source of truth
- host export service не должен зависеть от installer-baked workspace path
- `disconnect` сохраняет запись базы в реестре
- `remove` очищает runtime/state/graph, но не удаляет физические BSL-файлы
- `ghcr.io/alekseiseleznev/onec-mcp-universal:latest` должен отражать текущий `main`
- `ghcr.io/alekseiseleznev/onec-mcp-universal-bsl-graph-lite:latest` публикуется отдельно для встроенного graph backend
- `ghcr.io/alekseiseleznev/onec-mcp-universal-docker-control:latest` публикуется отдельно для внутреннего Docker sidecar
