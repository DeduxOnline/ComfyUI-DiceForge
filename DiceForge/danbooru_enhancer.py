import asyncio
import hashlib
import json
import logging
import os
import re
import time
import aiohttp
import folder_paths
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .model_lists import seed_inputs
from .seed_modes import MEMORY, make_picker, pick_index
from .tag_autocomplete import INDEX, tag_key
# Danbooru Tag Enhancer: more tags for a prompt, from a real Danbooru post that has the tags already there. The most telling of the prompt's tags
# (the rarest that Danbooru knows: a character before "1girl") finds the posts, the most liked first; the seed picks one of them, by the seed modes;
# its tags that the prompt lacks are added, the most used first. The posts of a search are kept on disk, so a seed gives the same post again, also
# offline. A search without an account may have two terms, and order:score is one (rating: is free): so one tag searches, with the rating, and the
# prompt's other tags pick, among the posts found, those that have the most of them.
DANBOORU_URL = os.environ.get("DICEFORGE_DANBOORU_URL", "https://danbooru.donmai.us")
CACHE_FOLDER = os.path.join(folder_paths.get_user_directory(), "DiceForge", "danbooru")
CACHE_DAYS = 30
POSTS = 200
RATING_CHOICES = ["general", "general + sensitive", "up to questionable", "any"]
ALLOWED = {"general": {"g"}, "general + sensitive": {"g", "s"}, "up to questionable": {"g", "s", "q"}, "any": {"g", "s", "q", "e"}}
RATING_TERMS = {"general": "rating:g", "general + sensitive": "rating:g,s", "up to questionable": "rating:g,s,q", "any": ""} # Not in the two terms.
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
# The search: the tag of the prompt that says the most (in the tag lists: characters, then series, then the rarest); without tag lists, the first.
# Tags Danbooru doesn't know (masterpiece, score_9) are left out when the lists are there. Returns the search tag (a list: none for an empty
# prompt) and the prompt's tags Danbooru knows (all of them without lists).
def search_tags(tags):
    index = INDEX.load()
    known = {tag_key(tag): (kind, count) for tag, kind, count, _aliases in index.tags} if index.tags else None
    if known is None:
        return tags[:1], tags
    rank = {4: 0, 3: 1, 1: 2, 0: 3, 5: 4} # character, copyright, artist, general, meta
    found = [tag for tag in tags if tag in known]
    return sorted(found, key=lambda tag: (rank.get(known[tag][0], 3), known[tag][1]))[:1], found


def cache_path(query):
    return os.path.join(CACHE_FOLDER, hashlib.sha256(query.encode()).hexdigest()[:24] + ".json")
def read_cache(query, fresh=True):
    try:
        with open(cache_path(query), encoding="utf-8") as file:
            cached = json.load(file)
    except (OSError, ValueError):
        return None
    if not isinstance(cached, dict) or cached.get("query") != query or not isinstance(cached.get("posts"), list):
        return None
    if fresh and time.time() - cached.get("time", 0) > CACHE_DAYS * 86400:
        return None
    return cached["posts"]
def write_cache(query, posts):
    os.makedirs(CACHE_FOLDER, exist_ok=True)
    with open(cache_path(query), "w", encoding="utf-8") as file:
        json.dump({"query": query, "time": time.time(), "posts": posts}, file)
# A post as kept: its id, rating, score and tags by group.
def post_summary(post):
    if not isinstance(post, dict) or not isinstance(post.get("id"), int):
        return None
    return {"id": post["id"], "rating": str(post.get("rating") or ""), "score": post.get("score") if isinstance(post.get("score"), int) else 0,
            **{group: str(post.get(f"tag_string_{group}") or "").split() for group in GROUPS}}
# The most liked posts with the tag (order:score); refused anyway (an account's own limits, or a tag that counts double), the search again without it.
async def fetch_posts(query):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers={"User-Agent": USER_AGENT}, trust_env=True) as session:
        for tags in (f"{query} order:score".strip(), query):
            async with session.get(f"{DANBOORU_URL.rstrip('/')}/posts.json", params={"tags": tags, "limit": str(POSTS)}) as response:
                if response.status == 422 and tags != query:
                    continue
                if response.status == 422:
                    raise ValueError(f"Danbooru Tag Enhancer: Danbooru refused the search {query!r}: {(await response.text())[:200]}")
                response.raise_for_status()
                data = await response.json(content_type=None)
                return [summary for summary in map(post_summary, data if isinstance(data, list) else []) if summary]
    return []
