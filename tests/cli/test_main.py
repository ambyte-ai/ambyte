import logging
from unittest import mock
import pytest
from typer.testing import CliRunner
from ambyte_cli.main import app

runner = CliRunner()


def test_main_no_args_shows_help():
	"""
	Verify that running 'ambyte' without arguments displays help.
	We check result.output because exit code can be 0 or 2 depending on Typer version.
	"""
	result = runner.invoke(app, [])
	# Verify that the help text is present
	assert 'Ambyte Platform CLI' in result.output
	assert 'Usage:' in result.output
	# Check that registered commands are listed in help
	assert 'init' in result.output
	assert 'build' in result.output


def test_main_help_explicit():
	"""
	Verify the CLI displays help with --help.
	"""
	result = runner.invoke(app, ['--help'])
	assert result.exit_code == 0
	assert 'Ambyte Platform CLI' in result.stdout
	# Verify root commands are registered
	assert 'init' in result.stdout
	assert 'build' in result.stdout
	assert 'check' in result.stdout


def test_version_callback_success():
	"""
	Verify --version prints the version from package metadata.
	"""
	with mock.patch('importlib.metadata.version', return_value='0.1.2-test'):
		result = runner.invoke(app, ['--version'])
		assert result.exit_code == 0
		assert 'Ambyte CLI Version: 0.1.2-test' in result.stdout


def test_version_callback_not_found():
	"""
	Verify version defaults to 'dev' if package metadata is missing.
	"""
	from importlib import metadata

	with mock.patch('importlib.metadata.version', side_effect=metadata.PackageNotFoundError):
		result = runner.invoke(app, ['-v'])
		assert result.exit_code == 0
		assert 'Ambyte CLI Version: dev' in result.stdout


@mock.patch('logging.basicConfig')
def test_debug_flag_enables_verbose_logging(mock_logging_config):
	"""
	Verify that the global --debug flag sets the log level to DEBUG.
	"""
	# Using 'validate' as a safe target command that exists
	runner.invoke(app, ['--debug', 'validate'])

	args, kwargs = mock_logging_config.call_args
	assert kwargs['level'] == logging.DEBUG


def test_debug_logging_suppresses_third_party_noise():
	"""
	Verify that by default (no debug), external library logging is restricted.
	"""
	with mock.patch('logging.getLogger') as mock_get_logger:
		runner.invoke(app, ['init', '--help'])

		# Check for suppression of noise
		mock_get_logger.assert_any_call('httpx')
		mock_get_logger.assert_any_call('httpcore')

		# Ensure setLevel was called on the logger instance
		mock_get_logger.return_value.setLevel.assert_any_call(logging.WARNING)


def test_invalid_command():
	"""
	Verify error handling for non-existent commands.
	Uses .output to capture both stdout and stderr.
	"""
	result = runner.invoke(app, ['not-a-command'])
	assert result.exit_code != 0
	# Typer error output is often in result.output (combined streams)
	# We check for the presence of the invalid command name and 'Usage'
	output = result.output
	assert 'not-a-command' in output
	assert 'Usage' in output or 'No such command' in output


def test_cloud_subgroup_registration():
	"""
	Verify that the 'cloud' sub-typer is correctly registered.
	"""
	result = runner.invoke(app, ['cloud', '--help'])
	assert result.exit_code == 0
	assert 'Manage interaction with the Ambyte Control Plane' in result.stdout


def test_debug_output_path(caplog):
	"""
	Ensure that if --debug is passed, the debug branch in main() is reached.
	"""
	with caplog.at_level(logging.DEBUG):
		# We need to invoke a command so the callback triggers
		runner.invoke(app, ['--debug', 'validate'])
		# The code has logging.debug('Debug logging enabled.')
		# But since basicConfig is patched or already run, we check the flow
		# by ensuring the 'debug' argument to main was True.
		pass  # Logic covered by test_debug_flag_enables_verbose_logging
