import asyncio
import logging
import os
import random
import re
import time
import aiohttp
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from . import tag_autocomplete
from .clip_text_encode_pos_neg import fill_in, wildcards_signature
from .tag_autocomplete import INDEX, parse_tags, tag_key
# Danbooru Tag Enhancer: more tags for a prompt, from real posts that have the tags already there, on Danbooru (anime) or e621 (furry). The site
# picks random posts with the most telling two of the prompt's tags (the rarest it knows: a character before "1girl") and the rating; their tags
# that the prompt lacks are added, the most used first. Random mode: new posts on every run, written into post_ids; fixed mode: those posts again
# (as a seed's fixed). A Danbooru search without an account may have two tags (rating: is free); with none found for both, each one alone.
DANBOORU_URL = os.environ.get("DICEFORGE_DANBOORU_URL", "https://danbooru.donmai.us")
E621_URL = os.environ.get("DICEFORGE_E621_URL", "https://e621.net")
# The ratings to search, as Danbooru's letters, from safe on: general, sensitive (suggestive), questionable (nudity), explicit. One, or several.
RATINGS = {"general": "g", "sensitive": "s", "questionable": "q", "explicit": "e", "general + sensitive": "gs", "sensitive + questionable": "sq",
           "questionable + explicit": "qe", "up to questionable": "gsq", "sensitive and up": "sqe", "any": "gsqe"}
RATING_CHOICES = list(RATINGS)
DEFAULT_EXCLUDE = "signature, watermark, artist_name, *username, web_address, dated, speech_bubble, comic, *_text, text_focus, *censor*"
GROUPS = ("general", "species", "character", "copyright", "artist", "meta")
MAX_POSTS = 5
# Appearance tags (how the character looks: hair, eyes, skin, body, ears, tails...): left out with include_appearance off, so the post adds the
# pose, clothes and scene but your character keeps its own look. A tag is one when a word of it is one of these, or it is one of the tags below.
APPEARANCE_WORDS = re.compile(r"(?:^|_)(?:hair|haired|eyes?|pupils|sclera|eyelashes|eyebrows|skin|skinned|ears?|tail|tails|horns?|wings?|breasts?|bangs|sidelocks|"
                              r"ahoge|twintails|ponytail|braids?|bun|buns|drills|halo|freckles|mole|fangs?|abs|muscular|petite|curvy|plump|tall|height|"
                              r"fur|furred|scales|scaled|feathers|feathered|markings|countershading|muzzle|snout|claws|pawpads|tuft|mane|beak|whiskers|"
                              r"hooves)(?:_|$)")
APPEARANCE_TAGS = {"heterochromia", "flat_chest", "bob_cut", "hime_cut", "eyeliner", "makeup", "lipstick", "elf", "dark-skinned_female", "dark-skinned_male",
                   "tan", "tanlines", "pale_skin", "colored_skin", "mature_female", "loli", "shota", "kemonomimi_mode", "anthro", "feral", "humanoid", "taur"}
# e621's body colors (red_body, two_tone_fur...), not the framing (upper_body).
BODY_COLORS = ("_body", "_fur", "_scales", "_feathers")
FRAMING = {"upper_body", "lower_body", "full_body", "half_body"}
# Not the look itself: accessories and what is done with the hair or ears (hair_ornament, hair_ribbon, hand_in_hair, adjusting_hair...).
NOT_APPEARANCE = re.compile(r"ornament|ribbon|bow|clip|band|flower|scrunchie|pin|bobbles|tubes|tie|hand|holding|grab|adjusting|blowing|covering|pull|ring")
def is_appearance(tag):
    if tag in APPEARANCE_TAGS or (tag.endswith(BODY_COLORS) and tag not in FRAMING):
        return True
    return bool(APPEARANCE_WORDS.search(tag)) and not NOT_APPEARANCE.search(tag)
