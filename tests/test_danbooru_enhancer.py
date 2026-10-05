# Danbooru Tag Enhancer (DiceForge/danbooru_enhancer.py): the prompt's tags read through weights and escapes, the search tags, Danbooru's random
# post, the tags added, the fixed mode, wildcards, e621, and a stand-in for Danbooru and e621 (no test goes online).
import asyncio
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import pytest
from hypothesis import given, settings, strategies as st
from DiceForge import danbooru_enhancer, tag_autocomplete
from DiceForge.danbooru_enhancer import (GROUPS, SITES, DanbooruTagEnhancer, added_tags, excluded, is_appearance, is_background, is_clothes, is_count, parse_post_ids, preview_url,
                                         prompt_tags, prompt_text, search_tags, searches)

TAGS = "1girl,0,6000000,\nhatsune_miku,4,90000,miku\nvocaloid,3,200000,\nsmile,0,4000000,\nlong_hair,0,5000000,\ntwintails,0,900000,\nsignature,0,800000,\nthighhighs,0,700000,\n"


def post(number, rating, general, character="hatsune_miku"):
    return {"id": number, "rating": rating, "score": 100 - number, "tag_string_general": general, "tag_string_character": character,
            "tag_string_copyright": "vocaloid", "tag_string_artist": "someone", "tag_string_meta": "highres", "preview_file_url": f"https://cdn/{number}.jpg"}


POSTS = [post(1, "g", "1girl smile twintails long_hair signature"), post(2, "g", "1girl twintails thighhighs"), post(3, "e", "1girl nude"),
         post(4, "s", "1girl smile skirt")]


def e621_post(number, rating, general, species=("fox", "canine")):
    return {"id": number, "rating": rating, "score": {"total": 10}, "preview": {"url": f"https://static/{number}.jpg"},
            "tags": {"general": general.split(), "species": list(species), "character": [], "copyright": [], "artist": ["someone"], "meta": ["hi_res"]}}


E621_POSTS = [e621_post(11, "s", "solo anthro smile red_body shirt"), e621_post(12, "e", "duo anthro nude")]


# e621's search: tags, rating:x, -rating:x (order:random taken as asked).
def e621_found(tags):
    def fits(item, term):
        if term.startswith("-rating:"):
            return item["rating"] != term[len("-rating:"):]
        if term.startswith("rating:"):
            return item["rating"] == term[len("rating:"):]
        return term == "order:random" or any(term in group for group in item["tags"].values())
    return [item for item in E621_POSTS if all(fits(item, term) for term in tags.split())]


SAFEBOORU_POSTS = [{"id": 21, "rating": "safe", "score": 7, "directory": "4567", "image": "abc.png", "hash": "abc",
                    "tags": "1girl hatsune_miku vocaloid smile jack-o&#039;-lantern"},
                   {"id": 22, "rating": "questionable", "score": 3, "directory": "4568", "image": "def.jpg", "hash": "def", "tags": "1girl hatsune_miku swimsuit"}]


# Safebooru's search: tags, rating:x, -rating:x.
def safebooru_found(tags):
    def fits(item, term):
        if term.startswith("-rating:"):
            return item["rating"] != term[len("-rating:"):]
        if term.startswith("rating:"):
            return item["rating"] == term[len("rating:"):]
        return term in item["tags"].split()
    return [item for item in SAFEBOORU_POSTS if all(fits(item, term) for term in tags.split())]


def found(tags):
    wanted = [tag for tag in tags.split() if not tag.startswith("rating:")]
    ratings = next((tag[len("rating:"):].split(",") for tag in tags.split() if tag.startswith("rating:")), None)
    return [item for item in POSTS if (ratings is None or item["rating"] in ratings) and all(
        tag in " ".join(item[f"tag_string_{group}"] for group in ("general", "character", "copyright")).split() for tag in wanted)]


