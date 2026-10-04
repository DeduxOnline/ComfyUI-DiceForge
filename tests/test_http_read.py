# read_up_to (DiceForge/http_read.py): a body that arrives in slow pieces is read to the end (aiohttp's content.read(n) gives only what has come so
# far), and reading stops one byte past the limit, so a too big body is noticed without reading all of it.
import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import aiohttp
import pytest
from DiceForge.http_read import read_up_to


@pytest.fixture
def slow_server():
    """A server sending server.pieces pieces of server.size bytes (A's, then B's...), with a pause after each."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(self.server.pieces * self.server.size))
            self.end_headers()
            for index in range(self.server.pieces):
                try:
                    self.wfile.write(bytes([65 + index % 26]) * self.server.size)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError): # The reader stopped at its limit.
                    return
                time.sleep(0.02)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.pieces, server.size = 10, 3000
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


def read(server, limit):
    async def get():
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{server.server_port}/") as response:
                return await read_up_to(response, limit)
    return asyncio.run(get())


def test_a_body_in_slow_pieces_is_read_to_the_end(slow_server):
    body = read(slow_server, 10 ** 6)
    assert len(body) == 30000 and body == b"".join(bytes([65 + index]) * 3000 for index in range(10))


def test_reading_stops_one_byte_past_the_limit(slow_server):
    body = read(slow_server, 5000)
    assert body == b"A" * 3000 + b"B" * 2001 # limit + 1: the caller knows it was too big.
    assert len(read(slow_server, 30000)) == 30000 # Exactly the limit: all of it, nothing more to read.


def test_an_empty_body(slow_server):
    slow_server.pieces = 0
    assert read(slow_server, 100) == b""