# Clothes and accessories (shirt, pleated_skirt, school_uniform, hair_ornament, glasses...), also how much is worn (nude, barefoot): left out with
# include_clothes off, so your character keeps its own outfit. A tag is one when a word of it (between _ or -) is one of these.
CLOTHES_WORDS = re.compile(r"(?:^|[_-])(?:shirt|blouse|skirt|miniskirt|dress|sundress|gown|jacket|coat|cardigan|hoodie|sweater|vest|cape|capelet|cloak|robe|"
                           r"pants|trousers|jeans|shorts|leggings|thighhighs|kneehighs|socks|pantyhose|stockings|legwear|footwear|shoes|boots|sandals|heels|"
                           r"sneakers|loafers|slippers|gloves|mittens|hat|cap|beret|helmet|headwear|headband|headset|headphones|hood|hairband|hairclip|"
                           r"ornament|ribbon|bow|bowtie|necktie|tie|neckerchief|scarf|choker|collar|sleeves|sleeveless|strapless|belt|suit|tuxedo|armor|"
                           r"uniform|serafuku|kimono|yukata|hakama|bikini|swimsuit|leotard|bodysuit|apron|bra|panties|underwear|lingerie|garter|garters|"
                           r"earrings|necklace|jewelry|bracelet|glasses|eyewear|sunglasses|mask|crown|tiara|veil|clothes|clothing|outfit|costume|frills|"
                           r"frilled|buttons|zipper|lace|camisole|tank_top|crop_top|tube_top|cutout|off_shoulder|off-shoulder|bare_shoulders|nude|naked|"
                           r"topless|bottomless|barefoot|no_bra|no_panties|topwear|bottomwear|handwear|armwear|neckwear|swimwear|nightwear|clothed)(?:[_-]|$)")
def is_clothes(tag):
    return bool(CLOTHES_WORDS.search(tag))
# The scene (simple_background, outdoors, classroom, night, cherry_blossoms, on_bed...): left out with include_background off, so your prompt keeps
# its own place. A tag is one when a word of it is one of these.
BACKGROUND_WORDS = re.compile(r"(?:^|[_-])(?:background|outdoors|indoors|outside|inside|scenery|landscape|sky|cloud|clouds|cloudy|day|night|sunset|sunrise|evening|"
                              r"twilight|dusk|dawn|tree|trees|grass|forest|field|ocean|sea|beach|shore|water|waterfall|lake|river|pool|underwater|city|"
                              r"cityscape|town|street|road|alley|building|buildings|skyscraper|architecture|room|bedroom|classroom|bathroom|kitchen|library|"
                              r"office|hallway|window|curtains|wall|floor|ceiling|door|stairs|fence|railing|park|garden|mountain|mountains|hill|horizon|moon|"
                              r"sunlight|moonlight|light_rays|sunbeam|rain|snow|snowing|leaves|petals|cherry_blossoms|bed|couch|sofa|chair|table|desk|"
                              r"lamp|stage|school|shrine|temple|church|bridge|cafe|restaurant|shop|train|bus|car)(?:[_-]|$)")
def is_background(tag):
    return bool(BACKGROUND_WORDS.search(tag))
# People-count tags (1girl, 2boys, multiple_girls, 6+others, solo, no_humans; e621's duo, trio, group...): left out with include_count off, so the post doesn't change how
# many people your prompt has.
COUNT_TAGS = re.compile(r"(?:\d\+?(?:girl|boy|other)s?|multiple_(?:girls|boys|others)|solo|solo_focus|no_humans|duo|trio|group|zero_pictured)")
def is_count(tag):
    return bool(COUNT_TAGS.fullmatch(tag))
