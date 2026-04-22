from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _forbidden_name() -> str:
    return "cl" "aude"


def _forbidden_skill_dir_posix() -> str:
    return "." + _forbidden_name() + "/skills"


def _forbidden_skill_dir_windows() -> str:
    return "." + _forbidden_name() + "\\skills"


def _legacy_doc_name() -> str:
    return "CL" "AUDE.md"


def test_setup_is_codex_first_and_ai_agnostic():
    root = _repo_root()
    text = (root / "setup.sh").read_text(encoding="utf-8")

    assert "codex mcp add" in text
    assert "Codex CLI" in text
    assert "BSL_WORKSPACE" in text
    assert "BSL_HOST_WORKSPACE" in text
    assert "ensure_secret_env DOCKER_CONTROL_TOKEN" in text
    assert "ensure_secret_env ANONYMIZER_SALT" in text
    assert "generate_secret()" in text
    assert (_forbidden_name() + " mcp add") not in text.lower()


def test_env_example_keeps_workspace_as_documented_example_not_active_default():
    root = _repo_root()
    text = (root / ".env.example").read_text(encoding="utf-8")

    assert "BSL_WORKSPACE=/home/user/1c-bsl-projects" not in text
    assert "# BSL_WORKSPACE=/abs/path/to/bsl-projects" in text
    assert "setup.sh fills this automatically" in text
    assert "# DOCKER_CONTROL_TOKEN=change-me" in text
    assert "# ANONYMIZER_SALT=change-me" in text
    assert "dashboard masks it" in text


def test_install_skills_target_codex_directory():
    root = _repo_root()
    sh = (root / "install-skills.sh").read_text(encoding="utf-8")
    ps1 = (root / "install-skills.ps1").read_text(encoding="utf-8")

    assert ".codex/skills" in sh
    assert ".codex" in ps1
    assert _forbidden_skill_dir_posix() not in sh
    assert _forbidden_skill_dir_windows() not in ps1
    assert _forbidden_name() not in sh.lower()
    assert _forbidden_name() not in ps1.lower()


def test_export_service_installers_do_not_bake_workspace_path():
    root = _repo_root()
    linux = (root / "tools/install-export-service-linux.sh").read_text(encoding="utf-8")
    windows = (root / "tools/install-export-service-windows.ps1").read_text(encoding="utf-8")
    stop_stale = (root / "tools/stop-export-host-service-linux.sh").read_text(encoding="utf-8")

    assert "--workspace" not in linux
    assert "--workspace" not in windows
    assert "dynamic (.env / request-driven)" in linux
    assert "dynamic (.env / request-driven)" in windows
    assert "STOP_STALE_SH" in linux
    assert "ExecStartPre=/usr/bin/bash ${STOP_STALE_SH}" in linux
    assert "pgrep -f 'python3 .*export-host-service.py --port 8082'" in stop_stale


def test_skill_docs_are_repo_relative():
    root = _repo_root()
    offenders = []
    for skill_md in (root / "skills").rglob("*.md"):
        text = skill_md.read_text(encoding="utf-8")
        if (_forbidden_skill_dir_posix() + "/") in text:
            offenders.append(str(skill_md.relative_to(root)))

    assert offenders == []


def test_readme_documents_codex_and_package_policy():
    root = _repo_root()
    text = (root / "README.md").read_text(encoding="utf-8")

    assert "codex mcp add onec-universal --url http://localhost:8080/mcp" in text
    assert "ghcr.io/alekseiseleznev/onec-mcp-universal:latest" in text
    assert "onec-mcp-universal-docker-control" in text
    assert "Скилы 1С для Codex" in text


def test_dashboard_save_env_uses_explicit_replace_mode():
    root = _repo_root()
    text = (root / "gateway" / "gateway" / "web_ui.py").read_text(encoding="utf-8")

    assert "JSON.stringify({content:c,mode:'replace'})" in text


