import asyncio
import logging
import os
import random
import re
import aiohttp
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .clip_text_encode_pos_neg import fill_in, wildcards_signature
from .tag_autocomplete import INDEX, tag_key
# Danbooru Tag Enhancer: more tags for a prompt, from real Danbooru posts that have the tags already there. Danbooru picks a random post
# (/posts/random) with the most telling two of the prompt's tags (the rarest that Danbooru knows: a character before "1girl") and the rating; its
# tags that the prompt lacks are added, the most used first. Random mode: new posts on every run, written into post_ids; fixed mode: those posts
# again (as a seed's fixed). A search without an account may have two tags (rating: is free); with none found for both, each one alone.
DANBOORU_URL = os.environ.get("DICEFORGE_DANBOORU_URL", "https://danbooru.donmai.us")
RATING_CHOICES = ["general", "general + sensitive", "up to questionable", "any"]
RATING_TERMS = {"general": "rating:g", "general + sensitive": "rating:g,s", "up to questionable": "rating:g,s,q", "any": ""}
DEFAULT_EXCLUDE = "signature, watermark, artist_name, *username, web_address, dated, speech_bubble, comic, *_text, text_focus, *censor*"
GROUPS = ("general", "character", "copyright", "artist", "meta")
MAX_POSTS = 5
# Appearance tags (how the character looks: hair, eyes, skin, body, ears, tails...): left out with include_appearance off, so the post adds the
# pose, clothes and scene but your character keeps its own look. A tag is one when a word of it is one of these, or it is one of the tags below.
APPEARANCE_WORDS = re.compile(r"(?:^|_)(?:hair|haired|eyes?|pupils|sclera|eyelashes|eyebrows|skin|skinned|ears?|tail|tails|horns?|wings?|breasts?|bangs|sidelocks|"
                              r"ahoge|twintails|ponytail|braids?|bun|buns|drills|halo|freckles|mole|fangs?|abs|muscular|petite|curvy|plump|tall|height)(?:_|$)")
APPEARANCE_TAGS = {"heterochromia", "flat_chest", "bob_cut", "hime_cut", "eyeliner", "makeup", "lipstick", "elf", "dark-skinned_female", "dark-skinned_male",
                   "tan", "tanlines", "pale_skin", "colored_skin", "mature_female", "loli", "shota", "kemonomimi_mode"}
# Not the look itself: accessories and what is done with the hair or ears (hair_ornament, hair_ribbon, hand_in_hair, adjusting_hair...).
NOT_APPEARANCE = re.compile(r"ornament|ribbon|bow|clip|band|flower|scrunchie|pin|bobbles|tubes|tie|hand|holding|grab|adjusting|blowing|covering|pull|ring")
def is_appearance(tag):
    return tag in APPEARANCE_TAGS or (bool(APPEARANCE_WORDS.search(tag)) and not NOT_APPEARANCE.search(tag))
# Clothes and accessories (shirt, pleated_skirt, school_uniform, hair_ornament, glasses...), also how much is worn (nude, barefoot): left out with
# include_clothes off, so your character keeps its own outfit. A tag is one when a word of it (between _ or -) is one of these.
CLOTHES_WORDS = re.compile(r"(?:^|[_-])(?:shirt|blouse|skirt|miniskirt|dress|sundress|gown|jacket|coat|cardigan|hoodie|sweater|vest|cape|capelet|cloak|robe|"
                           r"pants|trousers|jeans|shorts|leggings|thighhighs|kneehighs|socks|pantyhose|stockings|legwear|footwear|shoes|boots|sandals|heels|"
                           r"sneakers|loafers|slippers|gloves|mittens|hat|cap|beret|helmet|headwear|headband|headset|headphones|hood|hairband|hairclip|"
                           r"ornament|ribbon|bow|bowtie|necktie|tie|neckerchief|scarf|choker|collar|sleeves|sleeveless|strapless|belt|suit|tuxedo|armor|"
                           r"uniform|serafuku|kimono|yukata|hakama|bikini|swimsuit|leotard|bodysuit|apron|bra|panties|underwear|lingerie|garter|garters|"
                           r"earrings|necklace|jewelry|bracelet|glasses|eyewear|sunglasses|mask|crown|tiara|veil|clothes|clothing|outfit|costume|frills|"
                           r"frilled|buttons|zipper|lace|camisole|tank_top|crop_top|tube_top|cutout|off_shoulder|off-shoulder|bare_shoulders|nude|naked|"
                           r"topless|bottomless|barefoot|no_bra|no_panties)(?:[_-]|$)")