# The kinds of tags a switch leaves out: include_<kind> off.
KINDS = {"appearance": is_appearance, "clothes": is_clothes, "background": is_background, "count": is_count}
USER_AGENT = "DiceForge/1.0" # Short: Danbooru's Cloudflare answers a longer one (with parentheses, a link or "ComfyUI") with a challenge page (403).
# e621 too takes it (it asks for a name of the program, without which it refuses).


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
# A site's own tag list (danbooru.csv, e621.csv) when downloaded, else all the lists together: {tag: (kind, count)}. Read again when the file changes.
_site_lists = {}
def site_tags(name):
    path = os.path.join(tag_autocomplete.TAGS_FOLDER, f"{name}.csv")
    try:
        stamp = (os.path.getmtime(path), os.path.getsize(path))
    except OSError:
        return {tag_key(tag): (kind, count) for tag, kind, count, _aliases in INDEX.load().tags}
    if _site_lists.get(path, (None,))[0] != stamp:
        with open(path, encoding="utf-8", errors="replace") as file:
            _site_lists[path] = (stamp, {tag_key(tag): (kind, count) for tag, kind, count, _aliases in parse_tags(file.read())})
    return _site_lists[path][1]
# The search: the two tags of the prompt that say the most (in the site's tag list: characters, then series, then the rarest); without tag lists,
# the first two. Tags the site doesn't know (masterpiece, score_9) are left out when the lists are there; when the lists know none of the prompt's
# tags (a new tag, or an incomplete list), its own first two still search: never an empty search, which would bring any post at all.
def search_tags(tags, site=None, known=None):
    site = site or SITES["danbooru"]
    known = site_tags(site.key) if known is None else known
    if not known:
        return tags[:2]
    found = sorted((tag for tag in tags if tag in known), key=lambda tag: (site.ranks.get(known[tag][0], site.ranks[0]), known[tag][1]))
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


# The picture of a Danbooru post for the node's preview: a small size Danbooru made (none for a post it hides from visitors).
def preview_url(post):
    asset = post.get("media_asset")
    variants = asset.get("variants") if isinstance(asset, dict) else None
    sized = {variant["type"]: variant.get("url") for variant in variants if isinstance(variant, dict) and isinstance(variant.get("type"), str)} \
        if isinstance(variants, list) else {}
    url = sized.get("360x360") or sized.get("180x180") or post.get("preview_file_url")
    return url if isinstance(url, str) else ""
# Busy: overloaded, limiting the requests, or its Cloudflare checking this computer. Asked again after a pause (RETRY_DELAYS seconds).
BUSY = {429, 500, 502, 503, 504}
RETRY_DELAYS = (1, 3)
class DanbooruBusy(Exception):
    pass
# A post's id: a whole number above 0 (not true, a text or a fraction).
def post_number(post):
    number = post.get("id") if isinstance(post, dict) else None
    return number if isinstance(number, int) and not isinstance(number, bool) and number > 0 else None
def text_of(value):
    return value if isinstance(value, str) else ""


# A site to take posts from. A post is kept as: id, rating (the site's letter), rating_name, safe (not blurred), score, preview, and its tags by
# group (GROUPS; species only on e621).
class Site:
    name = key = safe = ""
    pause = 0.0 # Seconds between requests (e621 asks for at most two a second).
    ranks = {} # Tag kinds of the site's tag list by how much they say: the search takes the lowest first; 0 is general.
    names = {}

    def __init__(self):
        self.last = 0.0

    def base(self):
        raise NotImplementedError

    def link(self, number):
        return f"{self.base().rstrip('/')}/posts/{number}"

    # The site's JSON for a path, None for 404.
    async def get(self, session, path, params=None, query=None):
        wait = self.last + self.pause - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self.last = time.monotonic()
        async with session.get(f"{self.base().rstrip('/')}{path}", params=params) as response:
            if response.status == 404:
                return None
            if response.status == 422:
                raise ValueError(f"Danbooru Tag Enhancer: {self.name} refused the search {query!r}: {(await response.text())[:200]}")
            if response.status in BUSY or (response.status == 403 and "challenge" in (await response.text())[:3000].lower()):
                text = (await response.text())[:3000].lower()
                raise DanbooruBusy(f"{response.status} {response.reason}" + (" (a Cloudflare check)" if "cloudflare" in text or "just a moment" in text else ""))
            response.raise_for_status()
            try:
                return await response.json(content_type=None)
            except ValueError: # A page instead of data, or a cut-off answer: asked again like a busy site.
                raise DanbooruBusy(f"{response.status}, an answer that isn't JSON") from None

    def kept(self, post, rating, preview, score, tags):
        return {"id": post["id"], "rating": rating, "rating_name": self.names.get(rating, rating), "safe": rating == self.safe, "preview": preview,
                "score": score if isinstance(score, int) else 0, **{group: tags.get(group, []) for group in GROUPS}}


