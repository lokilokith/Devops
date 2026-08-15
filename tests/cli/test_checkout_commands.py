import pytest
from unittest.mock import patch

from app.cli.checkout_commands import process_expirations_cmd


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


def test_process_expirations_command_success(runner):
    """Test that the command invokes run_expiration_job and prints output."""
    expected_result = {
        "run_id": "808f9d0c-1234-5678",
        "attempted": 5,
        "succeeded": 4,
        "failed": 1,
        "duration_seconds": 0.5,
    }

    with patch("app.cli.checkout_commands.run_expiration_job", return_value=expected_result) as mock_run:
        result = runner.invoke(process_expirations_cmd)

        assert result.exit_code == 0
        assert "Run ID: 808f9d0c-1234-5678" in result.output
        assert "Processed 4 of 5 expired leases." in result.output
        assert "Failed: 1" in result.output

        mock_run.assert_called_once()
        kwargs = mock_run.call_args.args
        assert len(kwargs) == 2  # db.session, service


def test_process_expirations_command_exception(runner):
    """Test that the command handles exceptions safely."""
    with patch("app.cli.checkout_commands.run_expiration_job", side_effect=Exception("Database down")) as mock_run:
        result = runner.invoke(process_expirations_cmd)

        assert result.exit_code == 0 # click.secho just prints red, exit code might be 0 unless sys.exit(1) is called
        assert "Expiration processing failed: Database down" in result.output
        mock_run.assert_called_once()
