import asyncio
import logging
import os
import re
import aiohttp
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .tag_autocomplete import INDEX, tag_key
# Danbooru Tag Enhancer: more tags for a prompt, from a real Danbooru post that has the tags already there. Danbooru picks a random post
# (/posts/random) with the most telling two of the prompt's tags (the rarest that Danbooru knows: a character before "1girl") and the rating; its
# tags that the prompt lacks are added, the most used first. A new post on every run: the node shows the prompt it made, to copy the one you like.
# A search without an account may have two tags (rating: is free); with none found for both, each one alone.
DANBOORU_URL = os.environ.get("DICEFORGE_DANBOORU_URL", "https://danbooru.donmai.us")
RATING_CHOICES = ["general", "general + sensitive", "up to questionable", "any"]
RATING_TERMS = {"general": "rating:g", "general + sensitive": "rating:g,s", "up to questionable": "rating:g,s,q", "any": ""}
DEFAULT_EXCLUDE = "signature, watermark, artist_name, twitter_username, web_address, dated, speech_bubble, comic, english_text, text_focus"
GROUPS = ("general", "character", "copyright", "artist", "meta")
USER_AGENT = "DiceForge (ComfyUI custom nodes; https://github.com/DeduxOnline/ComfyUI-DiceForge)"


# The prompt's tags as Danbooru writes them: one per comma or line, weights and escapes taken off ("(long hair:1.2)" -> long_hair), lower case.
def prompt_tags(text):
    tags = []
    for part in re.split(r"[,\n]", text or ""):
        part = re.sub(r"<[^>]*>", "", part) # <lora:...> tags.
        part = re.sub(r":\s*-?\d+(?:\.\d+)?\s*\)?\s*$", "", part.strip()) # (tag:1.2) weights.
        part = part.replace("\\(", "\u0001").replace("\\)", "\u0002").strip(" ()[]{}").replace("\u0001", "(").replace("\u0002", ")")
        key = tag_key(part)
        if key and key not in tags and not key.startswith(("embedding:", "__")):
            tags.append(key)
    return tags
# The tag as the models learned it: spaces for underscores (not in emoticons like ^_^), escaped parentheses (as the autocomplete writes it).
def prompt_text(tag):
    spaced = tag.replace("_", " ") if re.search(r"[a-z]{2}", tag, re.IGNORECASE) and len(tag) > 3 else tag
    return re.sub(r"([()])", r"\\\1", spaced)
# The search: the two tags of the prompt that say the most (in the tag lists: characters, then series, then the rarest); without tag lists, the
# first two. Tags Danbooru doesn't know (masterpiece, score_9) are left out when the lists are there.
def search_tags(tags):
    index = INDEX.load()
    if not index.tags:
        return tags[:2]
    known = {tag_key(tag): (kind, count) for tag, kind, count, _aliases in index.tags}
    rank = {4: 0, 3: 1, 1: 2, 0: 3, 5: 4} # character, copyright, artist, general, meta
    return sorted((tag for tag in tags if tag in known), key=lambda tag: (rank.get(known[tag][0], 3), known[tag][1]))[:2]
# The searches to try: both tags, then each alone (a pair no post has together).
def searches(tags):
    return [tags] + ([[tag] for tag in tags] if len(tags) > 1 else [])


# A post as kept: its id, rating, score and tags by group.
def post_summary(post):
    if not isinstance(post, dict) or not isinstance(post.get("id"), int):
        return None
    return {"id": post["id"], "rating": str(post.get("rating") or ""), "score": post.get("score") if isinstance(post.get("score"), int) else 0,
            **{group: str(post.get(f"tag_string_{group}") or "").split() for group in GROUPS}}
# A random post of a search (Danbooru picks it), or None when no post has the tags.
async def random_post(session, query):
    async with session.get(f"{DANBOORU_URL.rstrip('/')}/posts/random.json", params={"tags": query}) as response:
        if response.status == 404:
            return None
        if response.status == 422:
            raise ValueError(f"Danbooru Tag Enhancer: Danbooru refused the search {query!r}: {(await response.text())[:200]}")
        response.raise_for_status()
        return post_summary(await response.json(content_type=None))
# The post: both tags with the rating, else each tag alone; returns it and the search that found it.
async def find_post(tags, rating_term):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers={"User-Agent": USER_AGENT}, trust_env=True) as session:
            for search in searches(tags):
                query = " ".join([*search, rating_term]).strip()
                post = await random_post(session, query)
                if post:
                    return post, query
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        raise ValueError(f"Danbooru Tag Enhancer: Danbooru can't be reached ({error}).") from None
    return None, None


