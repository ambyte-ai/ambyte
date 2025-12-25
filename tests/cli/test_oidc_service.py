import threading
from queue import Queue
from unittest import mock

from ambyte_cli.services.oidc import AuthCallbackHandler, AuthServer, OidcService

# ==============================================================================
# UNIT TESTS: OidcService
# ==============================================================================


def test_get_auth_url():
	"""Verify URL construction and state randomness."""
	svc = OidcService(port=9999)
	base_url = 'https://api.test.ai'

	url, state = svc.get_auth_url(base_url)

	assert base_url in url
	assert 'state=' in url
	assert 'redirect_uri=http%3A%2F%2Flocalhost%3A9999' in url
	assert len(state) >= 16

	# Ensure state is different on second call
	_, state2 = svc.get_auth_url(base_url)
	assert state != state2


def test_open_browser_success():
	"""Verify webbrowser.open is called."""
	svc = OidcService()
	with mock.patch('webbrowser.open') as mock_open:
		svc.open_browser('http://auth')
		mock_open.assert_called_once_with('http://auth')


def test_open_browser_failure(capsys):
	"""Verify fallback print when browser cannot open."""
	svc = OidcService()
	with mock.patch('webbrowser.open', side_effect=Exception('Failed')):
		svc.open_browser('http://auth-url')

	captured = capsys.readouterr()
	assert 'Could not open browser automatically' in captured.out
	assert 'http://auth-url' in captured.out


def test_wait_for_token_timeout():
	"""Verify wait_for_token returns None on timeout."""
	svc = OidcService(port=4243)

	# We patch the AuthServer CLASS so the instantiation returns a mock
	with mock.patch('ambyte_cli.services.oidc.AuthServer') as mock_server_class:
		mock_instance = mock_server_class.return_value

		# This will trigger the queue.get timeout but call mock_instance.shutdown()
		result = svc.wait_for_token(timeout=0.1)

		assert result is None
		# Verify the lifecycle was attempted on the mock
		mock_instance.serve_forever.assert_called()
		mock_instance.shutdown.assert_called()


# ==============================================================================
# UNIT TESTS: AuthCallbackHandler
# ==============================================================================


class MockRequest:
	"""Simulates a socket request for the HTTP handler."""

	def makefile(self, *args, **kwargs):
		return mock.Mock()


def test_handler_do_get():
	"""
	Directly tests the do_GET logic using a mock instance.
	Avoids AttributeError by calling the class method with a mock 'self'.
	"""
	# 1. Setup Mock Server and Queue
	mock_server = mock.MagicMock()
	mock_server.result_queue = Queue()

	# 2. Create a mock handler instance
	# We use spec=AuthCallbackHandler so it has the right 'shape'
	handler = mock.Mock(spec=AuthCallbackHandler)
	handler.server = mock_server
	handler.path = '/?token=test-jwt-token&state=test-random-state'
	handler.wfile = mock.Mock()  # Mock the stream where HTML is written

	# 3. Execute the REAL do_GET logic using our mock 'handler' as 'self'
	AuthCallbackHandler.do_GET(handler)

	# 4. Assertions: Logic inside do_GET
	# A. Check if the token and state were extracted and queued
	result = mock_server.result_queue.get(timeout=1)
	assert result['token'] == 'test-jwt-token'
	assert result['state'] == 'test-random-state'

	# B. Check if HTTP response methods were called
	handler.send_response.assert_called_with(200)
	handler.send_header.assert_called_with('Content-type', 'text/html')
	handler.end_headers.assert_called_once()

	# C. Check if the success HTML was written to the client
	handler.wfile.write.assert_called()
	written_bytes = handler.wfile.write.call_args[0][0]
	written_text = written_bytes.decode('utf-8')
	assert 'Ambyte CLI' in written_text
	assert 'Authentication complete' in written_text
	assert 'window.close()' in written_text


def test_handler_log_message():
	"""Ensure log_message is silenced (for 100% coverage)."""
	handler = mock.MagicMock(spec=AuthCallbackHandler)
	# This shouldn't do anything or raise
	AuthCallbackHandler.log_message(handler, 'format', 'arg1')


# ==============================================================================
# INTEGRATION-ISH: wait_for_token Success
# ==============================================================================


def test_wait_for_token_success():
	"""
	Simulates a successful background token arrival.
	"""
	svc = OidcService()

	def simulate_arrival():
		# Simulate the handler putting data into the queue
		svc.result_queue.put({'token': 'success-token', 'state': 'valid-state'})

	with mock.patch('ambyte_cli.services.oidc.AuthServer') as mock_server_class:
		# Start a timer to drop the token into the queue while wait_for_token is blocking
		threading.Timer(0.1, simulate_arrival).start()

		result = svc.wait_for_token(timeout=1.0)

		assert result is not None
		assert result['token'] == 'success-token'
		assert result['state'] == 'valid-state'