def test_mcptoolkit_connect_resets_existing_poll_before_gateway_reregistration():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    connect_start = text.index("Процедура Подключиться(Команда)")
    connect_end = text.index("КонецПроцедуры", connect_start)
    connect_body = text[connect_start:connect_end]

    disconnect_pos = connect_body.index("СброситьСостояниеПодключенияПередПереподключением();")
    register_log_pos = connect_body.index('ДобавитьВЛог("Регистрация базы в шлюзе...");')

    assert disconnect_pos < register_log_pos


def test_mcptoolkit_connect_generates_new_channel_before_gateway_registration():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    connect_start = text.index("Процедура Подключиться(Команда)")
    connect_end = text.index("КонецПроцедуры", connect_start)
    connect_body = text[connect_start:connect_end]

    channel_pos = connect_body.index("СгенерироватьИдентификаторКанала(Неопределено);")
    register_pos = connect_body.index("ЗарегистрироватьсяВШлюзе(Неопределено);")

    assert channel_pos < register_pos


def test_mcptoolkit_register_payload_includes_channel():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index("Процедура ЗарегистрироватьсяВШлюзе(Команда)")
    end = text.index("КонецПроцедуры", start)
    body = text[start:end]

    assert '"", ""channel"": """ + СокрЛП(ИдентификаторКанала) + """}' in body


def test_mcptoolkit_register_uses_extended_first_connect_timeout():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index("Процедура ЗарегистрироватьсяВШлюзе(Команда)")
    end = text.index("КонецПроцедуры", start)
    body = text[start:end]

    assert "HTTPСоединение(СтруктураURL.Хост, СтруктураURL.Порт, , , , 240" in body


def test_mcptoolkit_form_exposes_global_dangerous_auto_approval_toggle():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form.xml"
    ).read_text(encoding="utf-8")

    assert "АвтоРазрешитьВсеОпасныеОперации" in text
    assert "Все опасные операции без предупреждения" in text
    assert "ФлагАвтоВсеОпасныеОперацииПриИзменении" in text


def test_mcptoolkit_module_confirms_global_dangerous_auto_approval_toggle():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    assert "Процедура ФлагАвтоВсеОпасныеОперацииПриИзменении(Элемент)" in text
    assert "Все действия, включая опасные операции, будут выполняться автоматически без предупреждения." in text
    assert "Удаление объектов" in text
    assert "Операции с файлами и каталогами" in text
    assert "Внешние компоненты и COM-объекты" in text
    assert "Монопольный и привилегированный режимы" in text


def test_mcptoolkit_global_dangerous_auto_approval_bypasses_keyword_specific_flags():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index("Функция ВсеОперацииАвтоРазрешены(МассивОпасныхСлов)")
    end = text.index("КонецФункции", start)
    body = text[start:end]

    assert "Если АвтоРазрешитьВсеОпасныеОперации Тогда" in body
    assert "Возврат Истина;" in body


def test_mcptoolkit_does_not_refresh_auto_approval_settings_before_proxy_dangerous_check():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index('Если ПараметрыКоманды.Свойство("requires_approval") И ПараметрыКоманды.requires_approval = Истина Тогда')
    end = text.index("// Получение кода", start)
    body = text[start:end]

    assert "ОбновитьНастройкиАвтоРазрешенияИзХранилища();" not in body


def test_mcptoolkit_does_not_refresh_auto_approval_settings_before_embedded_mcp_dangerous_check():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index('Если ИмяИнструмента = "execute_code" Тогда')
    end = text.index("// Выполнение", start)
    body = text[start:end]

    assert "ОбновитьНастройкиАвтоРазрешенияИзХранилища();" not in body