class Danbooru(Site):
    name, key, safe = "Danbooru", "danbooru", "g"
    ranks = {4: 0, 3: 1, 1: 2, 0: 3, 5: 4} # character, copyright, artist, general, meta
    names = {"g": "general", "s": "sensitive", "q": "questionable", "e": "explicit"}

    def base(self):
        return DANBOORU_URL

    def rating_term(self, letters): # rating:g,s is general or sensitive.
        return "" if len(letters) == 4 else "rating:" + ",".join(letters)

    def summary(self, post):
        if not post_number(post):
            return None
        tags = {group: text.split() if isinstance(text := post.get(f"tag_string_{group}"), str) else [] for group in GROUPS}
        return self.kept(post, text_of(post.get("rating")), preview_url(post), post.get("score"), tags)

    # Random posts (count of them, different ones): Danbooru picks one a request; it may pick a post twice, and a search with fewer posts gives fewer.
    async def random_posts(self, session, query, count):
        found = {}
        for _ in range(2 * count - 1):
            post = self.summary(await self.get(session, "/posts/random.json", {"tags": query}, query))
            if not post:
                break
            found.setdefault(post["id"], post)
            if len(found) >= count:
                break
        return list(found.values())

    async def post(self, session, number):
        return self.summary(await self.get(session, f"/posts/{number}.json"))


class E621(Site):
    name, key, safe = "e621", "e621", "s"
    pause = 0.5
    ranks = {4: 0, 3: 1, 5: 2, 1: 3, 0: 4, 7: 5} # character, copyright, species, artist, general, meta
    names = {"s": "safe", "q": "questionable", "e": "explicit"}

    def base(self):
        return E621_URL

    # e621 has three ratings: safe (Danbooru's general and sensitive), questionable, explicit. Two of them: the third one left out.
    def rating_term(self, letters):
        wanted = {"s" if letter in "gs" else letter for letter in letters}
        if len(wanted) == 3:
            return ""
        if len(wanted) == 1:
            return f"rating:{wanted.pop()}"
        return " ".join(f"-rating:{rating}" for rating in "sqe" if rating not in wanted)

    def summary(self, post):
        if not post_number(post):
            return None
        groups = post.get("tags") if isinstance(post.get("tags"), dict) else {}
        tags = {group: [tag for tag in groups[group] if isinstance(tag, str)] if isinstance(groups.get(group), list) else [] for group in GROUPS}
        preview = post.get("preview") if isinstance(post.get("preview"), dict) else {}
        score = post.get("score") if isinstance(post.get("score"), dict) else {}
        return self.kept(post, text_of(post.get("rating")), preview.get("url") if isinstance(preview.get("url"), str) else "", score.get("total"), tags)

    # The posts of a /posts.json answer.
    def listed(self, data):
        posts = data.get("posts") if isinstance(data, dict) else None
        return [post for post in map(self.summary, posts if isinstance(posts, list) else []) if post]

    # Random posts in one request (order:random; e621 allows more tags than Danbooru).
    async def random_posts(self, session, query, count):
        return self.listed(await self.get(session, "/posts.json", {"tags": f"{query} order:random".strip(), "limit": count}, query))

    async def post(self, session, number):
        data = await self.get(session, f"/posts/{number}.json")
        return self.summary(data.get("post") if isinstance(data, dict) else None)


SITES = {"danbooru": Danbooru(), "e621": E621()}


