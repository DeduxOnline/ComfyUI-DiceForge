# A response's whole body, read as it arrives. aiohttp's response.content.read(n) gives at most n bytes but only what has come so far (often the
# first few kilobytes of a big file), so a download read that way is cut short; this reads to the end.
CHUNK = 64 * 1024


# Up to limit + 1 bytes: one more than allowed tells the caller the body was too big, without reading all of it.
async def read_up_to(response, limit):
    data = bytearray()
    async for chunk in response.content.iter_chunked(CHUNK):
        data += chunk
        if len(data) > limit:
            break
    return bytes(data[:limit + 1])