def test_mcptoolkit_embedded_execute_code_client_context_bypasses_dangerous_gate():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    handler_start = text.index("Функция ОбработатьToolsCall(")
    start = text.index('Если ИмяИнструмента = "execute_code" Тогда', handler_start)
    end = text.index("// Выполнение", start)
    body = text[start:end]

    assert 'Если КонтекстВыполнения <> "client" Тогда' in body
    assert "МассивОпасныхСлов = ПроверитьОпасныеСлова(Код);" in body
    assert body.index('Если КонтекстВыполнения <> "client" Тогда') < body.index(
        "МассивОпасныхСлов = ПроверитьОпасныеСлова(Код);"
    )


def test_mcptoolkit_auto_approval_flags_start_false_without_storage_restore():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index("Процедура ЗагрузитьНастройки()")
    end = text.index("КонецПроцедуры", start)
    body = text[start:end]

    assert "АвтоРазрешитьЗаписать = Ложь;" in body
    assert "АвтоРазрешитьПривилегированныйРежим = Ложь;" in body
    assert "АвтоРазрешитьВсеОпасныеОперации = Ложь;" in body
    assert 'ХранилищеОбщихНастроек.Загрузить("MCPToolkit", "АвтоРазрешенияОпасныхОпераций")' not in body


def test_mcptoolkit_server_execute_code_guides_to_client_context_for_form_flags():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index("Функция ВыполнитьКод(Код)")
    end = text.index("КонецФункции", start)
    body = text[start:end]

    assert "ЭтоОшибкаДоступаКФлагамАвтоРазрешения(Код, ТекстОшибки)" in body
    assert "execution_context=\"\"client\"\"" in body


def test_mcptoolkit_heartbeat_reregisters_after_gateway_404():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index("Процедура ОтправитьHeartbeatEPF(Принудительно = Ложь)")
    end = text.index("КонецПроцедуры", start)
    body = text[start:end]

    assert "ИначеЕсли Ответ.КодСостояния = 404 Тогда" in body
    assert 'ДобавитьВЛог("Gateway потерял регистрацию базы. Выполняется повторная регистрация...");' in body
    assert "ЗарегистрироватьсяВШлюзе(Неопределено);" in body


def test_mcptoolkit_heartbeat_payload_includes_channel():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index("Процедура ОтправитьHeartbeatEPF(Принудительно = Ложь)")
    end = text.index("КонецПроцедуры", start)
    body = text[start:end]

    assert '""name"": """ + СокрЛП(ИмяБазы) + """' in body
    assert '""channel"": """ + СокрЛП(ИдентификаторКанала) + """' in body


def test_mcptoolkit_error_handler_recovers_instead_of_forcing_disconnect():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index("Процедура ОбработатьОшибкуПодключения(ОписаниеОшибки)")
    end = text.index("КонецПроцедуры", start)
    body = text[start:end]

    assert 'ДобавитьВЛог("Ошибка подключения: " + ОписаниеОшибки + ". Превышено количество попыток. Выполняется восстановление подключения...");' in body
    assert "ВосстановитьПодключениеПослеОшибки();" in body
    assert "ОтключитьсяОтСервера();" not in body
    assert "УведомитьШлюзОбОтключенииEPF();" not in body


def test_mcptoolkit_recovery_reregisters_without_dropping_current_channel():
    root = _repo_root()
    text = (
        root
        / "1c"
        / "MCPToolkit"
        / "MCPToolkit"
        / "Forms"
        / "Форма"
        / "Ext"
        / "Form"
        / "Module.bsl"
    ).read_text(encoding="utf-8")

    start = text.index("Процедура ВосстановитьПодключениеПослеОшибки()")
    end = text.index("КонецПроцедуры", start)
    body = text[start:end]

    assert "Если НЕ ФлагПодключения Тогда" in body
    assert "ПоследнийHeartbeatEPF = 0;" in body
    assert "ТекущееКоличествоПопытокПереподключения = 0;" in body
    assert "ЗарегистрироватьсяВШлюзе(Неопределено);" in body
    assert "СгенерироватьИдентификаторКанала(Неопределено);" not in body
    assert "ОтключитьсяОтСервера();" not in body