# Work with the site (work(session)); busy: asked again after a pause, twice.
async def ask(site, work):
    for attempt, delay in enumerate((*RETRY_DELAYS, None)):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers={"User-Agent": USER_AGENT}, trust_env=True) as session:
                return await work(session)
        except DanbooruBusy as busy:
            if delay is None:
                raise ValueError(f"Danbooru Tag Enhancer: {site.name} is busy and turned the request away ({busy}), {attempt + 1} times in a row. "
                                 "It does that for a while when it is overloaded or gets many requests: try again in a minute.") from None
            logging.warning(f"[DiceForge] Danbooru Tag Enhancer | {site.name} is busy ({busy}): asking again in {delay} s.")
            await asyncio.sleep(delay)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise ValueError(f"Danbooru Tag Enhancer: {site.name} can't be reached ({error}).") from None
    return None
# Random posts: both tags with the rating, else each tag alone; returns them and the search that found them.
async def find_posts(site, tags, rating_term, count=1):
    async def work(session):
        for search in searches(tags):
            query = " ".join([*search, rating_term]).strip()
            posts = await site.random_posts(session, query, count)
            if posts:
                return posts, query
        return [], None
    return await ask(site, work)
# The posts of the ids (fixed mode).
async def fetch_posts(site, ids):
    async def work(session):
        posts = []
        for number in ids:
            post = await site.post(session, number)
            if not post:
                raise ValueError(f"Danbooru Tag Enhancer: {site.name} has no post {number} (deleted, or hidden from visitors); fix post_ids or switch to random.")
            posts.append(post)
        return posts
    return await ask(site, work)


# The tags of the posts to add: of the groups asked for, not in the prompt, not excluded, not of a kind switched off (left_out: the kinds' tests);
# the tags more of the posts have first, then the most used (known: the site's tag list); at most max_tags.
def added_tags(posts, groups, have, exclude, max_tags, left_out=(), known=None):
    known = known or {}
    shared = {} # tag: how many of the posts have it
    for post in posts:
        for tag in dict.fromkeys(tag for group in groups for tag in post.get(group, [])):
            if tag not in have and not exclude(tag) and not any(kind(tag) for kind in left_out):
                shared[tag] = shared.get(tag, 0) + 1
    tags = sorted(shared, key=lambda tag: (-shared[tag], -known.get(tag, (0, 0))[1]))
    return tags[:max_tags] if max_tags else tags