def is_clothes(tag):
    return bool(CLOTHES_WORDS.search(tag))
# The scene (simple_background, outdoors, classroom, night, cherry_blossoms, on_bed...): left out with include_background off, so your prompt keeps
# its own place. A tag is one when a word of it is one of these.
BACKGROUND_WORDS = re.compile(r"(?:^|[_-])(?:background|outdoors|indoors|scenery|landscape|sky|cloud|clouds|cloudy|day|night|sunset|sunrise|evening|"
                              r"twilight|dusk|dawn|tree|trees|grass|forest|field|ocean|sea|beach|shore|water|waterfall|lake|river|pool|underwater|city|"
                              r"cityscape|town|street|road|alley|building|buildings|skyscraper|architecture|room|bedroom|classroom|bathroom|kitchen|library|"
                              r"office|hallway|window|curtains|wall|floor|ceiling|door|stairs|fence|railing|park|garden|mountain|mountains|hill|horizon|moon|"
                              r"sunlight|moonlight|light_rays|sunbeam|rain|snow|snowing|leaves|petals|cherry_blossoms|bed|couch|sofa|chair|table|desk|"
                              r"lamp|stage|school|shrine|temple|church|bridge|cafe|restaurant|shop|train|bus|car)(?:[_-]|$)")
def is_background(tag):
    return bool(BACKGROUND_WORDS.search(tag))
# People-count tags (1girl, 2boys, multiple_girls, 6+others, solo, no_humans...): left out with include_count off, so the post doesn't change how
# many people your prompt has.
COUNT_TAGS = re.compile(r"(?:\d\+?(?:girl|boy|other)s?|multiple_(?:girls|boys|others)|solo|solo_focus|no_humans)")
def is_count(tag):
    return bool(COUNT_TAGS.fullmatch(tag))
# The kinds of tags a switch leaves out: include_<kind> off.
KINDS = {"appearance": is_appearance, "clothes": is_clothes, "background": is_background, "count": is_count}
USER_AGENT = "DiceForge/1.0" # Short: Danbooru's Cloudflare answers a longer one (with parentheses, a link or "ComfyUI") with a challenge page (403).


# The prompt's tags as Danbooru writes them: one per comma or line, weights and escapes taken off ("(long hair:1.2)" -> long_hair), lower case.
def prompt_tags(text):
    tags = []
    for part in re.split(r"[,\n]", text or ""):
        part = re.sub(r"<[^>]*>", "", part) # <lora:...> tags.
        part = re.sub(r":\s*-?\d+(?:\.\d+)?\s*\)?$", "", part.strip()) # (tag:1.2) weights.
        part = part.replace("\\(", "\u0001").replace("\\)", "\u0002").strip(" ()[]{}").replace("\u0001", "(").replace("\u0002", ")")
        key = tag_key(part)
        if key and key not in tags and not key.startswith(("embedding:", "__")):
            tags.append(key)
    return tags
# The tag as the models learned it: spaces for underscores (not in emoticons like ^_^), escaped parentheses (as the autocomplete writes it).
def prompt_text(tag):
    spaced = tag.replace("_", " ") if re.search(r"[a-z]{2}", tag, re.IGNORECASE) and len(tag) > 3 else tag
    return re.sub(r"([()])", r"\\\1", spaced)
# The exclude list as a test of a tag: its tags, and patterns with * for any text (*censor* leaves out bar_censor, censored, mosaic_censoring).
def excluded(exclude):
    tags = prompt_tags(exclude)
    exact = {tag for tag in tags if "*" not in tag}
    patterns = [re.compile(".*".join(re.escape(part) for part in tag.split("*"))) for tag in tags if "*" in tag]
    return lambda tag: tag in exact or any(pattern.fullmatch(tag) for pattern in patterns)
# The search: the two tags of the prompt that say the most (in the tag lists: characters, then series, then the rarest); without tag lists, the
# first two. Tags Danbooru doesn't know (masterpiece, score_9) are left out when the lists are there; when the lists know none of the prompt's
# tags (a new tag, or an incomplete list), its own first two still search: never an empty search, which would bring any post at all.
def search_tags(tags):
    index = INDEX.load()
    if not index.tags:
        return tags[:2]
    known = {tag_key(tag): (kind, count) for tag, kind, count, _aliases in index.tags}
    rank = {4: 0, 3: 1, 1: 2, 0: 3, 5: 4} # character, copyright, artist, general, meta
    found = sorted((tag for tag in tags if tag in known), key=lambda tag: (rank.get(known[tag][0], 3), known[tag][1]))
    return found[:2] or tags[:2]