def test_docker_publish_tracks_main_and_release_tags():
    root = _repo_root()
    text = (root / ".github/workflows/docker-publish.yml").read_text(encoding="utf-8")

    assert 'branches: ["main"]' in text
    assert 'tags: ["v*"]' in text
    assert "actions/checkout@v5" in text
    assert "docker buildx build" in text
    assert 'docker login "${REGISTRY}" -u "${GITHUB_ACTOR}" --password-stdin' in text
    assert 'if [[ "${GITHUB_REF_TYPE}" == "branch" && "${GITHUB_REF_NAME}" == "main" ]]' in text
    assert 'if [[ "${GITHUB_REF_TYPE}" == "tag" && "${GITHUB_REF_NAME}" =~ ^v([0-9]+)\\.([0-9]+)\\.([0-9]+)$ ]]' in text
    assert "onec-mcp-universal-bsl-graph-lite" in text
    assert "onec-mcp-universal-docker-control" in text
    assert "context: ./bsl-graph-lite" in text
    assert "context: ./docker-control" in text
    assert "tags<<EOF" not in text
    assert "mapfile -t tags" not in text
    assert "docker/login-action" not in text
    assert "docker/metadata-action" not in text
    assert "docker/build-push-action" not in text


def test_ci_enforces_full_coverage():
    root = _repo_root()
    text = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "actions/checkout@v5" in text
    assert "--cov=gateway" in text
    assert "--cov-branch" in text
    assert "--cov-fail-under=94" in text
    assert "cache: pip" in text


def test_bsl_graph_dockerfile_has_healthcheck():
    root = _repo_root()
    text = (root / "bsl-graph-lite/Dockerfile").read_text(encoding="utf-8")

    assert "HEALTHCHECK" in text
    assert "http://localhost:8888/health" in text


def test_bsl_graph_viewer_uses_per_database_edge_stats():
    root = _repo_root()
    text = (root / "bsl-graph-lite/static/app.js").read_text(encoding="utf-8")

    assert "edgesByDb" in text
    assert "edges = '—';" not in text


def test_bsl_graph_viewer_exposes_analysis_modes_and_path_api():
    root = _repo_root()
    html = (root / "bsl-graph-lite/static/index.html").read_text(encoding="utf-8")
    js = (root / "bsl-graph-lite/static/app.js").read_text(encoding="utf-8")

    assert 'id="mode-select"' in html
    assert 'value="overview"' in html
    assert 'value="path"' in html
    assert 'id="path-panel"' in html
    assert 'id="analysis-panel"' in html
    assert 'id="lang-sw"' in html
    assert 'id="dialog-modal"' in html
    assert 'id="path-depth-dec"' in html
    assert 'id="path-depth-inc"' in html
    assert html.index('id="lang-sw"') < html.index('id="btn-rebuild"') < html.index('id="current-db"') < html.index('id="stats"')
    assert "/api/graph/path" in js
    assert "selectedSourceId" in js
    assert "selectedTargetId" in js
    assert "hide-bsl-files" in html
    assert "showDialog(" in js
    assert 'getElementById(\'current-db\')' in js


def test_bsl_graph_viewer_supports_bootstrap_query_params():
    root = _repo_root()
    text = (root / "bsl-graph-lite/static/app.js").read_text(encoding="utf-8")

    assert "queryParams().get('db')" in text
    assert "queryParams().get('q')" in text
    assert "queryParams().get('nodeId')" in text
    assert "queryParams().get('mode')" in text
    assert "bootstrapFromUrl" in text


def test_bsl_graph_viewer_localizes_graph_type_labels_for_ru_and_en():
    root = _repo_root()
    text = (root / "bsl-graph-lite/static/app.js").read_text(encoding="utf-8")

    assert "Регистр сведений" in text
    assert "Справочник" in text
    assert "Документ" in text
    assert "Contains BSL file" in text
    assert "Accumulation register" in text


