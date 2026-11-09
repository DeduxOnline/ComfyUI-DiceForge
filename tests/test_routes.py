# get_routes (DiceForge/routes.py): the route table of ComfyUI's server, or None outside it. A module's register_routes() does nothing
# when there is none (the tests), and registers on the table when there is one.
import sys
import types

from DiceForge.routes import get_routes


def test_outside_the_server_there_are_no_routes(monkeypatch):
    monkeypatch.setitem(sys.modules, "server", types.ModuleType("server"))
    assert get_routes() is None


def test_the_server_route_table_is_returned(monkeypatch):
    table = object()
    server = types.ModuleType("server")
    server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=table))
    monkeypatch.setitem(sys.modules, "server", server)
    assert get_routes() is table