# The searches to try: both tags, then each alone (a pair no post has together).
def searches(tags):
    return [tags] + ([[tag] for tag in tags] if len(tags) > 1 else [])
# The posts of post_ids: numbers or post links, separated by commas or spaces ("4926058, https://danbooru.donmai.us/posts/123").
def parse_post_ids(text):
    ids = []
    for part in re.split(r"[,\s]+", text or ""):
        found = re.search(r"posts/(\d+)", part) or re.fullmatch(r"#?(\d+)", part)
        if found and int(found.group(1)) not in ids:
            ids.append(int(found.group(1)))
    return ids


# The picture of a post for the node's preview: a small size Danbooru made (none for a post it hides from visitors).
def preview_url(post):
    asset = post.get("media_asset")
    variants = asset.get("variants") if isinstance(asset, dict) else None
    sized = {variant.get("type"): variant.get("url") for variant in variants or [] if isinstance(variant, dict)}
    url = sized.get("360x360") or sized.get("180x180") or post.get("preview_file_url")
    return url if isinstance(url, str) else ""
# A post as kept: its id, rating, score, preview and tags by group.
def post_summary(post):
    if not isinstance(post, dict) or not isinstance(post.get("id"), int):
        return None
    return {"id": post["id"], "rating": str(post.get("rating") or ""), "score": post.get("score") if isinstance(post.get("score"), int) else 0,
            "preview": preview_url(post), **{group: str(post.get(f"tag_string_{group}") or "").split() for group in GROUPS}}
def post_link(number):
    return f"{DANBOORU_URL.rstrip('/')}/posts/{number}"
# Danbooru busy: overloaded, limiting the requests, or its Cloudflare checking this computer. Asked again after a pause (RETRY_DELAYS seconds).
BUSY = {429, 500, 502, 503, 504}
RETRY_DELAYS = (1, 3)
class DanbooruBusy(Exception):
    pass
# A post from Danbooru (path: /posts/random.json with the search, or /posts/<id>.json), or None when there is none.
async def get_post(session, path, query=None):
    async with session.get(f"{DANBOORU_URL.rstrip('/')}{path}", params={"tags": query} if query is not None else None) as response:
        if response.status == 404:
            return None
        if response.status == 422:
            raise ValueError(f"Danbooru Tag Enhancer: Danbooru refused the search {query!r}: {(await response.text())[:200]}")
        if response.status in BUSY or (response.status == 403 and "challenge" in (await response.text())[:3000].lower()):
            text = (await response.text())[:3000].lower()
            raise DanbooruBusy(f"{response.status} {response.reason}" + (" (a Cloudflare check)" if "cloudflare" in text or "just a moment" in text else ""))
        response.raise_for_status()
        return post_summary(await response.json(content_type=None))
# Work with Danbooru (work(session)); busy: asked again after a pause, twice.
async def ask_danbooru(work):
    for attempt, delay in enumerate((*RETRY_DELAYS, None)):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers={"User-Agent": USER_AGENT}, trust_env=True) as session:
                return await work(session)
        except DanbooruBusy as busy:
            if delay is None:
                raise ValueError(f"Danbooru Tag Enhancer: Danbooru is busy and turned the request away ({busy}), {attempt + 1} times in a row. "
                                 "It does that for a while when it is overloaded or gets many requests: try again in a minute.") from None
            logging.warning(f"[DiceForge] Danbooru Tag Enhancer | Danbooru is busy ({busy}): asking again in {delay} s.")
            await asyncio.sleep(delay)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise ValueError(f"Danbooru Tag Enhancer: Danbooru can't be reached ({error}).") from None
    return None
# Random posts (count of them, different ones): both tags with the rating, else each tag alone; returns them and the search that found them.
async def find_posts(tags, rating_term, count=1):
    async def work(session):
        for search in searches(tags):
            query = " ".join([*search, rating_term]).strip()
            post = await get_post(session, "/posts/random.json", query)
            if post:
                found = {post["id"]: post}
                for _ in range(2 * (count - 1)): # Danbooru may pick a post twice; a search with fewer posts gives fewer.
                    if len(found) >= count:
                        break
                    more = await get_post(session, "/posts/random.json", query)
                    if more:
                        found.setdefault(more["id"], more)
                return list(found.values()), query
        return [], None
    return await ask_danbooru(work)
