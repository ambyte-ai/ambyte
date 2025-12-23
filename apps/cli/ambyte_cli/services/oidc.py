"""
Logic for handling the ephemeral local server during Browser-based OIDC login.
Uses only standard library components to keep CLI overhead minimal.
"""

import http.server
import secrets
import threading
import urllib.parse
import webbrowser
from queue import Queue
from typing import cast

from ambyte_cli.ui.console import console


class AuthServer(http.server.HTTPServer):
	"""
	Custom HTTPServer subclass to satisfy type checkers.
	Explicitly defines the queue used to pass tokens back to the main thread.
	"""

	result_queue: Queue


class AuthCallbackHandler(http.server.BaseHTTPRequestHandler):
	"""
	HTTP Handler that catches the redirect from the Ambyte Dashboard.
	"""

	def log_message(self, format, *args):
		"""Silence standard logging to keep the terminal clean."""
		return

	def do_GET(self):
		"""
		Handles the redirect. Expected URL: http://localhost:4242/?token=...&state=...
		"""
		query = urllib.parse.urlparse(self.path).query
		params = urllib.parse.parse_qs(query)

		# Extract data from the URL
		token = params.get('token', [None])[0]
		state = params.get('state', [None])[0]

		# Put the result in the queue for the main thread
		server = cast(AuthServer, self.server)
		server.result_queue.put({'token': token, 'state': state})

		# Send a user-friendly response to the browser
		self.send_response(200)
		self.send_header('Content-type', 'text/html')
		self.end_headers()

		success_html = """
        <html>
            <body style="font-family: sans-serif; text-align: center; padding-top: 50px; background: #0f172a; color: white;">
                <h1 style="color: #22d3ee;">Ambyte CLI</h1>
                <p>Authentication complete. You can close this window and return to your terminal.</p>
                <script>window.close();</script>
            </body>
        </html>
        """  # noqa: E501
		self.wfile.write(success_html.encode('utf-8'))


class OidcService:
	"""
	Manages the lifecycle of the local login server.
	"""

	def __init__(self, port: int = 4242):
		self.port = port
		self.result_queue: Queue = Queue()
		self._server: http.server.HTTPServer | None = None
		self._thread: threading.Thread | None = None

	def get_auth_url(self, base_url: str) -> tuple[str, str]:
		"""
		Constructs the login URL with a secure state and redirect_uri.
		"""
		state = secrets.token_urlsafe(16)
		redirect_uri = f'http://localhost:{self.port}'

		params = {'redirect_uri': redirect_uri, 'state': state, 'source': 'cli'}
		url = f'{base_url.rstrip("/")}/login/cli?{urllib.parse.urlencode(params)}'
		return url, state

	def wait_for_token(self, timeout: int = 120) -> dict | None:
		"""
		Starts the local server and blocks until a token is received or timeout hits.
		"""
		self._server = AuthServer(('localhost', self.port), AuthCallbackHandler)
		self._server.result_queue = self.result_queue

		self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
		self._thread.start()

		console.print(f'[dim]Waiting for browser authentication on port {self.port}...[/dim]')

		try:
			# Block until data arrives or timeout
			return self.result_queue.get(timeout=timeout)
		except Exception:
			console.print('\n[error]Login timed out or failed.[/error]')
			return None
		finally:
			self.shutdown()

	def shutdown(self):
		"""Cleans up the server and thread."""
		if self._server:
			self._server.shutdown()
			self._server.server_close()
		if self._thread:
			self._thread.join(timeout=1.0)

	def open_browser(self, url: str):
		"""Attempts to open the user's default browser."""
		try:
			webbrowser.open(url)
		except Exception:
			console.print('\n[warning]Could not open browser automatically.[/warning]')
			# TODO: Add actual URL.
			console.print(f'Please visit this URL to login:\n[highlight]{url}[/highlight]\n')