@pytest.fixture
def danbooru(monkeypatch):
    """The stand-in of /posts/random.json: a post of the search (server.choose picks it: the first by default), 404 when none has the tags, 422 past
    two tags (rating: isn't counted) or when told to refuse; and of /posts/<id>.json. Under /e621, e621's /posts.json and /posts/<id>.json.
    Requests are recorded (the search, or the path)."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            tags = parse_qs(url.query).get("tags", [""])[0]
            query = parse_qs(url.query)
            self.server.requests.append(tags if url.path in ("/posts/random.json", "/e621/posts.json") else
                                        f"safebooru {query.get('id', [tags])[0]} {query.get('pid', ['-'])[0]}" if url.path == "/safebooru/index.php" else url.path)
            posts = found(tags)
            by_id = next((item for item in POSTS if url.path == f"/posts/{item['id']}.json"), None)
            if self.server.busy > 0: # Danbooru overloaded: 503 this many times.
                self.server.busy -= 1
                status, body = 503, {"message": "Service Unavailable"}
            elif self.server.garbage > 0: # A page instead of data (200), this many times.
                self.server.garbage -= 1
                status, body = 200, "<html><body>Down for maintenance</body></html>"
            elif url.path == "/safebooru/index.php" and "id" in query:
                posts = [item for item in SAFEBOORU_POSTS if str(item["id"]) == query["id"][0]]
                status, body = 200, posts or "" # Nothing found: an empty answer.
            elif url.path == "/safebooru/index.php" and query.get("json") != ["1"]: # XML: how many posts the search has.
                status, body = 200, f'<?xml version="1.0" encoding="UTF-8"?><posts count="{len(safebooru_found(tags))}" offset="0"></posts>'
            elif url.path == "/safebooru/index.php":
                place = int(query.get("pid", ["0"])[0])
                status, body = 200, safebooru_found(tags)[place:place + int(query.get("limit", ["100"])[0])] or ""
            elif url.path == "/e621/posts.json":
                status, body = 200, {"posts": e621_found(tags)[:int(parse_qs(url.query).get("limit", ["1"])[0])]}
            elif url.path.startswith("/e621/posts/"):
                item = next((item for item in E621_POSTS if url.path == f"/e621/posts/{item['id']}.json"), None)
                status, body = (200, {"post": item}) if item else (404, {"success": False, "reason": "not found"})
            elif by_id:
                status, body = 200, by_id
            elif url.path != "/posts/random.json":
                status, body = 404, {"message": "Not found"}
            elif self.server.refuse or len([tag for tag in tags.split() if not tag.startswith("rating:")]) > 2:
                status, body = 422, {"message": "You cannot search for more than 2 tags at a time."}
            elif not posts:
                status, body = 404, {"message": "That record was not found."}
            else:
                status, body = 200, self.server.choose(posts)
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests, server.refuse, server.choose, server.busy, server.garbage = [], False, lambda posts: posts[0], 0, 0
    monkeypatch.setattr(danbooru_enhancer, "RETRY_DELAYS", (0, 0)) # No waiting in the tests.
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(danbooru_enhancer, "DANBOORU_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(danbooru_enhancer, "E621_URL", f"http://127.0.0.1:{server.server_port}/e621")
    monkeypatch.setattr(danbooru_enhancer, "SAFEBOORU_URL", f"http://127.0.0.1:{server.server_port}/safebooru")
    monkeypatch.setattr(SITES["safebooru"], "pause", 0)
    monkeypatch.setattr(SITES["e621"], "pause", 0)
    yield server
    server.shutdown()


def tag_list():
    os.makedirs(tag_autocomplete.TAGS_FOLDER, exist_ok=True)
    with open(os.path.join(tag_autocomplete.TAGS_FOLDER, "danbooru.csv"), "w", encoding="utf-8") as file:
        file.write(TAGS)


def execute(tags="1girl, hatsune miku, masterpiece", **inputs):
    return asyncio.run(DanbooruTagEnhancer.execute(tags, **inputs))


def run(tags="1girl, hatsune miku, masterpiece", **inputs):
    return execute(tags, **inputs).result


def test_prompt_tags_read_through_the_prompt_syntax():
    assert prompt_tags("1girl, (long hair:1.2), hatsune miku \\(cosplay\\), <lora:x:1>, embedding:bad, __color__\nsmile, , 1girl") == \
        ["1girl", "long_hair", "hatsune_miku_(cosplay)", "smile"]
    assert prompt_text("hatsune_miku_(cosplay)") == "hatsune miku \\(cosplay\\)" and prompt_text("^_^") == "^_^"


def test_search_tags_are_the_two_most_telling():
    assert search_tags(["1girl", "masterpiece", "hatsune_miku"]) == ["1girl", "masterpiece"] # No lists: the first two.
    tag_list()
    assert search_tags(["1girl", "masterpiece", "smile", "hatsune_miku"]) == ["hatsune_miku", "smile"] # The character, then the rarer general tag.
    assert search_tags(["blue_archive", "masterpiece"]) == ["blue_archive", "masterpiece"] # None known to the lists: the prompt's own, not an empty search.
    assert searches(["a", "b"]) == [["a", "b"], ["a"], ["b"]] and searches(["a"]) == [["a"]] and searches([]) == [[]]


def test_adds_the_tags_of_a_random_post(danbooru):
    tag_list()
    output = execute(tags="1girl, hatsune miku, masterpiece")
    text, added, url, number = output.result
    assert danbooru.requests == ["hatsune_miku 1girl rating:g"] # Two tags (masterpiece isn't a Danbooru tag), the rating free.
    assert number == 1 and url.endswith("/posts/1")
    assert added == "long hair, smile, twintails" # The most used first; 1girl is there already, signature excluded.
    assert text == "1girl, hatsune miku, masterpiece, long hair, smile, twintails"
    shown = output.ui["dice_forge_danbooru"][0]
    assert {key: shown[key] for key in ("text", "tags", "added", "search", "mode", "post_ids")} == {
        "text": text, "tags": "1girl, hatsune miku, masterpiece", "added": added, "search": "hatsune_miku 1girl rating:g", "mode": "random", "post_ids": "1"}
    assert shown["posts"] == [{"id": 1, "url": url, "rating": "g", "rating_name": "general", "safe": True, "preview": "https://cdn/1.jpg"}]
    assert shown["site"] == "danbooru" and isinstance(shown["wildcard_seed"], int)


def test_a_new_post_on_every_run(danbooru):
    first = DanbooruTagEnhancer.fingerprint_inputs(tags="x", mode="random")
    assert DanbooruTagEnhancer.fingerprint_inputs(tags="x", mode="random") != first # Never from the cache.
    fixed = [DanbooruTagEnhancer.fingerprint_inputs(tags="x", mode="fixed") for _ in range(2)]
    assert fixed[0] == fixed[1] # Fixed: the same each time, so from the cache.
    danbooru.choose = lambda posts: posts[-1]
    assert run(tags="hatsune miku", rating="general + sensitive")[3] == 4
    assert run(tags="hatsune miku", rating="general")[3] == 2
    assert danbooru.requests == ["hatsune_miku rating:g,s", "hatsune_miku rating:g"] # Asked each time.


def test_ratings(danbooru):
    assert run(tags="hatsune miku", rating="explicit")[3] == 3
    assert run(tags="hatsune miku", rating="sensitive")[3] == 4
    assert run(tags="hatsune miku", rating="questionable + explicit")[3] == 3
    danbooru.choose = lambda posts: posts[-1]
    assert run(tags="hatsune miku", rating="sensitive and up")[3] == 4
    assert danbooru.requests == ["hatsune_miku rating:e", "hatsune_miku rating:s", "hatsune_miku rating:q,e", "hatsune_miku rating:s,q,e"]
    with pytest.raises(ValueError, match="no questionable post on Danbooru has hatsune_miku"):
        run(tags="hatsune miku", rating="questionable")


def test_options(danbooru):
    tag_list()
    text, added, _url, number = run(max_tags=2, include_character=True, include_copyright=True, position="before", rating="any")
    assert number == 1 and added == "long hair, smile" and text == "long hair, smile, 1girl, hatsune miku, masterpiece" # The most used first.
    assert danbooru.requests[-1] == "hatsune_miku 1girl" # Any: no rating term.
    danbooru.choose = lambda posts: next(post for post in posts if post["id"] == 3)
    assert run(rating="any", max_tags=0)[1] == "nude"
    assert "vocaloid" in run(rating="any", include_general=False, include_copyright=True)[1]


def test_appearance_tags():
    for tag in ("long_hair", "blue_eyes", "twintails", "cone_hair_bun", "yellow_pupils", "dark_skin", "large_breasts", "animal_ears", "cat_tail", "ahoge",
                "heterochromia", "hair_between_eyes", "elf", "red_body", "two_tone_fur", "anthro", "white_countershading", "muzzle"):
        assert is_appearance(tag), tag
    for tag in ("smile", "1girl", "shirt", "hair_ornament", "hair_ribbon", "hand_in_hair", "earrings", "blush", "thighhighs", "hairclip", "outdoors", "upper_body", "full_body"):
        assert not is_appearance(tag), tag


def test_without_appearance_the_post_adds_the_rest(danbooru):
    tag_list()
    assert run(include_appearance=False)[1] == "smile" # Not long hair nor twintails: the character keeps its own look.
    assert run(include_appearance=True)[1] == "long hair, smile, twintails"


def test_count_tags():
    for tag in ("1girl", "2girls", "6+girls", "multiple_girls", "1boy", "3boys", "multiple_boys", "1other", "multiple_others", "solo", "solo_focus", "no_humans", "duo", "trio", "group"):
        assert is_count(tag), tag
    for tag in ("girl", "boy_on_top", "smile", "long_hair", "solo_leveling", "multiple_views"):
        assert not is_count(tag), tag


def test_clothes_and_background_tags():
    for tag in ("shirt", "pleated_skirt", "school_uniform", "hair_ornament", "t-shirt", "off-shoulder_dress", "glasses", "nude", "barefoot", "thighhighs",
                "topwear", "fully_clothed"):
        assert is_clothes(tag), tag
    for tag in ("smile", "long_hair", "collarbone", "looking_at_viewer", "girl_on_top", "white_background"):
        assert not is_clothes(tag), tag
    for tag in ("white_background", "simple_background", "outdoors", "classroom", "night_sky", "cherry_blossoms", "on_bed", "against_wall", "outside"):
        assert is_background(tag), tag
    for tag in ("smile", "sun_hat", "upper_body", "holding", "1girl", "daydream"):
        assert not is_background(tag), tag


def test_without_clothes_the_character_keeps_its_outfit(danbooru):
    tag_list()
    danbooru.choose = lambda posts: posts[-1] # Post 4: 1girl smile skirt.
    assert run(tags="hatsune miku", rating="general + sensitive", include_clothes=False)[1] == "1girl, smile"
    assert run(tags="hatsune miku", rating="general + sensitive", include_clothes=True)[1] == "1girl, smile, skirt"
    assert run(tags="hatsune miku", rating="general + sensitive", include_clothes=False, include_count=False, include_background=False)[1] == "smile"


def test_exclude_patterns():
    leave_out = excluded("signature, *censor*, *_text, (*tail*:1.1)")
    for tag in ("signature", "bar_censor", "censored", "mosaic_censoring", "english_text", "twintails", "cat_tail"):
        assert leave_out(tag), tag
    for tag in ("smile", "text", "signature_x", "long_hair"):
        assert not leave_out(tag), tag
    assert not excluded("")("smile")


def test_exclude_patterns_in_the_node(danbooru):
    tag_list()
    assert run(tags="hatsune miku", exclude="*tail*, 1*, signature")[1] == "long hair, smile" # Not twintails, not 1girl.


def test_without_count_the_post_keeps_the_prompts_count(danbooru):
    tag_list()
    assert run(tags="hatsune miku", include_count=False)[1] == "long hair, smile, twintails" # Not 1girl.
    assert run(tags="hatsune miku", include_count=True)[1].startswith("1girl, ")


def test_several_posts_share_their_tags(danbooru):
    tag_list()
    picks = iter([0, 0, 1]) # Post 1, post 1 again (taken once), post 2.
    danbooru.choose = lambda posts: posts[next(picks)]
    output = execute(tags="hatsune miku", posts=2)
    text, added, urls, number = output.result
    assert danbooru.requests == ["hatsune_miku rating:g"] * 3
    assert added == "1girl, twintails, long hair, smile, thighhighs" # Both posts' tags first, then the most used.
    assert [url.rsplit("/", 1)[1] for url in urls.split("\n")] == ["1", "2"] and number == 1 # One link per line.
    assert output.ui["dice_forge_danbooru"][0]["post_ids"] == "1, 2"


def test_fixed_mode_takes_the_posts_of_post_ids(danbooru):
    tag_list()
    text, added, _urls, number = run(tags="hatsune miku", mode="fixed", post_ids="https://danbooru.donmai.us/posts/4, #2, 4")
    assert danbooru.requests == ["/posts/4.json", "/posts/2.json"] # No search; the rating doesn't matter: your pick.
    assert number == 4 and added == "1girl, smile, twintails, thighhighs, skirt"
    with pytest.raises(ValueError, match="fixed mode needs post_ids"):
        run(mode="fixed", post_ids="")
    with pytest.raises(ValueError, match="no post 99"):
        run(mode="fixed", post_ids="99")
    assert parse_post_ids("12, https://danbooru.donmai.us/posts/34?q=1girl #56\nnope 12") == [12, 34, 56]


def test_wildcards_in_tags_are_filled_in_and_fixed_keeps_them(danbooru, wildcards):
    tag_list()
    wildcards("who.txt", "hatsune miku\nsmile, hatsune miku\n")
    first = execute(tags="__who__, {1girl|1girl}")
    shown = first.ui["dice_forge_danbooru"][0]
    assert shown["tags"] in ("hatsune miku, 1girl", "smile, hatsune miku, 1girl") and first.result[0].startswith(shown["tags"])
    again = execute(tags="__who__, {1girl|1girl}", mode="fixed", post_ids=shown["post_ids"], wildcard_seed=shown["wildcard_seed"])
    assert again.result[0] == first.result[0] # The same wildcards and post: the same prompt.


def test_preview_url():
    assert preview_url({"media_asset": {"variants": [{"type": "180x180", "url": "a"}, {"type": "360x360", "url": "b"}]}, "preview_file_url": "c"}) == "b"
    assert preview_url({"preview_file_url": "c"}) == "c" and preview_url({}) == "" and preview_url({"media_asset": "x"}) == ""


def test_e621(danbooru):
    output = execute(tags="fox, smile", source="e621")
    text, added, url, number = output.result
    assert danbooru.requests == ["fox smile rating:s order:random"] # General: e621's safe; one request for random posts.
    assert number == 11 and url.endswith("/e621/posts/11")
    assert added == "solo, anthro, red body, shirt, canine" and text == "fox, smile, solo, anthro, red body, shirt, canine" # Species too.
    shown = output.ui["dice_forge_danbooru"][0]
    assert shown["site"] == "e621" and shown["posts"] == [{"id": 11, "url": url, "rating": "s", "rating_name": "safe", "safe": True,
                                                            "preview": "https://static/11.jpg"}]
    assert run(tags="fox, smile", source="e621", include_appearance=False, include_count=False)[1] == "shirt" # Not the body, anthro, the species.


def test_e621_ratings_and_fixed_mode(danbooru):
    e621 = SITES["e621"]
    assert [e621.rating_term(letters) for letters in ("g", "gs", "q", "gsq", "qe", "sqe", "gsqe")] == \
        ["rating:s", "rating:s", "rating:q", "-rating:e", "-rating:s", "", ""]
    assert run(tags="fox", source="e621", rating="up to questionable")[3] == 11
    assert run(tags="fox", source="e621", rating="explicit")[3] == 12
    with pytest.raises(ValueError, match="no questionable post on e621 has fox"):
        run(tags="fox", source="e621", rating="questionable")
    assert danbooru.requests == ["fox -rating:e order:random", "fox rating:e order:random", "fox rating:q order:random"]
    _text, added, _url, number = run(source="e621", mode="fixed", post_ids="https://e621.net/posts/12")
    assert danbooru.requests[-1] == "/e621/posts/12.json" and number == 12 and added == "duo, anthro, nude, fox, canine"
    with pytest.raises(ValueError, match="e621 has no post 99"):
        run(source="e621", mode="fixed", post_ids="99")
    with pytest.raises(ValueError, match="unknown source"):
        run(source="nope")


def test_the_prompt_input_goes_first_is_not_searched_nor_added_again(danbooru):
    tag_list()
    text, added, _url, _id = run(tags="hatsune miku", prompt="masterpiece, best quality, smile,")
    assert danbooru.requests == ["hatsune_miku rating:g"] # Only the tags search.
    assert added == "1girl, long hair, twintails" # smile is in the prompt input already.
    assert text == "masterpiece, best quality, smile, hatsune miku, 1girl, long hair, twintails"


def test_a_pair_no_post_has_is_searched_one_tag_at_a_time(danbooru):
    assert run(tags="nothing_here, smile")[3] == 1
    assert danbooru.requests == ["nothing_here smile rating:g", "nothing_here rating:g", "smile rating:g"]


def test_clear_errors(danbooru):
    with pytest.raises(ValueError, match="no general post on Danbooru has nothing_like_this"):
        run(tags="nothing_like_this")
    with pytest.raises(ValueError, match="unknown rating"):
        run(rating="nope")
    danbooru.refuse = True
    with pytest.raises(ValueError, match="refused the search"):
        run()


def test_a_busy_danbooru_is_asked_again(danbooru):
    danbooru.busy = 2 # 503 twice, then the post.
    assert run(tags="hatsune miku")[3] == 1
    assert len(danbooru.requests) == 3


def test_danbooru_busy_every_time_says_so(danbooru):
    danbooru.busy = 10
    with pytest.raises(ValueError, match=r"Danbooru is busy and turned the request away \(503 Service Unavailable\), 3 times in a row.*try again in a minute"):
        run(tags="hatsune miku")
    assert len(danbooru.requests) == 3 # Asked three times, no more.


def test_an_answer_that_isnt_json_is_asked_again_then_named(danbooru):
    danbooru.garbage = 1 # A maintenance page once, then the post.
    assert run(tags="hatsune miku")[3] == 1
    danbooru.garbage = 10
    with pytest.raises(ValueError, match=r"Danbooru is busy .*an answer that isn't JSON.*3 times in a row"):
        run(tags="hatsune miku")
    danbooru.garbage = 10
    with pytest.raises(ValueError, match=r"e621 is busy .*an answer that isn't JSON"):
        run(tags="fox", source="e621")


def test_e621_is_asked_at_most_twice_a_second(danbooru, monkeypatch):
    monkeypatch.setattr(SITES["e621"], "pause", 0.3)
    start = time.monotonic()
    assert run(source="e621", mode="fixed", post_ids="11, 12, 11")[3] == 11 # Two requests (11 once): a pause between them.
    assert time.monotonic() - start >= 0.3 and danbooru.requests[-2:] == ["/e621/posts/11.json", "/e621/posts/12.json"]


def test_each_site_searches_by_its_own_tag_list():
    tag_list() # Danbooru's: 1girl, hatsune_miku, smile...
    with open(os.path.join(tag_autocomplete.TAGS_FOLDER, "e621.csv"), "w", encoding="utf-8") as file:
        file.write("solo,0,3000000,\nanthro,0,2000000,\nfox,5,600000,\nsmile,0,900000,\n")
    e621 = SITES["e621"]
    assert search_tags(["solo", "anthro", "fox"], e621) == ["fox", "anthro"] # The species first, then the rarer general tag.
    assert search_tags(["1girl", "hatsune_miku", "solo"], e621) == ["solo"] # Danbooru's tags aren't e621's.
    assert search_tags(["fox", "smile", "hatsune_miku"]) == ["hatsune_miku", "smile"] # Danbooru's search knows only Danbooru's list.
    with open(os.path.join(tag_autocomplete.TAGS_FOLDER, "e621.csv"), "w", encoding="utf-8") as file:
        file.write("wolf,5,500000,\n")
    assert search_tags(["fox", "wolf"], e621) == ["wolf"] # Read again when the file changes.


def test_safebooru(danbooru):
    tag_list() # Danbooru's list tells the groups: hatsune_miku is a character, vocaloid a series.
    output = execute(tags="hatsune miku", source="safebooru")
    text, added, url, number = output.result
    assert danbooru.requests == ["safebooru hatsune_miku rating:safe -", "safebooru hatsune_miku rating:safe 0"] # How many, then a post at a random place.
    assert number == 21 and url.endswith("/safebooru/index.php?page=post&s=view&id=21")
    assert added == "1girl, smile, jack-o'-lantern" # Not the character or the series (off by default); an HTML entity read back.
    assert "vocaloid" in run(tags="hatsune miku", source="safebooru", include_copyright=True)[1]
    assert output.ui["dice_forge_danbooru"][0]["posts"][0] == {"id": 21, "url": url, "rating": "g", "rating_name": "safe", "safe": True,
                                                              "preview": url.split("/index.php")[0] + "/thumbnails/4567/thumbnail_abc.jpg"}
    assert run(tags="hatsune miku", source="safebooru", rating="questionable + explicit")[3] == 22
    assert danbooru.requests[-1] == "safebooru hatsune_miku -rating:safe 0"
    with pytest.raises(ValueError, match="no explicit post on Safebooru has hatsune_miku"):
        run(tags="hatsune miku", source="safebooru", rating="explicit")
    assert run(source="safebooru", mode="fixed", post_ids="22")[3] == 22 and danbooru.requests[-1] == "safebooru 22 -"
    with pytest.raises(ValueError, match="Safebooru has no post 99"):
        run(source="safebooru", mode="fixed", post_ids="99")
    safebooru = SITES["safebooru"]
    assert [safebooru.rating_term(letters) for letters in ("g", "gs", "qe", "gsq", "gsqe")] == ["rating:safe", "rating:safe", "-rating:safe", "-rating:explicit", ""]
    assert safebooru.listed(SAFEBOORU_POSTS[0])[0]["id"] == 21 and safebooru.listed({"post": SAFEBOORU_POSTS})[1]["id"] == 22 and safebooru.listed(None) == []


def test_e621_busy_names_e621(danbooru):
    danbooru.busy = 10
    with pytest.raises(ValueError, match=r"e621 is busy and turned the request away \(503 Service Unavailable\)"):
        run(tags="fox", source="e621")


# Whatever JSON a site answers with: a post is skipped or kept whole (an id above 0, texts, lists of tags), and its tags can always be added.
json_values = st.recursive(st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=12),
                           lambda children: st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=10), children, max_size=4), max_leaves=12)
tag_lists = st.lists(st.text(max_size=10) | json_values, max_size=5)
danbooru_posts = st.fixed_dictionaries({}, optional={
    "id": json_values, "rating": json_values, "score": json_values, "preview_file_url": json_values,
    "media_asset": json_values | st.fixed_dictionaries({"variants": st.lists(st.fixed_dictionaries({}, optional={"type": json_values, "url": json_values}), max_size=3)}),
    **{f"tag_string_{group}": json_values for group in GROUPS}})
e621_posts = st.fixed_dictionaries({}, optional={
    "id": json_values, "rating": json_values, "score": json_values | st.fixed_dictionaries({"total": json_values}),
    "preview": json_values | st.fixed_dictionaries({"url": json_values}),
    "tags": json_values | st.dictionaries(st.sampled_from(GROUPS), tag_lists | json_values, max_size=6)})


safebooru_posts = st.fixed_dictionaries({}, optional={"id": json_values, "rating": json_values, "score": json_values, "directory": json_values,
                                                     "image": json_values, "hash": json_values, "tags": json_values | st.text(max_size=40)})


@settings(max_examples=300)
@given(safebooru_posts | json_values, st.lists(safebooru_posts | json_values, max_size=3) | safebooru_posts | json_values)
def test_any_safebooru_json_gives_a_whole_post_or_none(data, listing):
    check_post(SITES["safebooru"].summary(data))
    for post in SITES["safebooru"].listed({"post": listing}) + SITES["safebooru"].listed(listing):
        check_post(post)


def check_post(post):
    if post is None:
        return
    assert isinstance(post["id"], int) and not isinstance(post["id"], bool) and post["id"] > 0
    assert all(isinstance(post[key], str) for key in ("rating", "rating_name", "preview")) and isinstance(post["safe"], bool)
    assert all(isinstance(post[group], list) and all(isinstance(tag, str) for tag in post[group]) for group in GROUPS)
    assert all(isinstance(tag, str) for tag in added_tags([post], list(GROUPS), set(), excluded("*censor*"), 0, [danbooru_enhancer.is_clothes]))


@settings(max_examples=300)
@given(danbooru_posts | json_values)
def test_any_danbooru_json_gives_a_whole_post_or_none(data):
    check_post(SITES["danbooru"].summary(data))


@settings(max_examples=300)
@given(e621_posts | json_values, st.lists(e621_posts | json_values, max_size=3) | json_values)
def test_any_e621_json_gives_a_whole_post_or_none(data, listing):
    check_post(SITES["e621"].summary(data))
    for post in SITES["e621"].listed({"posts": listing}) + SITES["e621"].listed(listing):
        check_post(post)


def test_offline_says_so():
    with pytest.raises(ValueError, match="can't be reached"):
        run()