# The posts of the ids (fixed mode).
async def fetch_posts(ids):
    async def work(session):
        posts = []
        for number in ids:
            post = await get_post(session, f"/posts/{number}.json")
            if not post:
                raise ValueError(f"Danbooru Tag Enhancer: Danbooru has no post {number} (deleted, or hidden from visitors); fix post_ids or switch to random.")
            posts.append(post)
        return posts
    return await ask_danbooru(work)


# The tags of the posts to add: of the groups asked for, not in the prompt, not excluded, not of a kind switched off (left_out: the kinds' tests);
# the tags more of the posts have first, then the most used (by the tag lists); at most max_tags.
def added_tags(posts, groups, have, exclude, max_tags, left_out=()):
    index = INDEX.load()
    counts = {tag_key(tag): count for tag, _kind, count, _aliases in index.tags} if index.tags else {}
    shared = {} # tag: how many of the posts have it
    for post in posts:
        for tag in dict.fromkeys(tag for group in groups for tag in post.get(group, [])):
            if tag not in have and not exclude(tag) and not any(kind(tag) for kind in left_out):
                shared[tag] = shared.get(tag, 0) + 1
    tags = sorted(shared, key=lambda tag: (-shared[tag], -counts.get(tag, 0)))
    return tags[:max_tags] if max_tags else tags