# The posts of a search: kept ones while fresh, else asked again (and kept); when Danbooru can't be reached, the kept ones however old.
async def posts_for(query):
    posts = await asyncio.get_running_loop().run_in_executor(None, read_cache, query)
    if posts is not None:
        return posts
    try:
        posts = await fetch_posts(query)
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        stale = await asyncio.get_running_loop().run_in_executor(None, read_cache, query, False)
        if stale is not None:
            logging.warning(f"[DiceForge] Danbooru Tag Enhancer | Danbooru can't be reached ({error}): using the posts kept from before.")
            return stale
        raise ValueError(f"Danbooru Tag Enhancer: Danbooru can't be reached ({error}), and nothing is kept for these tags yet.") from None
    await asyncio.get_running_loop().run_in_executor(None, write_cache, query, posts)
    return posts


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
            description="Adds tags to a prompt from a real Danbooru post that has its tags: the seed picks one of the most liked posts with the prompt's most telling tags, and its other tags are added.",
            search_aliases=["danbooru", "tag enhancer", "prompt enhancer", "booru", "tags", "enhance prompt"],
            inputs=[
                io.String.Input("tags", multiline=True, default="1girl, hatsune miku", tooltip="The prompt's tags (or connect positive_text of CLIP Dual Text Encode). Weights, escapes and <lora:> tags are read through."),
                *seed_inputs("posts"),
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

    @classmethod
    async def execute(cls, tags, seed=0, seed_mode="random", rating="general", max_tags=15, add_general=True, add_character=False, add_copyright=False,
                      add_artist=False, exclude=DEFAULT_EXCLUDE, position="after"):
        if rating not in ALLOWED:
            raise ValueError(f"Danbooru Tag Enhancer: unknown rating {rating!r} (one of {', '.join(RATING_CHOICES)}).")
        have = prompt_tags(tags)
        loop = asyncio.get_running_loop()
        searched, known = await loop.run_in_executor(None, search_tags, have)
        query = " ".join([*searched, RATING_TERMS[rating]]).strip() # Danbooru picks the rating: the 200 posts are all of it.
        posts = [post for post in await posts_for(query) if post["rating"] in ALLOWED[rating]] # And here again, for a server that ignored it.
        wanted = [tag for tag in known if tag not in searched]
        overlap = [sum(tag in {t for group in GROUPS for t in post[group]} for tag in wanted) for post in posts]
        best = max(overlap, default=0)
        matching = [post for post, count in zip(posts, overlap) if count == best] # The posts with the most of the prompt's other tags.
        if not matching:
            raise ValueError(f"Danbooru Tag Enhancer: no {rating} post on Danbooru has {' and '.join(searched) or 'any tags'}; try other tags or another rating.")
        post = matching[pick_index(len(matching), make_picker(seed_mode, seed), seed, f"danbooru {query} {rating}")]
        MEMORY.save()
        groups = [group for group, wanted_group in (("character", add_character), ("copyright", add_copyright), ("artist", add_artist), ("general", add_general)) if wanted_group]
        added = [prompt_text(tag) for tag in added_tags(post, groups, set(have), set(prompt_tags(exclude)), max_tags)]
        text, extra = (tags or "").strip().rstrip(","), ", ".join(added)
        combined = ", ".join(part for part in ((extra, text) if position == "before" else (text, extra)) if part)
        url = f"{DANBOORU_URL.rstrip('/')}/posts/{post['id']}"
        logging.info(f"[DiceForge] Danbooru Tag Enhancer | {query or 'any'} ({len(matching)} posts) | post {post['id']} | Seed: {seed} ({seed_mode}) | Added: {extra}")
        return io.NodeOutput(combined, extra, url, post["id"])


class DanbooruTagEnhancerExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [DanbooruTagEnhancer]
async def comfy_entrypoint():
    return DanbooruTagEnhancerExtension()
