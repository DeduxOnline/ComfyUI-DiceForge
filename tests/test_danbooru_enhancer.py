# Danbooru Tag Enhancer (DiceForge/danbooru_enhancer.py): the prompt's tags read through weights and escapes, the search tags, the post picked by the
# seed modes, the tags added, the posts kept on disk, and a stand-in for Danbooru (no test goes online).
import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import pytest
from DiceForge import danbooru_enhancer, tag_autocomplete
from DiceForge.danbooru_enhancer import DanbooruTagEnhancer, prompt_tags, prompt_text, search_tags

TAGS = "1girl,0,6000000,\nhatsune_miku,4,90000,miku\nvocaloid,3,200000,\nsmile,0,4000000,\nlong_hair,0,5000000,\ntwintails,0,900000,\nsignature,0,800000,\n"


def post(number, rating, general, character="hatsune_miku"):
    return {"id": number, "rating": rating, "score": 100 - number, "tag_string_general": general, "tag_string_character": character,
            "tag_string_copyright": "vocaloid", "tag_string_artist": "someone", "tag_string_meta": "highres"}


POSTS = [post(1, "g", "1girl smile twintails long_hair signature"), post(2, "g", "1girl twintails thighhighs"), post(3, "e", "1girl nude"),
         post(4, "s", "1girl smile skirt")]


def found(tags):
    wanted = [tag for tag in tags.split() if not tag.startswith("order:")]
    return [item for item in POSTS if all(tag in " ".join(item[f"tag_string_{group}"] for group in ("general", "character", "copyright")).split() for tag in wanted)]


@pytest.fixture
def danbooru(monkeypatch):
    """The stand-in: posts by search; order:score is refused once when asked (requests are recorded)."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            tags = parse_qs(url.query).get("tags", [""])[0]
            self.server.requests.append(tags)
            if self.server.refuse_order and "order:" in tags:
                status, body = 422, {"message": "You cannot search for more than 2 tags at a time"}
            else:
                status, body = 200, found(tags)
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests, server.refuse_order = [], False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(danbooru_enhancer, "DANBOORU_URL", f"http://127.0.0.1:{server.server_port}")
    yield server
    server.shutdown()


def tag_list():
    os.makedirs(tag_autocomplete.TAGS_FOLDER, exist_ok=True)
    with open(os.path.join(tag_autocomplete.TAGS_FOLDER, "danbooru.csv"), "w", encoding="utf-8") as file:
        file.write(TAGS)


def run(tags="1girl, hatsune miku, masterpiece", **inputs):
    return asyncio.run(DanbooruTagEnhancer.execute(tags, **inputs)).result


def test_prompt_tags_read_through_the_prompt_syntax():
    assert prompt_tags("1girl, (long hair:1.2), hatsune miku \\(cosplay\\), <lora:x:1>, embedding:bad, __color__\nsmile, , 1girl") == \
        ["1girl", "long_hair", "hatsune_miku_(cosplay)", "smile"]
    assert prompt_text("hatsune_miku_(cosplay)") == "hatsune miku \\(cosplay\\)" and prompt_text("^_^") == "^_^"


def test_search_tags_are_the_most_telling():
    assert search_tags(["1girl", "masterpiece", "hatsune_miku"]) == (["1girl", "masterpiece"], ["1girl", "masterpiece", "hatsune_miku"]) # No lists: the first two.
    tag_list()
    assert search_tags(["1girl", "masterpiece", "smile", "hatsune_miku"]) == (["hatsune_miku", "smile"], ["1girl", "smile", "hatsune_miku"])


def test_adds_the_posts_tags_by_the_seed(danbooru):
    tag_list()
    danbooru.refuse_order = True # Danbooru counting order: as a tag: searched again without it.
    text, added, url, number = run(tags="1girl, hatsune miku, masterpiece", seed=0, seed_mode="sequential")
    assert danbooru.requests == ["hatsune_miku 1girl order:score", "hatsune_miku 1girl"] # The character first; masterpiece isn't a Danbooru tag.
    assert number == 1 and url.endswith("/posts/1") # General only (posts 1 and 2): not 3 (explicit) nor 4 (sensitive).
    assert added == "long hair, smile, twintails" # The most used first; 1girl is there already, signature excluded.
    assert text == "1girl, hatsune miku, masterpiece, long hair, smile, twintails"
    both = {run(seed=seed, seed_mode="deck")[3] for seed in range(2)}
    assert both == {1, 2} # deck: each post once.
    assert run(seed=7)[3] == run(seed=7)[3] # The same seed: the same post.


def test_options(danbooru):
    tag_list()
    first = run(seed=0, seed_mode="sequential", max_tags=2, add_character=True, add_copyright=True, position="before", rating="any")
    text, added, _url, number = first
    assert number == 1 and added == "smile, long hair" and text == "smile, long hair, 1girl, hatsune miku, masterpiece" # The most used first; miku is already there.
    assert run(seed=2, seed_mode="sequential", rating="any", max_tags=0)[1] == "nude"
    assert "vocaloid" in run(seed=0, seed_mode="sequential", rating="any", add_general=False, add_copyright=True)[1]


def test_posts_are_kept_and_used_offline(danbooru):
    tag_list()
    picked = run(seed=3)
    asked = len(danbooru.requests)
    assert run(seed=3) == picked and len(danbooru.requests) == asked # Kept: not asked again.
    danbooru.shutdown()
    danbooru_enhancer.DANBOORU_URL = "http://127.0.0.1:9"
    assert run(seed=3) == picked # Offline: the kept posts.


def test_clear_errors(danbooru):
    with pytest.raises(ValueError, match="no general post on Danbooru has"):
        run(tags="nothing_like_this")
    with pytest.raises(ValueError, match="unknown rating"):
        run(rating="nope")


def test_offline_without_kept_posts_says_so():
    with pytest.raises(ValueError, match="can't be reached"):
        run()
