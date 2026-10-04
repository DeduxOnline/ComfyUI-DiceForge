# Danbooru Tag Enhancer (DiceForge/danbooru_enhancer.py): the prompt's tags read through weights and escapes, the search tags, Danbooru's random
# post, the tags added, the fixed mode, wildcards, and a stand-in for Danbooru (no test goes online).
import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import pytest
from DiceForge import danbooru_enhancer, tag_autocomplete
from DiceForge.danbooru_enhancer import (DanbooruTagEnhancer, excluded, is_appearance, is_background, is_clothes, is_count, parse_post_ids, preview_url,
                                         prompt_tags, prompt_text, search_tags, searches)

TAGS = "1girl,0,6000000,\nhatsune_miku,4,90000,miku\nvocaloid,3,200000,\nsmile,0,4000000,\nlong_hair,0,5000000,\ntwintails,0,900000,\nsignature,0,800000,\nthighhighs,0,700000,\n"


def post(number, rating, general, character="hatsune_miku"):
    return {"id": number, "rating": rating, "score": 100 - number, "tag_string_general": general, "tag_string_character": character,
            "tag_string_copyright": "vocaloid", "tag_string_artist": "someone", "tag_string_meta": "highres", "preview_file_url": f"https://cdn/{number}.jpg"}


POSTS = [post(1, "g", "1girl smile twintails long_hair signature"), post(2, "g", "1girl twintails thighhighs"), post(3, "e", "1girl nude"),
         post(4, "s", "1girl smile skirt")]


def found(tags):
    wanted = [tag for tag in tags.split() if not tag.startswith("rating:")]
    ratings = next((tag[len("rating:"):].split(",") for tag in tags.split() if tag.startswith("rating:")), None)
    return [item for item in POSTS if (ratings is None or item["rating"] in ratings) and all(
        tag in " ".join(item[f"tag_string_{group}"] for group in ("general", "character", "copyright")).split() for tag in wanted)]


@pytest.fixture
def danbooru(monkeypatch):
    """The stand-in of /posts/random.json: a post of the search (server.choose picks it: the first by default), 404 when none has the tags, 422 past
    two tags (rating: isn't counted) or when told to refuse; and of /posts/<id>.json. Requests are recorded (the search, or the path)."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            tags = parse_qs(url.query).get("tags", [""])[0]
            self.server.requests.append(tags if url.path == "/posts/random.json" else url.path)
            posts = found(tags)
            by_id = next((item for item in POSTS if url.path == f"/posts/{item['id']}.json"), None)
            if self.server.busy > 0: # Danbooru overloaded: 503 this many times.
                self.server.busy -= 1
                status, body = 503, {"message": "Service Unavailable"}
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
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests, server.refuse, server.choose, server.busy = [], False, lambda posts: posts[0], 0
    monkeypatch.setattr(danbooru_enhancer, "RETRY_DELAYS", (0, 0)) # No waiting in the tests.
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(danbooru_enhancer, "DANBOORU_URL", f"http://127.0.0.1:{server.server_port}")
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
    assert shown["posts"] == [{"id": 1, "url": url, "rating": "g", "preview": "https://cdn/1.jpg"}] and isinstance(shown["wildcard_seed"], int)


def test_a_new_post_on_every_run(danbooru):
    first = DanbooruTagEnhancer.fingerprint_inputs(tags="x", mode="random")
    assert DanbooruTagEnhancer.fingerprint_inputs(tags="x", mode="random") != first # Never from the cache.
    assert DanbooruTagEnhancer.fingerprint_inputs(tags="x", mode="fixed") == DanbooruTagEnhancer.fingerprint_inputs(tags="x", mode="fixed") # Cached.
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
                "heterochromia", "hair_between_eyes", "elf"):
        assert is_appearance(tag), tag
    for tag in ("smile", "1girl", "shirt", "hair_ornament", "hair_ribbon", "hand_in_hair", "earrings", "blush", "thighhighs", "hairclip", "outdoors"):
        assert not is_appearance(tag), tag


def test_without_appearance_the_post_adds_the_rest(danbooru):
    tag_list()
    assert run(include_appearance=False)[1] == "smile" # Not long hair nor twintails: the character keeps its own look.
    assert run(include_appearance=True)[1] == "long hair, smile, twintails"


def test_count_tags():
    for tag in ("1girl", "2girls", "6+girls", "multiple_girls", "1boy", "3boys", "multiple_boys", "1other", "multiple_others", "solo", "solo_focus", "no_humans"):
        assert is_count(tag), tag
    for tag in ("girl", "boy_on_top", "smile", "long_hair", "solo_leveling", "multiple_views"):
        assert not is_count(tag), tag


def test_clothes_and_background_tags():
    for tag in ("shirt", "pleated_skirt", "school_uniform", "hair_ornament", "t-shirt", "off-shoulder_dress", "glasses", "nude", "barefoot", "thighhighs"):
        assert is_clothes(tag), tag
    for tag in ("smile", "long_hair", "collarbone", "looking_at_viewer", "girl_on_top", "white_background"):
        assert not is_clothes(tag), tag
    for tag in ("white_background", "simple_background", "outdoors", "classroom", "night_sky", "cherry_blossoms", "on_bed", "against_wall"):
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


def test_offline_says_so():
    with pytest.raises(ValueError, match="can't be reached"):
        run()
