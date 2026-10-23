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


# An answer of another site (Civitai, Danbooru, e621, Safebooru) as text: far bigger than any real one is an error, so a site gone wrong can't fill
# the memory. cut: the first limit bytes are enough (the start of an error page for a message).
ANSWER_BYTES = 16 * 1024 * 1024
async def read_text(response, limit=ANSWER_BYTES, cut=False):
    data = await read_up_to(response, limit)
    if len(data) > limit and not cut:
        raise ValueError(f"{response.url.host} answered more than {limit // (1024 * 1024)} MB")
    return data[:limit].decode(response.charset or "utf-8", errors="replace")
