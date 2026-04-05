# onec-mcp-universal

Единый MCP-шлюз для работы с 1С:Предприятие из AI-ассистентов — Claude Code, Cursor, Windsurf и любых MCP-клиентов.

Один адрес `http://localhost:8080/mcp` вместо нескольких отдельных MCP-подключений. Шлюз принимает запросы от AI и автоматически маршрутизирует их к нужному бэкенду.

---

## Содержание

- [Возможности](#возможности)
- [Требования](#требования)
- [Установка](#установка)
- [Подключение к AI-ассистенту](#подключение-к-ai-ассистенту)
- [Подключение базы 1С](#подключение-базы-1с)
- [Примеры команд AI](#примеры-команд-ai)
- [Работа с несколькими базами](#работа-с-несколькими-базами)
- [Опциональные модули](#опциональные-модули)
- [Установка на Windows](#установка-на-windows)
- [Диагностика](#диагностика)
- [Обновление](#обновление)
- [Архитектура](#архитектура)
- [Используемые проекты](#используемые-проекты)
- [Удаление](#удаление)
- [Лицензия](#лицензия)

---

## Возможности

**38 инструментов + 1 ресурс:**

| Категория | Кол-во | Инструменты |
|---|---|---|
| **Данные 1С** | 8 | `execute_query` — запросы к БД на языке 1С с параметрами и лимитами<br>`execute_code` — выполнение произвольного кода 1С на сервере или клиенте<br>`get_metadata` — структура конфигурации: реквизиты, табличные части, типы<br>`get_event_log` — чтение журнала регистрации с фильтрацией<br>`get_object_by_link` — получение объекта по навигационной ссылке<br>`get_link_of_object` — генерация ссылки из результатов запроса<br>`find_references_to_object` — поиск использований объекта в документах и регистрах<br>`get_access_rights` — анализ ролей и прав на объекты метаданных |
| **Документация платформы** | 5 | Поиск по API встроенного языка 1С, методы типов, конструкторы, описания параметров |
| **Навигация по BSL-коду** | 14 | `symbol_explore` — семантический поиск символов в коде<br>`definition` — переход к определению<br>`hover` — информация о символе<br>`call_hierarchy` — дерево вызовов<br>`call_graph` — граф вызовов с определением точек входа<br>`document_diagnostics` — ошибки и предупреждения в файле<br>`project_analysis` — анализ проекта: символы, связи, структура<br>`code_actions` — рекомендации по исправлению кода<br>`rename` / `prepare_rename` — переименование символов<br>`get_range_content` — чтение фрагмента кода по координатам<br>`selection_range` — интеллектуальное выделение<br>`did_change_watched_files` — уведомление об изменении файлов<br>`lsp_status` — статус индексации |
| **Управление шлюзом** | 11 | `connect_database` — подключение базы 1С (создаёт Docker-контейнеры)<br>`disconnect_database` — отключение базы<br>`switch_database` — переключение между базами<br>`list_databases` — список подключённых баз<br>`get_server_status` — здоровье бэкендов<br>`validate_query` — проверка синтаксиса запроса (статика + сервер)<br>`reindex_bsl` — принудительное переиндексирование BSL-файлов<br>`export_bsl_sources` — выгрузка исходников конфигурации<br>`graph_stats` / `graph_search` / `graph_related` — граф зависимостей |

**MCP-ресурс:** `syntax_1c.txt` — справочник синтаксиса встроенного языка 1С, используется AI как контекст при написании BSL-кода.

**Ключевые особенности v0.3:**

- **Auto-reconnect баз** — при перезапуске шлюза ранее подключённые базы восстанавливаются автоматически
- **StdioBackend reconnect** — автоматическое переподключение LSP при обрыве `docker exec`
- **Команда reindex_bsl** — принудительное переиндексирование при изменении BSL-файлов
- **CI/CD** — автосборка Docker-образа и публикация в GitHub Container Registry
- **Unit-тесты** — pytest для ядра шлюза (валидация запросов, BackendManager, registry)

---

## Требования

- **Docker** 24+ и Docker Compose v2
- **Linux** (Ubuntu 22.04+) или **Windows** 10/11 с Docker Desktop (WSL2)
- **Платформа 1С:Предприятие** 8.3, установленная на хосте
- **Информационная база 1С** (серверная или файловая)

---

## Установка

### 1. Скачать проект

```bash
git clone https://github.com/AlekseiSeleznev/onec-mcp-universal.git
cd onec-mcp-universal
```

### 2. Создать файл настроек

```bash
cp .env.example .env
```

Указать путь к платформе 1С:

```env
PLATFORM_PATH=/opt/1cv8/x86_64/8.3.27.2074
```

> Узнать путь: `ls /opt/1cv8/x86_64/`

### 3. Запустить сервис выгрузки исходников

Сервис работает на хосте и выгружает конфигурацию 1С в BSL-файлы:

```bash
python3 tools/export-host-service.py --port 8082 --workspace ~/1c-projects
```

Оставить терминал открытым, либо настроить запуск через systemd.

### 4. Запустить контейнеры

```bash
docker compose up -d
```

Первый запуск: 2-3 минуты (скачивание образов + сборка шлюза).

### 5. Проверить

```bash
curl http://localhost:8080/health
```

Ожидаемый ответ:

```json
{
  "status": "ok",
  "backends": {
    "onec-toolkit": {"ok": true, "tools": 8},
    "platform-context": {"ok": true, "tools": 5},
    "bsl-lsp-bridge": {"ok": true, "tools": 14}
  }
}
```

---

## Подключение к AI-ассистенту

### Claude Code

```bash
claude mcp add onec --transport http http://localhost:8080/mcp
```

### Cursor

**Settings** → **MCP** → **Add new MCP server**:
- Name: `onec`
- Type: `HTTP`
- URL: `http://localhost:8080/mcp`

### Windsurf / другие MCP-клиенты

Любой клиент с поддержкой Streamable HTTP:

```
http://localhost:8080/mcp
```

---

## Подключение базы 1С

### 1. Подключить базу через AI

```
Подключи базу ERP_DEMO, строка подключения Srvr=localhost;Ref=ERP_DEMO;, папка /home/user/projects
```

Шлюз создаст два Docker-контейнера: `onec-toolkit-ERP_DEMO` (данные) и `mcp-lsp-ERP_DEMO` (навигация по коду).

**Форматы строки подключения:**

| Тип базы | Формат |
|---|---|
| Серверная | `Srvr=имя_сервера;Ref=имя_базы;` |
| С авторизацией | `Srvr=имя_сервера;Ref=имя_базы;Usr=admin;Pwd=пароль;` |
| Файловая | `File=/путь/к/базе` |

### 2. Открыть обработку MCPToolkit в 1С

Открыть `1c/MCPToolkit.epf` в клиенте 1С:Предприятие. Обработка является посредником между шлюзом и базой — держать открытой во время работы.

### 3. Выгрузить исходники BSL

```
Выгрузи исходники конфигурации
```

На крупных конфигурациях (ERP, ЗУП) индексация занимает 3-5 минут. Проверить готовность:

```
Покажи статус индексации BSL
```

---

## Примеры команд AI

Все примеры — запросы на естественном русском языке в чате с AI.

### Запросы к данным

```
Выбери первые 10 контрагентов с наименованием и ИНН
```

```
Покажи документы реализации за последний месяц с суммой больше 100 000
```

```
Выбери остатки товара "Кабель ВВГ 3x2.5" на всех складах
```

```
Посчитай непроведённые документы поступления за текущий год
```

### Валидация запросов

```
Проверь запрос:
ВЫБРАТЬ Ссылка, Наименование ИЗ Справочник.Контрагенты ГДЕ Ссылка В (&Список
```

> AI обнаружит незакрытую скобку и предложит исправление.

### Метаданные

```
Покажи структуру документа РеализацияТоваровУслуг
```

```
Какие реквизиты есть у справочника Номенклатура?
```

```
Сколько объектов в конфигурации по каждому типу?
```

### Выполнение кода

```
Выполни код: Результат = ТекущаяДатаСеанса()
```

```
Выполни код: Результат = Метаданные.Конфигурация.Версия
```

### Права доступа

```
Какие роли имеют право изменять справочник Номенклатура?
```

```
Покажи права на документ РеализацияТоваровУслуг — чтение, добавление, изменение
```

### Навигация по коду BSL

```
Найди процедуру ЗаполнитьТабличнуюЧастьТовары в конфигурации
```

```
Покажи граф вызовов функции ПолучитьСтруктуруОплаты
```

```
Какие ошибки в модуле ИнтеграцияЕГАИС?
```

```
Покажи код функции ЗаполнитьТабличнуюЧастьТовары из модуля ИнтеграцияЕГАИС
```

### Документация платформы

```
Как работает метод НайтиСтроки у ТаблицыЗначений?
```

```
Какие параметры у конструктора ОписаниеОповещения?
```

### Журнал регистрации

```
Покажи последние 10 ошибок из журнала регистрации за сегодня
```

```
Найди записи журнала от пользователя Иванов за последний час
```

### Поиск использований

```
Найди все документы где используется контрагент "Электробыт"
```

```
Открой контрагента по ссылке e1cib/data/Справочник.Контрагенты?ref=80260015e9b8c48d11e2c2d02ff9d345
```

### Переиндексирование

```
Переиндексируй BSL-файлы
```

---

## Работа с несколькими базами

```
Подключи базу ZUP, строка подключения Srvr=myserver;Ref=zup;, папка /home/user/projects/ZUP
```

```
Переключись на базу ZUP
```

```
Покажи список подключённых баз
```

```
Отключи базу ZUP
```

При перезапуске шлюза все ранее подключённые базы восстанавливаются автоматически.

---

## Опциональные модули

### Тестирование YaXUnit

Запуск тестов, сборка проекта и проверка синтаксиса. Использует [mcp-onec-test-runner](https://github.com/alkoleft/mcp-onec-test-runner).

```bash
cp test-runner/application.yml.example test-runner/application.yml
# Отредактировать application.yml — указать строку подключения
docker compose --profile test-runner up -d
```

Добавить в `.env`:

```env
ENABLED_BACKENDS=onec-toolkit,platform-context,bsl-lsp-bridge,test-runner
```

```bash
docker compose restart gateway
```

Примеры:

```
Запусти все тесты YaXUnit
```

```
Запусти тесты модуля ОбработкаЗаказов
```

### Граф связей конфигурации

Анализ зависимостей между объектами. Использует [bsl-graph](https://github.com/alkoleft/bsl-graph) + NebulaGraph (~4 ГБ RAM).

```bash
docker compose --profile bsl-graph up -d
```

Примеры:

```
Покажи статистику графа объектов конфигурации
```

```
Найди все объекты, связанные с документом ПоступлениеТоваровУслуг
```

---

## Установка на Windows

На Windows платформа 1С работает только на хосте, а не внутри Linux-контейнеров.

### 1. Запустить сервис выгрузки

```cmd
python tools\export-host-service.py --port 8082 --workspace C:\1c-projects
```

### 2. Настроить `.env`

```env
EXPORT_HOST_URL=http://host.docker.internal:8082
```

### 3. Запустить контейнеры

```bash
docker compose up -d
```

> Если `platform-context` не стартует из-за монтирования `/opt/1cv8` — удалить строку `${HOST_PLATFORM_PATH:-/opt/1cv8}:/opt/1cv8:ro` из `docker-compose.yml` в секции `platform-context`.

---

## Диагностика

**Статус бэкендов:**

```bash
curl http://localhost:8080/health
```

Или через AI: `Покажи статус MCP-сервера`

**Логи шлюза:**

```bash
docker logs onec-mcp-gw -f
```

**Логи toolkit конкретной базы:**

```bash
docker logs onec-toolkit-ERP_DEMO -f
```

**Перезапуск шлюза:**

```bash
docker compose restart gateway
```

---

## Обновление

```bash
git pull
docker compose build --no-cache gateway
docker compose up -d
```

---

## Архитектура

```
Claude Code / Cursor / Windsurf
       │ HTTP :8080/mcp (Streamable HTTP)
       ▼
┌──────────────────────────────────────┐
│  onec-mcp-gw  (Python, host network)│
│                                      │
│  Статические бэкенды:                │
│  ├─ onec-toolkit      :6003  (HTTP) │
│  └─ platform-context  :8081  (SSE)  │
│                                      │
│  Динамические бэкенды (per-DB):      │
│  ├─ onec-toolkit-{db} :6100+ (HTTP) │
│  └─ mcp-lsp-{db}      (stdio)      │
│                                      │
│  /data/db_state.json ← persistence  │
└──────────────────────────────────────┘
         ▲
         │  MCPToolkit.epf (клиент 1С)
         │  держит соединение с onec-toolkit
```

| Контейнер | Образ | Роль |
|---|---|---|
| `onec-mcp-gw` | Собирается локально | MCP-шлюз, маршрутизация инструментов |
| `onec-mcp-toolkit` | [roctup/1c-mcp-toolkit-proxy](https://github.com/ROCTUP/1c-mcp-toolkit) | Статический бэкенд данных |
| `onec-mcp-platform` | [ghcr.io/alkoleft/mcp-bsl-platform-context](https://github.com/alkoleft/mcp-bsl-platform-context) | Документация платформы |
| `onec-toolkit-{db}` | roctup/1c-mcp-toolkit-proxy | Динамический бэкенд данных (per-DB) |
| `mcp-lsp-{db}` | mcp-lsp-bridge-bsl | BSL Language Server (per-DB) |

---

## Используемые проекты

### Основные

| Проект | Автор | Назначение |
|---|---|---|
| [1c-mcp-toolkit](https://github.com/ROCTUP/1c-mcp-toolkit) | ROCTUP | Запросы к БД, выполнение кода, метаданные, журнал регистрации, права |
| [mcp-bsl-platform-context](https://github.com/alkoleft/mcp-bsl-platform-context) | alkoleft | Документация API платформы 1С |
| [mcp-bsl-lsp-bridge](https://github.com/alkoleft/mcp-bsl-lsp-bridge) | alkoleft | MCP-мост к BSL Language Server |
| [lsp-session-manager](https://github.com/alkoleft/lsp-session-manager) | alkoleft | Мультиплексор сессий BSL Language Server |
| [bsl-language-server](https://github.com/1c-syntax/bsl-language-server) | 1c-syntax | Language Server для BSL |
| [1c_mcp](https://github.com/vladimir-kharin/1c_mcp) | vladimir-kharin | Справочник синтаксиса BSL |

### Опциональные

| Проект | Автор | Профиль | Назначение |
|---|---|---|---|
| [mcp-onec-test-runner](https://github.com/alkoleft/mcp-onec-test-runner) | alkoleft | `test-runner` | Запуск тестов YaXUnit, сборка, проверка синтаксиса |
| [bsl-graph](https://github.com/alkoleft/bsl-graph) | alkoleft | `bsl-graph` | Граф зависимостей объектов конфигурации |

---

## Удаление

```bash
# Остановить и удалить контейнеры
docker compose down

# Удалить образ шлюза
docker rmi onec-mcp-universal-gateway

# Удалить проект
cd .. && rm -rf onec-mcp-universal

# Удалить MCP-подключение из Claude Code
claude mcp remove onec
```

Данные баз 1С и выгруженные BSL-исходники не затрагиваются.

---

## Лицензия

[MIT](LICENSE) — Copyright (c) 2026 Aleksei Seleznev
