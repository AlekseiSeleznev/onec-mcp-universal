from pathlib import Path
import json
import os
import subprocess


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_workflow_skill_files_exist():
    root = _repo_root()
    expected = [
        "skills/1c-help-mcp/SKILL.md",
        "skills/brainstorm/SKILL.md",
        "skills/openspec-apply/SKILL.md",
        "skills/openspec-archive/SKILL.md",
        "skills/openspec-proposal/SKILL.md",
        "skills/bsp-patterns/SKILL.md",
        "skills/img-grid/SKILL.md",
        "skills/epf-expert/SKILL.md",
        "skills/erf-expert/SKILL.md",
        "skills/mxl-expert/SKILL.md",
        "skills/inspect/SKILL.md",
        "skills/validate/SKILL.md",
        "skills/session-save/SKILL.md",
        "skills/session-restore/SKILL.md",
        "skills/session-retro/SKILL.md",
        "skills/write-plan/SKILL.md",
        "skills/1c-project-init/SKILL.md",
        "skills/1c-query-opt/SKILL.md",
        "skills/1c-feature-dev/SKILL.md",
        "skills/role-expert/SKILL.md",
        "skills/subsystem-expert/SKILL.md",
        "skills/subagent-dev/SKILL.md",
        "skills/1c-test-runner/SKILL.md",
        "skills/1c-web-session/SKILL.md",
        "skills/playwright-test/SKILL.md",
        "templates/mcp.json",
    ]
    for rel in expected:
        assert (root / rel).is_file(), f"Missing workflow skill file: {rel}"


def test_session_skills_define_expected_headings():
    root = _repo_root()
    save_text = (root / "skills/session-save/SKILL.md").read_text(encoding="utf-8")
    restore_text = (root / "skills/session-restore/SKILL.md").read_text(encoding="utf-8")
    retro_text = (root / "skills/session-retro/SKILL.md").read_text(encoding="utf-8")

    assert "session-notes.md" in save_text
    assert "## Next Action" in save_text
    assert "session-notes.md" in restore_text
    assert "## Retrospective" in retro_text


def test_context_monitor_scripts_exist_and_have_thresholds():
    root = _repo_root()
    ps1 = root / "tools/context-monitor.ps1"
    sh = root / "tools/context-monitor.sh"

    assert ps1.is_file()
    assert sh.is_file()

    ps1_text = ps1.read_text(encoding="utf-8")
    sh_text = sh.read_text(encoding="utf-8")

    assert "WarnPercent" in ps1_text
    assert "CriticalPercent" in ps1_text
    assert "WARN_PERCENT" in sh_text
    assert "CRITICAL_PERCENT" in sh_text


def test_project_mcp_template_has_onec_universal_server():
    root = _repo_root()
    template = root / "templates/mcp.json"
    data = json.loads(template.read_text(encoding="utf-8"))

    assert "mcpServers" in data
    assert "onec-universal" in data["mcpServers"]
    assert data["mcpServers"]["onec-universal"]["url"] == "http://localhost:8080/mcp"


def test_workflow_docs_exist():
    root = _repo_root()
    assert (root / "docs/workflow-layer-design.md").is_file()
    assert (root / "docs/session-management.md").is_file()
    assert (root / "docs/project-bootstrap.md").is_file()
    assert (root / "docs/feature-lifecycle-example.md").is_file()


def test_workflow_skill_count_floor():
    root = _repo_root()
    skill_dirs = [p for p in (root / "skills").iterdir() if p.is_dir()]
    assert len(skill_dirs) >= 96


def test_query_opt_skill_contract_markers():
    root = _repo_root()
    text = (root / "skills/1c-query-opt/SKILL.md").read_text(encoding="utf-8")
    assert "validate_query" in text
    assert "execute_query" in text
    assert "query_stats" in text


def test_feature_dev_skill_contract_markers():
    root = _repo_root()
    text = (root / "skills/1c-feature-dev/SKILL.md").read_text(encoding="utf-8")
    assert "9 фаз" in text
    assert "design.md" in text
    assert "tasks.md" in text
    assert "validate_query" in text


def test_context_monitor_shell_script_is_executable():
    root = _repo_root()
    sh = root / "tools/context-monitor.sh"
    assert os.access(sh, os.X_OK), "tools/context-monitor.sh must be executable"


