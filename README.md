# onec-mcp-universal

Единый MCP-сервер для работы с 1С:Предприятие из AI-ассистентов (Claude Code, Cursor).

Вместо трёх отдельных MCP-подключений — одно. Шлюз принимает все запросы и маршрутизирует их к нужному бэкенду автоматически.

---

## Содержание

- [Что умеет](#что-умеет)
- [Требования](#требования)
- [Установка](#установка)
- [Подключение к Cursor](#подключение-к-cursor)
- [Подключение к Claude Code](#подключение-к-claude-code)
- [Подключение базы 1С](#подключение-базы-1с)
- [Примеры использования](#примеры-использования)
- [Работа с несколькими базами](#работа-с-несколькими-базами)
- [Опциональные модули](#опциональные-модули)
- [Настройка на Windows](#настройка-на-windows)
- [Диагностика](#диагностика)
- [Обновление](#обновление)
- [Архитектура](#архитектура)
- [Компоненты](#компоненты)
- [Используемые проекты](#используемые-проекты)
- [Планы развития](#планы-развития)
- [Удаление](#удаление)
- [Лицензия](#лицензия)

---

## Что умеет

**33 инструмента и 1 ресурс в четырёх категориях:**

| Категория | Инструментов | Что делает |
|---|---|---|
| Данные 1С (`onec-toolkit`) | 8 | Запросы к БД, выполнение кода, метаданные, журнал регистрации, права доступа |
| Документация платформы (`platform-context`) | 5 | Поиск по API 1С, методы типов, конструкторы |
| Навигация по BSL (`bsl-lsp-bridge`) | 14 | Поиск символов, hover-подсказки, диагностика, структура файла |
| Граф связей (`bsl-graph`, опционально) | 3 | Поиск объектов, анализ зависимостей, анализ влияния изменений |

Плюс 8 инструментов самого шлюза: подключение баз, переключение, статус, валидация запросов, граф связей.

**MCP Resource:** `syntax_1c.txt` — справочник синтаксиса встроенного языка 1С для контекста AI при написании BSL-кода.

---

## Требования

- Docker 24+
- Linux (Ubuntu 22.04 / 24.04) или Windows с WSL2
- Платформа 1С, установленная на хосте
- Доступ к базе 1С (серверная или файловая)

---

## Установка

### 1. Клонировать репозиторий

```bash
git clone https://github.com/AlekseiSeleznev/onec-mcp-universal.git
cd onec-mcp-universal
```

### 2. Создать файл конфигурации

```bash
cp .env.example .env
```

Открыть `.env` и указать путь к платформе:

```env
# Путь к установленной платформе 1С (папка bin находится внутри)
PLATFORM_PATH=/opt/1cv8/x86_64/8.3.27.2074
```

### 3. Запустить сервис выгрузки BSL

Сервис запускается один раз на хосте и остаётся работать в фоне. Он нужен для выгрузки исходников конфигурации в файлы BSL.

Открыть **новый терминал** и выполнить:

```bash
python3 tools/export-host-service.py --port 8082 --workspace /home/username/projects
```

Где `/home/username/projects` — папка, куда будут сохраняться исходники баз 1С. Например: `/home/user/1c-projects`.

Терминал оставить открытым (или добавить сервис в автозапуск).

### 4. Запустить контейнеры

```bash
docker compose up -d
```

Первый запуск занимает 2–3 минуты: скачиваются образы и собирается шлюз.

### 5. Проверить работу

```bash
curl http://localhost:8080/health
```

Ожидаемый ответ (все три бэкенда должны показать `"ok": true`):

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

## Подключение к Cursor

1. Открыть **Settings** (Ctrl+,) → раздел **MCP**
2. Нажать **Add new MCP server**
3. Указать:
   - Name: `onec`
   - Type: `HTTP`
   - URL: `http://localhost:8080/mcp`
4. Нажать **Save**

После сохранения в списке MCP-инструментов появится 27+ инструментов с префиксом `onec-universal__`.

## Подключение к Claude Code

Выполнить в терминале:

```bash
claude mcp add onec --transport http http://localhost:8080/mcp
```

Или вручную добавить в `~/.claude.json`:

```json
{
  "mcpServers": {
    "onec": {
      "type": "http",
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

---

## Подключение базы 1С

Прежде чем задавать вопросы по данным конкретной базы, её нужно подключить. Это делается один раз (после каждого перезапуска шлюза).

### Шаг 1. Подключить базу

В чате с AI (Cursor или Claude Code) написать:

```
Подключи базу ERP, строка подключения Srvr=as-hp;Ref=erp_demo;, папка проекта /home/user/1c-projects/ERP
```

AI самостоятельно вызовет нужный инструмент. Или вызвать напрямую:

```
connect_database(
  name="ERP",
  connection="Srvr=as-hp;Ref=erp_demo;",
  project_path="/home/user/1c-projects/ERP"
)
```

**Параметры `connection`:**

| Тип базы | Пример |
|---|---|
| Серверная | `Srvr=имя_сервера;Ref=имя_базы;` |
| С авторизацией | `Srvr=имя_сервера;Ref=имя_базы;Usr=admin;Pwd=пароль;` |
| Файловая | `File=/путь/к/базе` |

Шлюз создаст два Docker-контейнера: `onec-toolkit-ERP` и `mcp-lsp-ERP`.

### Шаг 2. Открыть обработку MCPToolkit в 1С

1. Открыть файл `1c/MCPToolkit.epf` в клиенте 1С:Предприятие
2. Разрешить открытие при запросе безопасности
3. Обработка автоматически подключится к шлюзу

В строке состояния обработки появится: **«Подключено»**.

Обработку нужно держать открытой пока работаете с AI — она является посредником между шлюзом и базой 1С.

### Шаг 3. Выгрузить исходники BSL (для навигации по коду)

В обработке нажать кнопку **«Выгрузить BSL»**.

Или попросить AI:

```
Выгрузи исходники базы ERP
```

После выгрузки BSL Language Server проиндексирует файлы. На большой конфигурации (ERP 2.5, ZUP) индексация занимает **3–5 минут**. Проверить готовность:

```
lsp_status()
```

Когда в ответе появится `"state": "complete"` — всё готово.

---

## Примеры использования

### Запросить данные из базы

```
Выбери первые 10 контрагентов из справочника
```

```
Покажи документы Реализация за последний месяц с суммой больше 100000
```

### Изучить структуру объекта метаданных

```
Покажи структуру документа РеализацияТоваровУслуг: реквизиты и табличные части
```

### Выполнить произвольный код 1С

```
Выполни в базе код: Результат = Метаданные.Конфигурация.Версия
```

### Проверить права доступа

```
Какие роли имеют право изменять справочник Номенклатура?
```

```
get_access_rights(metadata_object="Документ.РеализацияТоваровУслуг")
```

### Открыть объект по ссылке

```
get_object_by_link(link="e1cib/data/Справочник.Контрагенты?ref=80260015e9b8c48d11e2c2d02ff9d345")
```

### Найти где используется объект

```
find_references_to_object(
  target_object_description={"_objectRef": true, "УникальныйИдентификатор": "...", "ТипОбъекта": "СправочникСсылка.Контрагенты"},
  search_scope=["documents"]
)
```

### Найти функцию в исходниках конфигурации

```
Найди все места где вызывается процедура ЗаполнитьТабличнуюЧасть
```

### Получить документацию платформы

```
Как работает метод НайтиСтроки у ТаблицаЗначений?
```

```
search(query="ТаблицаЗначений", type="type", limit=5)
```

### Проверить синтаксис запроса до выполнения

```
validate_query(query="ВЫБРАТЬ Ссылка, Наименование ИЗ Справочник.Контрагенты ГДЕ Ссылка В (&Список")
```

AI получит ошибку про несбалансированные скобки и исправит запрос до отправки в базу.

### Проверить журнал регистрации

```
Покажи последние 5 ошибок за сегодня
```

```
get_event_log(levels=["Error"], limit=5, start_date="2026-04-04T00:00:00")
```

---

## Работа с несколькими базами

К одному шлюзу можно подключить несколько баз одновременно и переключаться между ними.

```
# Подключить вторую базу
connect_database(name="ZUP", connection="Srvr=as-hp;Ref=zup;", project_path="/home/user/1c-projects/ZUP")

# Переключиться
switch_database(name="ZUP")

# Посмотреть список
list_databases()

# Отключить базу
disconnect_database(name="ZUP")
```

---

## Опциональные модули

### Тестирование YaXUnit (mcp-onec-test-runner)

Запуск тестов, сборка проекта и проверка синтаксиса из AI-ассистента. Использует [mcp-onec-test-runner](https://github.com/alkoleft/mcp-onec-test-runner).

**Настройка:**

1. Скопировать шаблон конфигурации:

```bash
cp test-runner/application.yml.example test-runner/application.yml
```

2. Открыть `test-runner/application.yml` и указать строку подключения к базе и путь к проекту.

3. Запустить:

```bash
docker compose --profile test-runner up -d
```

4. Добавить `test-runner` в `.env`:

```env
ENABLED_BACKENDS=onec-toolkit,platform-context,bsl-lsp-bridge,test-runner
```

5. Перезапустить шлюз: `docker compose restart gateway`

**Доступные инструменты:** `run_all_tests`, `run_module_tests`, `build_project`, `check_syntax_edt`, `check_syntax_designer_config`, `dump_config`, `launch_app`.

---

### Граф связей конфигурации (bsl-graph)

Анализ зависимостей между объектами: что использует объект и что сломается при его изменении. Использует [bsl-graph](https://github.com/alkoleft/bsl-graph) + NebulaGraph.

> **Требования к ресурсам:** NebulaGraph запускает 3 дополнительных контейнера и требует ~4 ГБ RAM.

**Запустить:**

```bash
docker compose --profile bsl-graph up -d
```

**Инструменты (доступны без дополнительной настройки шлюза):**

```
# Статистика графа
graph_stats()

# Поиск объекта по имени
graph_search(query="РеализацияТоваровУслуг")

# Зависимости объекта
graph_related(object_id="<id из graph_search>", depth=2)
```

Перед использованием необходимо проиндексировать BSL-исходники через REST API bsl-graph на порту 8888.

---

## Настройка на Windows

На Windows `ibcmd` работает только на хосте, не в контейнере.

1. Запустить сервис выгрузки в командной строке:

```cmd
python tools\export-host-service.py --port 8082 --workspace C:\1c-projects
```

2. В файле `.env` добавить:

```env
EXPORT_HOST_URL=http://host.docker.internal:8082
```

3. Удалить из `docker-compose.yml` строку монтирования `/opt/1cv8` в сервисе `platform-context`.

---

## Диагностика

### Проверить статус всех бэкендов

```
get_server_status()
```

### Посмотреть логи шлюза

```bash
docker logs onec-mcp-gw -f
```

### Логи toolkit для конкретной базы

```bash
docker logs onec-toolkit-ERP -f
```

### Перезапустить шлюз (без пересборки)

```bash
docker compose restart gateway
```

После перезапуска нужно заново вызвать `connect_database`. Обработка MCPToolkit переподключится автоматически при следующем открытии.

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
Cursor / Claude Code
       │ HTTP :8080/mcp
       ▼
┌─────────────────────────────────────┐
│  onec-mcp-gw  (Python, host network)│
│                                     │
│  Статические бэкенды:               │
│  → onec-mcp-toolkit  :6003          │  ← Streamable HTTP
│  → onec-mcp-platform :8081          │  ← SSE
│  → mcp-lsp-zup       (stdio)        │  ← docker exec
│                                     │
│  Динамические бэкенды (per-DB):     │
│  → onec-toolkit-ERP  :6100+         │  ← создаются при connect_database
│  → mcp-lsp-ERP       (stdio)        │
└─────────────────────────────────────┘
         ▲
         │ MCPToolkit.epf (клиент 1С)
         │ держит соединение с onec-toolkit
```

---

## Компоненты

| Контейнер | Образ | Роль |
|---|---|---|
| `onec-mcp-gw` | собирается локально | Шлюз, маршрутизация запросов |
| `onec-mcp-toolkit` | `roctup/1c-mcp-toolkit-proxy` | Статический бэкенд данных 1С |
| `onec-mcp-platform` | `ghcr.io/alkoleft/mcp-bsl-platform-context` | Документация платформы |
| `onec-toolkit-{name}` | `roctup/1c-mcp-toolkit-proxy` | Динамический бэкенд данных (per-DB) |
| `mcp-lsp-{name}` | `mcp-lsp-bridge-bsl:latest` | BSL Language Server (per-DB) |
| `onec-mcp-test-runner` | `ghcr.io/alkoleft/mcp-onec-test-runner` | Тестирование YaXUnit, сборка (опционально) |
| `onec-bsl-graph` | `ghcr.io/alkoleft/bsl-graph` | Граф связей объектов конфигурации (опционально) |
| `onec-nebula-*` | `vesoft/nebula-*:v3.8.0` | NebulaGraph — БД для графа (опционально, 3 контейнера) |

---

## Используемые проекты

Шлюз объединяет open-source проекты сообщества 1С:

**Основные (запускаются всегда):**

| Проект | Автор | Что делает |
|---|---|---|
| [1c-mcp-toolkit](https://github.com/ROCTUP/1c-mcp-toolkit) | ROCTUP | Запросы к БД, выполнение кода, метаданные, журнал регистрации |
| [mcp-bsl-platform-context](https://github.com/alkoleft/mcp-bsl-platform-context) | alkoleft | Документация платформы 1С, поиск по API |
| [mcp-bsl-lsp-bridge](https://github.com/alkoleft/mcp-bsl-lsp-bridge) | alkoleft | MCP-мост к BSL Language Server |
| [lsp-session-manager](https://github.com/alkoleft/lsp-session-manager) | alkoleft | Мультиплексор сессий BSL Language Server |
| [1c_mcp](https://github.com/vladimir-kharin/1c_mcp) | vladimir-kharin | Справочник синтаксиса BSL (`syntax_1c.txt`) как MCP Resource |

**Опциональные (профили docker compose):**

| Проект | Автор | Профиль | Что делает |
|---|---|---|---|
| [mcp-onec-test-runner](https://github.com/alkoleft/mcp-onec-test-runner) | alkoleft | `test-runner` | Запуск тестов YaXUnit, сборка конфигурации, проверка синтаксиса |
| [bsl-graph](https://github.com/alkoleft/bsl-graph) | alkoleft | `bsl-graph` | Граф зависимостей объектов конфигурации |

---

## Планы развития

Идеи для следующих версий, собранные из анализа экосистемы MCP-серверов для 1С.

### Запуск тестов YaXUnit из AI

Интеграция [mcp-onec-test-runner](https://github.com/alkoleft/mcp-onec-test-runner) в шлюз даст AI петлю обратной связи: написал код → запустил тесты → получил ошибки → исправил. Инструменты: `run_tests`, `build_project`, `check_syntax`.

### Анонимизация данных для работы с production-базами

Маскировка персональных данных в ответах: ФИО → TOKEN_001, ИНН → TOKEN_002 со стабильным маппингом (AI может работать со ссылками, не видя реальных значений). Снимает барьер 152-ФЗ/GDPR при подключении production-баз к облачным AI-ассистентам. Подход описан в [1c-mcp-toolkit](https://github.com/ROCTUP/1c-mcp-toolkit).

### Графовый анализ связей конфигурации

Инструменты типа `get_dependency_graph`, `get_impact_analysis` — «что сломается если удалить объект X». [alkoleft/bsl-graph](https://github.com/alkoleft/bsl-graph) строит граф через NebulaGraph. В шлюзе можно сделать легковесный вариант на основе данных BSL-индексации.

### Валидация запросов 1С до выполнения

Отдельный инструмент `validate_query` для проверки синтаксиса запроса до отправки в базу. AI сможет итеративно исправлять запрос не тратя ресурсы на выполнение. Идея из [artesk/1C_MCP_metadata](https://github.com/artesk/1C_MCP_metadata).

### RAG-поиск по БСП и коду конфигурации

Семантический поиск по исходникам конфигурации и Библиотеке стандартных подсистем — найти «функцию для работы с датами» без точного знания имени. [vibecoding1c.ru](https://vibecoding1c.ru/mcp_server) реализует это через отдельные серверы SSLSearchServer и HelpSearchServer. В шлюзе — как дополнительный бэкенд с pgvector/ChromaDB поверх выгруженных BSL-файлов.

### Write-операции метаданных

Сейчас шлюз только читает конфигурацию. [DitriXNew/EDT-MCP](https://github.com/DitriXNew/EDT-MCP) (131 звезда) реализует 26 инструментов для EDT включая переименование объектов с каскадным рефакторингом, добавление реквизитов, получение снимка формы. Требует интеграции с EDT.

### Поиск по ИТС через 1С:Напарник

1С:Напарник предоставляет API для поиска по документации ИТС и типовым конфигурациям. Инструмент `search_its(query)` позволит AI находить официальные рекомендации по методологии и архитектурным вопросам прямо в контексте задачи. [Описание подхода на infostart.ru](https://infostart.ru/1c/articles/2624226/).

---

## Удаление

```bash
# Остановить и удалить контейнеры
docker compose down

# Удалить образ шлюза
docker rmi onec-mcp-universal-gateway

# Удалить папку с проектом
cd ..
rm -rf onec-mcp-universal
```

Данные баз 1С и исходники BSL не затрагиваются — удаляются только контейнеры и образ шлюза.

---

## Лицензия

[MIT](LICENSE)
