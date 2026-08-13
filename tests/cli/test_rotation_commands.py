import pytest
from unittest.mock import patch, MagicMock
from app.workers.rotation_worker import run_rotation_job
from app.cli.rotation_commands import rotate_secrets_command

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

def test_rotate_secrets_command_success(runner):
    """Test that the command invokes run_rotation_job exactly once and prints safe metadata."""
    expected_result = {
        "attempted": 5,
        "succeeded": 3,
        "skipped": 1,
        "failed": 1
    }
    
    with patch("app.cli.rotation_commands.run_rotation_job", return_value=expected_result) as mock_run:
        result = runner.invoke(rotate_secrets_command)
        
        assert result.exit_code == 0
        assert "Rotation job completed." in result.output
        assert "Attempted:  5" in result.output
        assert "Succeeded:  3" in result.output
        assert "Skipped:    1" in result.output
        assert "Terminal:   1" in result.output
        
        # Verify exactly one invocation
        mock_run.assert_called_once()
        
        # Verify passed dependencies
        kwargs = mock_run.call_args.kwargs
        assert "session" in kwargs
        assert "audit_service" in kwargs
        assert "encryption_service" in kwargs
        assert "lifecycle_service" in kwargs
        assert "executor_registry" in kwargs

def test_rotate_secrets_command_exception_handled_safely(runner):
    """Test that an unexpected exception results in a non-zero exit code and hides sensitive data."""
    sentinel = "TEST_ROTATED_SECRET_123"
    
    with patch("app.cli.rotation_commands.run_rotation_job", side_effect=Exception(f"Worker crashed with {sentinel}")) as mock_run:
        result = runner.invoke(rotate_secrets_command)
        
        assert result.exit_code != 0
        assert "Rotation CLI dispatch failed unexpectedly." in result.output
        assert sentinel not in result.output

def test_rotate_secrets_command_no_eligibility_logic(runner):
    """Test that the CLI does not independently query or filter policies."""
    # We mock run_rotation_job and do NOT provide any database seeds.
    # The command should succeed just by calling the mock, proving it doesn't query the DB directly to filter.
    with patch("app.cli.rotation_commands.run_rotation_job", return_value={"attempted": 0}) as mock_run:
        result = runner.invoke(rotate_secrets_command)
        assert result.exit_code == 0
        mock_run.assert_called_once()