def test_dashboard_links_database_rows_to_graph_viewer():
    root = _repo_root()
    text = (root / "gateway/gateway/web_ui.py").read_text(encoding="utf-8")

    assert '"open_graph": "Открыть граф"' in text
    assert '"open_graph": "Open Graph"' in text
    assert 'http://localhost:8888/?lang={lang}&db=' in text
    assert text.count('http://localhost:8888/?lang={lang}&db=') == 1


def test_compose_does_not_ship_legacy_bsl_graph_stack():
    root = _repo_root()
    text = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "bsl-graph-legacy" not in text
    assert "nebula-metad" not in text
    assert "nebula-storaged" not in text
    assert "nebula-graphd" not in text


def test_gateway_compose_uses_docker_control_and_passes_naparnik_key_to_gateway():
    root = _repo_root()
    text = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "docker-control:" in text
    assert "container_name: onec-mcp-docker-control" in text
    assert "DOCKER_CONTROL_URL: ${DOCKER_CONTROL_URL:-http://localhost:8091}" in text
    assert "NAPARNIK_API_KEY: ${NAPARNIK_API_KEY:-}" in text

    gateway_block = text.split("  gateway:\n", 1)[1].split("\n  docker-control:\n", 1)[0]
    docker_control_block = text.split("  docker-control:\n", 1)[1].split("\n\n  # ─── 1C Data Backend", 1)[0]
    assert "/var/run/docker.sock" not in gateway_block
    assert "./.env:/data/.env:ro" in gateway_block
    assert "DOCKER_CONTROL_TOKEN: ${DOCKER_CONTROL_TOKEN:-}" in gateway_block
    assert "ANONYMIZER_SALT: ${ANONYMIZER_SALT:-}" in gateway_block
    assert "NAPARNIK_API_KEY: ${NAPARNIK_API_KEY:-}" in gateway_block
    assert "TOOLKIT_ALLOW_DANGEROUS_WITH_APPROVAL: ${TOOLKIT_ALLOW_DANGEROUS_WITH_APPROVAL:-true}" in gateway_block
    assert "GATEWAY_RATE_LIMIT_ENABLED: ${GATEWAY_RATE_LIMIT_ENABLED:-true}" in gateway_block
    assert "GATEWAY_RATE_LIMIT_READ_RPM: ${GATEWAY_RATE_LIMIT_READ_RPM:-120}" in gateway_block
    assert "GATEWAY_RATE_LIMIT_MUTATING_RPM: ${GATEWAY_RATE_LIMIT_MUTATING_RPM:-30}" in gateway_block
    assert '      - "127.0.0.1:8091:8091"' in docker_control_block
    assert "DOCKER_CONTROL_TOKEN: ${DOCKER_CONTROL_TOKEN:-}" in docker_control_block
    assert "ANONYMIZER_SALT: ${ANONYMIZER_SALT:-}" in docker_control_block


def test_windows_override_keeps_docker_control_internal_only():
    root = _repo_root()
    text = (root / "docker-compose.windows.yml").read_text(encoding="utf-8")

    assert "DOCKER_CONTROL_URL: ${DOCKER_CONTROL_URL:-http://docker-control:8091}" in text
    assert "  docker-control:\n" in text
    assert "ports: !reset []" in text


def test_verify_scripts_check_docker_control_health_and_auth():
    root = _repo_root()
    sh = (root / "verify-install.sh").read_text(encoding="utf-8")
    ps1 = (root / "verify-install.ps1").read_text(encoding="utf-8")

    assert 'LOCAL_HEALTH_HOST="127.0.0.1"' in sh
    assert "http://${LOCAL_HEALTH_HOST}:8091/health" in sh
    assert "docker-control is reachable" in sh
    assert "DOCKER_CONTROL_TOKEN is configured" in sh
    assert "ANONYMIZER_SALT is configured" in sh
    assert 'http_status "http://${LOCAL_HEALTH_HOST}:8091/api/docker/system"' in sh
    assert "expected 401 without token" in sh
    assert "docker exec onec-mcp-gw" in sh
    assert '$LocalHealthHost = "127.0.0.1"' in ps1
    assert "http://$LocalHealthHost:8091/health" in ps1
    assert "docker-control is reachable" in ps1
    assert "DOCKER_CONTROL_TOKEN is configured" in ps1
    assert "ANONYMIZER_SALT is configured" in ps1
    assert 'Get-HttpStatus -Url "http://$LocalHealthHost:8091/api/docker/system"' in ps1
    assert "expected 401 without token" in ps1
    assert "docker exec onec-mcp-gw" in ps1


