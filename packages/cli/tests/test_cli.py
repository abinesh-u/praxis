from praxis_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "praxis 0.1.0" in result.stdout