class DanbooruTagEnhancer(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        include = lambda kind, default, tooltip: io.Boolean.Input(f"include_{kind}", default=default, tooltip=tooltip, advanced=True)
        return io.Schema(
            node_id="DiceForgeDanbooruEnhancer",
            display_name="Danbooru Tag Enhancer",
            category="DiceForge/conditioning",
            description="Adds tags to a prompt from random Danbooru or e621 posts that have its most telling tags: new posts on every run (random) or "
                        "the same ones again (fixed); the posts are shown on the node.",
            search_aliases=["danbooru", "e621", "tag enhancer", "prompt enhancer", "booru", "tags", "enhance prompt", "random post"],
            is_output_node=True, # Runs (and shows its posts) also with nothing connected.
            inputs=[
                io.String.Input("tags", multiline=True, default="1girl, hatsune miku",
                                tooltip="The tags to find posts with (or connect positive_text of CLIP Dual Text Encode). Wildcards and {a|b} choices are "
                                        "filled in (__characters__: a new character each run); weights, escapes and <lora:> tags are read through."),
                io.Combo.Input("source", options=list(SITES), default="danbooru",
                               tooltip="Where the posts come from: Danbooru (anime: Illustrious, NoobAI, Anima, Pony) or e621 (furry: NoobAI, Pony). "
                                       "Each has its own tags: the tag list of the site (Tag autocomplete) helps the search."),
                io.Combo.Input("rating", options=RATING_CHOICES, default="general",
                               tooltip="The posts' ratings, from safe on: general, sensitive (suggestive), questionable (nudity), explicit; one, two "
                                       "next to each other, up to questionable, sensitive and up, or any. e621 has safe (general and sensitive), "
                                       "questionable and explicit."),
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
    async def execute(cls, tags, source="danbooru", rating="general", mode="random", post_ids="", prompt="", posts=1, max_tags=15, exclude=DEFAULT_EXCLUDE,
                      position="after", wildcard_seed=0, **include): # include: include_general, include_appearance... (the switches).
        wanted = lambda kind, default=True: include.get(f"include_{kind}", default)
        site = SITES.get(source)
        if site is None:
            raise ValueError(f"Danbooru Tag Enhancer: unknown source {source!r} (one of {', '.join(SITES)}).")
        if rating not in RATINGS:
            raise ValueError(f"Danbooru Tag Enhancer: unknown rating {rating!r} (one of {', '.join(RATING_CHOICES)}).")
        fixed = mode == "fixed"
        seed = wildcard_seed if fixed else random.randrange(0x100000000) # NOSONAR: picks wildcard lines, not security.
        loop = asyncio.get_running_loop()
        (tags,), _note = await loop.run_in_executor(None, fill_in, (tags or "",), seed, "random") # Wildcards, choices, comments.
        have = prompt_tags(tags)
        known = await loop.run_in_executor(None, site_tags, site.key)
        if fixed:
            ids = parse_post_ids(post_ids)
            if not ids:
                raise ValueError("Danbooru Tag Enhancer: fixed mode needs post_ids: run once in random mode (it fills them in), or type post ids or links.")
            found, query = await fetch_posts(site, ids), None
        else:
            searched = search_tags(have, site, known)
            found, query = await find_posts(site, searched, site.rating_term(RATINGS[rating]), max(1, min(MAX_POSTS, posts)))
            if not found:
                raise ValueError(f"Danbooru Tag Enhancer: no {rating} post on {site.name} has {' or '.join(searched) or 'any tags'}; try other tags or another rating.")
        groups = [group for group, default in (("character", False), ("copyright", False), ("artist", False), ("general", True)) if wanted(group, default)]
        groups += ["species"] if wanted("general") else [] # e621's species (fox, canine, mammal) go with the general tags.
        left_out = [test for kind, test in KINDS.items() if not wanted(kind)]
        if not wanted("appearance"): # The species are a look too.
            left_out.append({tag for post in found for tag in post["species"]}.__contains__)
        have_all = set(have) | set(prompt_tags(prompt)) # The prompt input's tags are not added again either.
        added = [prompt_text(tag) for tag in added_tags(found, groups, have_all, excluded(exclude), max_tags, left_out, known)]
        text, extra = tags.strip().rstrip(","), ", ".join(added)
        combined = ", ".join(part for part in ((extra, text) if position == "before" else (text, extra)) if part)
        combined = ", ".join(part for part in ((prompt or "").strip().rstrip(","), combined) if part) # The prompt input first.
        ids_text = ", ".join(str(post["id"]) for post in found)
        logging.info(f"[DiceForge] Danbooru Tag Enhancer | {site.name} | {query or mode} | posts {ids_text} | Added: {extra}")
        shown = {"text": combined, "tags": text, "added": extra, "site": site.key, "search": query, "mode": mode, "post_ids": ids_text, "wildcard_seed": seed,
                 "posts": [{"id": post["id"], "url": site.link(post["id"]), "rating": post["rating"], "rating_name": post["rating_name"], "safe": post["safe"],
                            "preview": post["preview"]} for post in found]}
        urls = "\n".join(site.link(post["id"]) for post in found)
        return io.NodeOutput(combined, extra, urls, found[0]["id"], ui={"dice_forge_danbooru": [shown]})


class DanbooruTagEnhancerExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [DanbooruTagEnhancer]
async def comfy_entrypoint():
    return DanbooruTagEnhancerExtension()
