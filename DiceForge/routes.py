# What every DiceForge route uses: the body of a POST request, and file work in a thread (tests/test_event_loop.py checks that no route
# touches a file on the event loop).
import asyncio
from aiohttp import web


# The JSON object a POST request sends; anything else (no JSON, a list, a number) is a 400 with a message instead of a server error.
async def json_body(request):
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="DiceForge: the request body is not valid JSON.") from None
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="DiceForge: the request body must be a JSON object.")
    return body


# A route's work with files (reading, writing, listing folders), in a thread: on ComfyUI's event loop it would hold up every other request and
# the progress of a run meanwhile (Sonar S7493). The handler reads what the request sends; the rest goes through here.
async def in_thread(function, *args):
    return await asyncio.get_running_loop().run_in_executor(None, function, *args)