def test_context_monitor_shell_script_handles_invalid_token_counter():
    root = _repo_root()
    sh = root / "tools/context-monitor.sh"
    env = os.environ.copy()
    env["ONEC_CONTEXT_TOKENS"] = "not-a-number"
    proc = subprocess.run(
        ["/bin/bash", str(sh)],
        input="abc",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout == "abc"
    assert "Context" not in proc.stderr


def test_brainstorm_and_plan_skill_contract_markers():
    root = _repo_root()
    brainstorm_text = (root / "skills/brainstorm/SKILL.md").read_text(encoding="utf-8")
    write_plan_text = (root / "skills/write-plan/SKILL.md").read_text(encoding="utf-8")

    assert "Что сделано" in brainstorm_text or "Процесс" in brainstorm_text
    assert "tasks.md" in write_plan_text


def test_openspec_skill_contract_markers():
    root = _repo_root()
    for rel in [
        "skills/openspec-proposal/SKILL.md",
        "skills/openspec-apply/SKILL.md",
        "skills/openspec-archive/SKILL.md",
    ]:
        text = (root / rel).read_text(encoding="utf-8")
        assert "openspec/changes" in text
        assert "tasks.md" in text or "proposal.md" in text


def test_feature_lifecycle_example_contains_full_chain():
    root = _repo_root()
    text = (root / "docs/feature-lifecycle-example.md").read_text(encoding="utf-8")
    assert "brainstorm" in text
    assert "openspec-proposal" in text
    assert "write-plan" in text
    assert "openspec-apply" in text
    assert "openspec-archive" in text


def test_feature_lifecycle_example_full_chain_is_ordered_and_has_artifacts():
    root = _repo_root()
    text = (root / "docs/feature-lifecycle-example.md").read_text(encoding="utf-8")

    steps = [
        "/brainstorm",
        "/openspec-proposal",
        "/write-plan",
        "/openspec-apply",
        "/openspec-archive",
    ]
    prev = -1
    for step in steps:
        idx = text.find(step)
        assert idx != -1, f"Missing workflow command marker: {step}"
        assert idx > prev, f"Workflow command order is broken at: {step}"
        prev = idx

    assert "openspec/changes/<feature-id>/" in text
    assert "proposal.md" in text
    assert "design.md" in text
    assert "tasks.md" in text


def test_compatibility_alias_skills_exist():
    root = _repo_root()
    for rel in [
        "skills/1c-help-mcp/SKILL.md",
        "skills/bsp-patterns/SKILL.md",
        "skills/img-grid/SKILL.md",
        "skills/role-expert/SKILL.md",
        "skills/subsystem-expert/SKILL.md",
        "skills/subagent-dev/SKILL.md",
        "skills/1c-test-runner/SKILL.md",
        "skills/1c-web-session/SKILL.md",
        "skills/playwright-test/SKILL.md",
    ]:
        assert (root / rel).is_file(), f"Missing compatibility skill file: {rel}"


def test_compatibility_alias_skill_contract_markers():
    root = _repo_root()
    help_text = (root / "skills/1c-help-mcp/SKILL.md").read_text(encoding="utf-8")
    bsp_text = (root / "skills/bsp-patterns/SKILL.md").read_text(encoding="utf-8")
    role_text = (root / "skills/role-expert/SKILL.md").read_text(encoding="utf-8")
    subsystem_text = (root / "skills/subsystem-expert/SKILL.md").read_text(encoding="utf-8")
    subagent_text = (root / "skills/subagent-dev/SKILL.md").read_text(encoding="utf-8")
    test_runner_text = (root / "skills/1c-test-runner/SKILL.md").read_text(encoding="utf-8")
    web_session_text = (root / "skills/1c-web-session/SKILL.md").read_text(encoding="utf-8")
    playwright_text = (root / "skills/playwright-test/SKILL.md").read_text(encoding="utf-8")

    assert "get_bsl_syntax_help" in help_text
    assert "search" in help_text
    assert "use-bsp" in bsp_text
    assert "role-compile" in role_text
    assert "meta-edit" in role_text
    assert "role-validate" in role_text
    assert "subsystem-compile" in subsystem_text
    assert "interface-edit" in subsystem_text
    assert "subsystem-validate" in subsystem_text
    assert "tasks.md" in subagent_text
    assert "openspec" in subagent_text
    assert "YaXUnit" in test_runner_text
    assert "test-runner" in test_runner_text
    assert "web-test" in web_session_text
    assert "action" in web_session_text.lower()
    assert "playwright" in playwright_text.lower()
    img_grid_text = (root / "skills/img-grid/SKILL.md").read_text(encoding="utf-8")
    assert "Pillow" in img_grid_text
    assert "mxl" in img_grid_text.lower()


def test_readme_documents_workflow_and_compatibility_examples():
    root = _repo_root()
    text = (root / "README.md").read_text(encoding="utf-8")
    required_examples = [
        "/1c-project-init",
        "/session-save",
        "/session-restore",
        "/session-retro",
        "/epf-expert",
        "/erf-expert",
        "/mxl-expert",
        "/inspect",
        "/validate",
        "/brainstorm",
        "/write-plan",
        "/openspec-proposal",
        "/openspec-apply",
        "/openspec-archive",
        "/1c-query-opt",
        "/1c-feature-dev",
        "/1c-help-mcp",
        "/bsp-patterns",
        "/role-expert",
        "/subsystem-expert",
        "/subagent-dev",
        "/1c-test-runner",
        "/1c-web-session",
        "/playwright-test",
    ]
    for cmd in required_examples:
        assert cmd in text, f"README examples missing command: {cmd}"


def test_readme_mcp_tool_count_is_marked_as_dynamic():
    root = _repo_root()
    text = (root / "README.md").read_text(encoding="utf-8")
    assert "48+ MCP-инструментов + 1 ресурс" in text
    assert "0-1" in text and "NAPARNIK_API_KEY" in text


def test_web_ui_docs_do_not_contain_stale_tool_counts():
    root = _repo_root()
    text = (root / "gateway/gateway/web_docs.py").read_text(encoding="utf-8")

    assert "полный список 49 инструментов" not in text
    assert "complete list of 49 tools" not in text
    assert "20 инструментов +" not in text
    assert "20 tools +" not in text

    assert "46-47 инструментов" not in text
    assert "46-47 tools" not in text
    assert "полный список MCP-инструментов" in text
    assert "complete list of MCP tools" in text
    assert "26 инструментов +" in text
    assert "26 tools +" in text


def test_web_ui_docs_describe_explicit_docker_stats_refresh():
    root = _repo_root()
    text = (root / "gateway/gateway/web_docs.py").read_text(encoding="utf-8")

    assert "Обновить статистику" in text
    assert "Refresh stats" in text
    assert "RAM сейчас" in text
    assert "Image on disk" in text


def test_readme_mentions_on_demand_docker_stats():
    root = _repo_root()
    text = (root / "README.md").read_text(encoding="utf-8")

    assert "Обновить статистику" in text
    assert "RAM сейчас" in text
    assert "Образ на диске" in text