def test_setup_health_checks_use_ipv4_loopback_to_avoid_ipv6_localhost_hangs():
    root = _repo_root()
    text = (root / "setup.sh").read_text(encoding="utf-8")

    assert 'LOCAL_HEALTH_HOST="127.0.0.1"' in text
    assert "http://${LOCAL_HEALTH_HOST}:${PORT}/health" in text
    assert "http://${LOCAL_HEALTH_HOST}:8091/health" in text
    assert "http://${LOCAL_HEALTH_HOST}:8082/health" in text
    assert "http://${LOCAL_HEALTH_HOST}:8888/health" in text
    assert "--max-time 5" in text


def test_repo_contains_codex_and_agents_guides():
    root = _repo_root()
    codex_text = (root / "CODEX.md").read_text(encoding="utf-8")
    agents_text = (root / "AGENTS.md").read_text(encoding="utf-8")

    assert "Codex" in codex_text
    assert "./setup.sh" in codex_text
    assert "http://localhost:8080/mcp" in codex_text
    assert "DOCKER_CONTROL_TOKEN" in codex_text
    assert "ANONYMIZER_SALT" in codex_text
    assert "AI-agnostic" in agents_text or "нейтраль" in agents_text.lower()
    assert "http://localhost:8080/mcp" in agents_text


def test_gateway_runtime_assets_drop_privileges_for_main_process():
    root = _repo_root()
    dockerfile = (root / "gateway/Dockerfile").read_text(encoding="utf-8")
    entrypoint = (root / "gateway/entrypoint.sh").read_text(encoding="utf-8")

    assert "useradd" in dockerfile
    assert "10001" in dockerfile
    assert " app" in dockerfile
    assert "gosu app python -m gateway" in entrypoint


def test_readme_top_level_description_is_client_neutral():
    root = _repo_root()
    text = (root / "README.md").read_text(encoding="utf-8")

    assert "особенно Codex" not in text.splitlines()[2]
    assert "любых MCP-клиентов" in text


def test_repo_tracked_text_assets_do_not_reference_legacy_client_name():
    root = _repo_root()
    suffixes = {".md", ".py", ".sh", ".ps1", ".yml", ".yaml", ".txt"}
    allow_rel = {
        _legacy_doc_name(),
        "gateway/tests/test_codex_install_assets.py",
    }
    offenders = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if (
            ".git" in path.parts
            or ".venv" in path.parts
            or "__pycache__" in path.parts
            or ".graphify-gateway-docs-corpus" in path.parts
        ):
            continue
        if path.suffix.lower() not in suffixes:
            continue
        rel = str(path.relative_to(root))
        if rel in allow_rel:
            continue
        text = path.read_text(encoding="utf-8")
        if _forbidden_name() in text.lower():
            offenders.append(rel)

    assert offenders == []


def test_codex_doc_uses_https_clone_and_safe_skill_removal():
    root = _repo_root()
    text = (root / "CODEX.md").read_text(encoding="utf-8")

    assert "git clone https://github.com/AlekseiSeleznev/onec-mcp-universal.git" in text
    assert "git@github.com:AlekseiSeleznev/onec-mcp-universal.git" not in text
    assert "rm -rf ~/.codex/skills/*" not in text
    assert "find ~/.codex/skills -maxdepth 1 -type l -print0" in text
    assert 'rm "$link"' in text