class DanbooruTagEnhancer(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        include = lambda kind, default, tooltip: io.Boolean.Input(f"include_{kind}", default=default, tooltip=tooltip, advanced=True)
        return io.Schema(
            node_id="DiceForgeDanbooruEnhancer",
            display_name="Danbooru Tag Enhancer",
            category="DiceForge/conditioning",
            description="Adds tags to a prompt from random Danbooru posts that have its most telling tags: new posts on every run (random) or the same "
                        "ones again (fixed); the posts are shown on the node.",
            search_aliases=["danbooru", "tag enhancer", "prompt enhancer", "booru", "tags", "enhance prompt", "random post"],
            is_output_node=True, # Runs (and shows its posts) also with nothing connected.
            inputs=[
                io.String.Input("tags", multiline=True, default="1girl, hatsune miku",
                                tooltip="The tags to find posts with (or connect positive_text of CLIP Dual Text Encode). Wildcards and {a|b} choices are "
                                        "filled in (__characters__: a new character each run); weights, escapes and <lora:> tags are read through."),
                io.Combo.Input("rating", options=RATING_CHOICES, default="general", tooltip="The posts' ratings: general only (safe), with sensitive, up to questionable, or any."),
                io.Combo.Input("mode", options=["random", "fixed"], default="random",
                               tooltip="random: new posts (and wildcards) on every run, written into post_ids. fixed: the posts of post_ids again, with the "
                                       "same wildcards: switch to it to keep a run you like."),
                io.String.Input("post_ids", default="", tooltip="The posts of the last random run (filled in by the node). In fixed mode, the posts "
                                                                "used: ids or post links, separated by commas."),
                io.String.Input("prompt", optional=True, force_input=True,
                                tooltip="Optional: the rest of the prompt (quality tags, style: masterpiece, best quality...). It goes first in text, is never searched, and its tags are not added again."),
                io.Int.Input("posts", default=1, min=1, max=MAX_POSTS, advanced=True,
                             tooltip="Posts taken at once (random mode): their tags together, the ones more of them share first. Steadier than one post."),
                io.Int.Input("max_tags", default=15, min=0, max=200, tooltip="Tags added at most (the most used first); 0: all of the posts'.", advanced=True),
                include("general", True, "Add the posts' general tags (what is in the picture: pose, clothes, background...)."),
                include("appearance", True, "Add appearance tags (hair color and style, eyes, skin, body, ears, tail...). Off: your character keeps its own look."),
                include("clothes", True, "Add clothes and accessories (shirt, skirt, uniform, hair ornament, glasses, nude...). Off: your character keeps its own outfit."),
                include("background", True, "Add the scene (simple background, outdoors, classroom, night, on bed...). Off: your prompt keeps its own place."),
                include("count", True, "Add people-count tags (1girl, 2girls, 1boy, multiple_boys, solo, no_humans...). Off: the prompt keeps its own count."),
                include("character", False, "Add the posts' characters."),
                include("copyright", False, "Add the posts' series."),
                include("artist", False, "Add the posts' artists (artist styles)."),
                io.String.Input("exclude", multiline=True, default=DEFAULT_EXCLUDE, advanced=True,
                                tooltip="Tags never added, separated by commas; * is any text (*censor* leaves out bar_censor, censored, mosaic_censoring)."),
                io.Combo.Input("position", options=["after", "before"], default="after", tooltip="Where the added tags go: after the prompt's tags or before them.", advanced=True),
                io.Int.Input("wildcard_seed", default=0, min=0, max=0xFFFFFFFF, advanced=True,
                             tooltip="The seed of the wildcards in tags: a new one each random run (filled in by the node), this one in fixed mode."),
            ],
            outputs=[
                io.String.Output(display_name="text", tooltip="The prompt with the added tags: connect it to CLIP Dual Text Encode's positive (or a text encoder)."),
                io.String.Output(display_name="added_tags", tooltip="Only the added tags."),
                io.String.Output(display_name="post_url", tooltip="The Danbooru posts the tags came from, one link per line."),
                io.Int.Output(display_name="post_id", tooltip="The id of the first one."),
            ],
        )

    # Random: new posts on every run, like Danbooru's random post. Fixed: the same inputs give the same prompt (runs again when a wildcard file changes).
    @classmethod
    def fingerprint_inputs(cls, mode="random", **kwargs):
        return wildcards_signature() if mode == "fixed" else os.urandom(8).hex()

    @classmethod
    async def execute(cls, tags, rating="general", mode="random", post_ids="", prompt="", posts=1, max_tags=15, exclude=DEFAULT_EXCLUDE,
                      position="after", wildcard_seed=0, **include): # include: include_general, include_appearance... (the switches).
        wanted = lambda kind, default=True: include.get(f"include_{kind}", default)
        if rating not in RATING_TERMS:
            raise ValueError(f"Danbooru Tag Enhancer: unknown rating {rating!r} (one of {', '.join(RATING_CHOICES)}).")
        fixed = mode == "fixed"
        seed = wildcard_seed if fixed else random.randrange(0x100000000) # NOSONAR: picks wildcard lines, not security.
        loop = asyncio.get_running_loop()
        (tags,), _note = await loop.run_in_executor(None, fill_in, (tags or "",), seed, "random") # Wildcards, choices, comments.
        have = prompt_tags(tags)
        if fixed:
            ids = parse_post_ids(post_ids)
            if not ids:
                raise ValueError("Danbooru Tag Enhancer: fixed mode needs post_ids: run once in random mode (it fills them in), or type post ids or links.")
            found, query = await fetch_posts(ids), None
        else:
            searched = await loop.run_in_executor(None, search_tags, have)
            found, query = await find_posts(searched, RATING_TERMS[rating], max(1, min(MAX_POSTS, posts)))
            if not found:
                raise ValueError(f"Danbooru Tag Enhancer: no {rating} post on Danbooru has {' or '.join(searched) or 'any tags'}; try other tags or another rating.")
        groups = [group for group, default in (("character", False), ("copyright", False), ("artist", False), ("general", True)) if wanted(group, default)]
        left_out = [test for kind, test in KINDS.items() if not wanted(kind)]
        have_all = set(have) | set(prompt_tags(prompt)) # The prompt input's tags are not added again either.
        added = [prompt_text(tag) for tag in added_tags(found, groups, have_all, excluded(exclude), max_tags, left_out)]
        text, extra = tags.strip().rstrip(","), ", ".join(added)
        combined = ", ".join(part for part in ((extra, text) if position == "before" else (text, extra)) if part)
        combined = ", ".join(part for part in ((prompt or "").strip().rstrip(","), combined) if part) # The prompt input first.
        ids_text = ", ".join(str(post["id"]) for post in found)
        logging.info(f"[DiceForge] Danbooru Tag Enhancer | {query or mode} | posts {ids_text} | Added: {extra}")
        shown = {"text": combined, "tags": text, "added": extra, "search": query, "mode": mode, "post_ids": ids_text, "wildcard_seed": seed,
                 "posts": [{"id": post["id"], "url": post_link(post["id"]), "rating": post["rating"], "preview": post["preview"]} for post in found]}
        urls = "\n".join(post_link(post["id"]) for post in found)
        return io.NodeOutput(combined, extra, urls, found[0]["id"], ui={"dice_forge_danbooru": [shown]})


class DanbooruTagEnhancerExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [DanbooruTagEnhancer]
async def comfy_entrypoint():
    return DanbooruTagEnhancerExtension()
