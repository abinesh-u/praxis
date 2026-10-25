from praxis_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "praxis 0.1.0" in result.stdout


def test_launch_without_args(tmp_path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Personal AI Execution Partner" in result.stdout
    assert "Profile:" in result.stdout
    assert "Quick Commands:" in result.stdout


def test_launch_command(tmp_path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))
    result = runner.invoke(app, ["launch"])
    assert result.exit_code == 0
    assert "Personal AI Execution Partner" in result.stdout
