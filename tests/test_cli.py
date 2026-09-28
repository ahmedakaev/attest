from click.testing import CliRunner

from attest.cli import cli


def test_cli_init_and_target_management(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    # 1. attest init
    res = runner.invoke(cli, ["init"])
    assert res.exit_code == 0
    assert "Attest is ready!" in res.output

    # 2. attest target add
    res = runner.invoke(
        cli,
        [
            "target",
            "add",
            "--id",
            "test-gpt4o",
            "--url",
            "https://api.test.com/v1",
            "--model",
            "gpt-4o",
            "--key",
            "test-dummy-cli-key",
        ],
    )
    assert res.exit_code == 0
    assert "Target test-gpt4o saved." in res.output

    # 3. attest target list
    res = runner.invoke(cli, ["target", "list"])
    assert res.exit_code == 0
    assert "test-gpt4o" in res.output
    assert "gpt-4o" in res.output

    # 4. attest estimate
    res = runner.invoke(cli, ["estimate", "test-gpt4o"])
    assert res.exit_code == 0
    assert "Run Budget Estimation" in res.output
    assert "Total Prompts" in res.output

    # 5. attest target delete
    res = runner.invoke(cli, ["target", "delete", "test-gpt4o"])
    assert res.exit_code == 0
    assert "Target test-gpt4o deleted." in res.output


def test_cli_wire_model_and_schedules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(cli, ["init"])

    # 1. Target add with wire-model
    res = runner.invoke(
        cli,
        [
            "target",
            "add",
            "--id",
            "or-llama",
            "--url",
            "https://openrouter.ai/api/v1",
            "--model",
            "llama-3.3-70b-instruct",
            "--wire-model",
            "meta-llama/llama-3.3-70b-instruct",
            "--key",
            "test-key",
        ],
    )
    assert res.exit_code == 0
    assert "Target or-llama saved." in res.output

    # 2. Baseline list (empty initially)
    res_b = runner.invoke(cli, ["baseline", "list"])
    assert res_b.exit_code == 0

    # 3. Schedule add
    res_s = runner.invoke(
        cli,
        [
            "schedule",
            "add",
            "or-llama",
            "--interval-hours",
            "12",
            "--battery",
            "quick",
        ],
    )
    assert res_s.exit_code == 0
    assert "Schedule #1" in res_s.output
    assert "12 hours" in res_s.output

    # 4. Schedule list
    res_sl = runner.invoke(cli, ["schedule", "list"])
    assert res_sl.exit_code == 0
    assert "or-llama" in res_sl.output
    assert "Every 12h" in res_sl.output

    # 5. Schedule delete
    res_sd = runner.invoke(cli, ["schedule", "delete", "1"])
    assert res_sd.exit_code == 0
    assert "Schedule #1 deleted." in res_sd.output


def test_cli_locale_option():
    runner = CliRunner()

    # 1. run --help has --locale
    res_run = runner.invoke(cli, ["run", "--help"])
    assert res_run.exit_code == 0
    assert "--locale" in res_run.output
    assert "[ru|en]" in res_run.output

    # 2. audit alias has --locale
    res_audit = runner.invoke(cli, ["audit", "--help"])
    assert res_audit.exit_code == 0
    assert "--locale" in res_audit.output
    assert "[ru|en]" in res_audit.output

    # 3. report latest has --locale
    res_latest = runner.invoke(cli, ["report", "latest", "--help"])
    assert res_latest.exit_code == 0
    assert "--locale" in res_latest.output

    # 4. report export has --locale
    res_export = runner.invoke(cli, ["report", "export", "--help"])
    assert res_export.exit_code == 0
    assert "--locale" in res_export.output


def test_cli_submodules_structure():
    import attest.cli as cli_pkg
    from attest.cli.baselines import cmd_baseline
    from attest.cli.compare import cmd_compare
    from attest.cli.init_cmd import cmd_init
    from attest.cli.reports import report_group
    from attest.cli.runs import cmd_run
    from attest.cli.schedules import schedule_group
    from attest.cli.targets import cmd_estimate, target_group
    from attest.cli.ui import cmd_ui

    assert hasattr(cli_pkg, "cli")
    assert hasattr(cli_pkg, "main")
    assert cmd_init.name == "init"
    assert target_group.name == "target"
    assert cmd_estimate.name == "estimate"
    assert cmd_baseline.name == "baseline"
    assert cmd_run.name == "run"
    assert report_group.name == "report"
    assert schedule_group.name == "schedule"
    assert cmd_compare.name == "compare"
    assert cmd_ui.name == "ui"