# The tags of a post to add: of the groups asked for, not in the prompt, not excluded; the most used first (by the tag lists), at most max_tags.
def added_tags(post, groups, have, exclude, max_tags):
    index = INDEX.load()
    counts = {tag_key(tag): count for tag, _kind, count, _aliases in index.tags} if index.tags else {}
    tags = [tag for group in groups for tag in post.get(group, []) if tag not in have and tag not in exclude]
    tags = sorted(dict.fromkeys(tags), key=lambda tag: -counts.get(tag, 0)) if counts else list(dict.fromkeys(tags))
    return tags[:max_tags] if max_tags else tags


class DanbooruTagEnhancer(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeDanbooruEnhancer",
            display_name="Danbooru Tag Enhancer",
            category="DiceForge/conditioning",
            description="Adds tags to a prompt from a random Danbooru post that has its most telling tags: a new post on every run, and the prompt it made is shown on the node.",
            search_aliases=["danbooru", "tag enhancer", "prompt enhancer", "booru", "tags", "enhance prompt", "random post"],
            is_output_node=True, # Runs (and shows its prompt) also with nothing connected.
            inputs=[
                io.String.Input("tags", multiline=True, default="1girl, hatsune miku", tooltip="The prompt's tags (or connect positive_text of CLIP Dual Text Encode). Weights, escapes and <lora:> tags are read through."),
                io.Combo.Input("rating", options=RATING_CHOICES, default="general", tooltip="The posts' ratings: general only (safe), with sensitive, up to questionable, or any."),
                io.Int.Input("max_tags", default=15, min=0, max=200, tooltip="Tags added at most (the most used first); 0: all of the post's."),
                io.Boolean.Input("add_general", default=True, tooltip="Add the post's general tags (what is in the picture: pose, clothes, background...)."),
                io.Boolean.Input("add_character", default=False, tooltip="Add the post's characters.", advanced=True),
                io.Boolean.Input("add_copyright", default=False, tooltip="Add the post's series.", advanced=True),
                io.Boolean.Input("add_artist", default=False, tooltip="Add the post's artists (artist styles).", advanced=True),
                io.String.Input("exclude", multiline=True, default=DEFAULT_EXCLUDE, tooltip="Tags never added, separated by commas.", advanced=True),
                io.Combo.Input("position", options=["after", "before"], default="after", tooltip="Where the added tags go: after the prompt's tags or before them.", advanced=True),
            ],
            outputs=[
                io.String.Output(display_name="text", tooltip="The prompt with the added tags: connect it to CLIP Dual Text Encode's positive (or a text encoder)."),
                io.String.Output(display_name="added_tags", tooltip="Only the added tags."),
                io.String.Output(display_name="post_url", tooltip="The Danbooru post the tags came from."),
                io.Int.Output(display_name="post_id", tooltip="Its id."),
            ],
        )

    # A new post on every run, like Danbooru's random post.
    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return os.urandom(8).hex()

    @classmethod
    async def execute(cls, tags, rating="general", max_tags=15, add_general=True, add_character=False, add_copyright=False, add_artist=False,
                      exclude=DEFAULT_EXCLUDE, position="after"):
        if rating not in RATING_TERMS:
            raise ValueError(f"Danbooru Tag Enhancer: unknown rating {rating!r} (one of {', '.join(RATING_CHOICES)}).")
        have = prompt_tags(tags)
        searched = await asyncio.get_running_loop().run_in_executor(None, search_tags, have)
        post, query = await find_post(searched, RATING_TERMS[rating])
        if not post:
            raise ValueError(f"Danbooru Tag Enhancer: no {rating} post on Danbooru has {' or '.join(searched) or 'any tags'}; try other tags or another rating.")
        groups = [group for group, wanted in (("character", add_character), ("copyright", add_copyright), ("artist", add_artist), ("general", add_general)) if wanted]
        added = [prompt_text(tag) for tag in added_tags(post, groups, set(have), set(prompt_tags(exclude)), max_tags)]
        text, extra = (tags or "").strip().rstrip(","), ", ".join(added)
        combined = ", ".join(part for part in ((extra, text) if position == "before" else (text, extra)) if part)
        url = f"{DANBOORU_URL.rstrip('/')}/posts/{post['id']}"
        logging.info(f"[DiceForge] Danbooru Tag Enhancer | {query or 'any'} | post {post['id']} | Added: {extra}")
        shown = {"text": combined, "added": extra, "url": url, "id": post["id"], "search": query, "rating": post["rating"]}
        return io.NodeOutput(combined, extra, url, post["id"], ui={"dice_forge_danbooru": [shown]})


class DanbooruTagEnhancerExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [DanbooruTagEnhancer]
async def comfy_entrypoint():
    return DanbooruTagEnhancerExtension()
