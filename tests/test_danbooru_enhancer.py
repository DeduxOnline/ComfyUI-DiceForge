# Danbooru Tag Enhancer (DiceForge/danbooru_enhancer.py): the prompt's tags read through weights and escapes, the search tags, Danbooru's random
# post, the tags added, and a stand-in for Danbooru (no test goes online).
import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import pytest
from DiceForge import danbooru_enhancer, tag_autocomplete
from DiceForge.danbooru_enhancer import DanbooruTagEnhancer, prompt_tags, prompt_text, search_tags, searches

TAGS = "1girl,0,6000000,\nhatsune_miku,4,90000,miku\nvocaloid,3,200000,\nsmile,0,4000000,\nlong_hair,0,5000000,\ntwintails,0,900000,\nsignature,0,800000,\nthighhighs,0,700000,\n"


def post(number, rating, general, character="hatsune_miku"):
    return {"id": number, "rating": rating, "score": 100 - number, "tag_string_general": general, "tag_string_character": character,
            "tag_string_copyright": "vocaloid", "tag_string_artist": "someone", "tag_string_meta": "highres"}


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
    two tags (rating: isn't counted) or when told to refuse. Requests are recorded."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            tags = parse_qs(url.query).get("tags", [""])[0]
            self.server.requests.append(tags)
            posts = found(tags)
            if url.path != "/posts/random.json":
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
    server.requests, server.refuse, server.choose = [], False, lambda posts: posts[0]
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
    assert output.ui["dice_forge_danbooru"][0] == {"text": text, "added": added, "url": url, "id": 1, "search": "hatsune_miku 1girl rating:g", "rating": "g"}


def test_a_new_post_on_every_run(danbooru):
    first = DanbooruTagEnhancer.fingerprint_inputs(tags="x")
    assert DanbooruTagEnhancer.fingerprint_inputs(tags="x") != first # Never from the cache.
    danbooru.choose = lambda posts: posts[-1]
    assert run(tags="hatsune miku", rating="general + sensitive")[3] == 4
    assert run(tags="hatsune miku", rating="general")[3] == 2
    assert danbooru.requests == ["hatsune_miku rating:g,s", "hatsune_miku rating:g"] # Asked each time.


def test_options(danbooru):
    tag_list()
    text, added, _url, number = run(max_tags=2, add_character=True, add_copyright=True, position="before", rating="any")
    assert number == 1 and added == "long hair, smile" and text == "long hair, smile, 1girl, hatsune miku, masterpiece" # The most used first.
    assert danbooru.requests[-1] == "hatsune_miku 1girl" # Any: no rating term.
    danbooru.choose = lambda posts: next(post for post in posts if post["id"] == 3)
    assert run(rating="any", max_tags=0)[1] == "nude"
    assert "vocaloid" in run(rating="any", add_general=False, add_copyright=True)[1]


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


def test_offline_says_so():
    with pytest.raises(ValueError, match="can't be reached"):
        run()
