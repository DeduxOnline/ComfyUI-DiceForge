# Tag autocomplete (DiceForge/tag_autocomplete.py): tag lists in tagcomplete's CSV format, the search, merging lists, and the download.
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import pytest
from DiceForge import tag_autocomplete
from DiceForge.tag_autocomplete import TagIndex, parse_tags

DANBOORU = 'long_hair,0,5000000,"longhair,long-hair"\nshort_hair,0,2000000,\nlong_sleeves,0,1500000,\nhatsune_miku,4,90000,miku\n^_^,0,30000,\nlo,0,10,\n1girl,0,6000000,\nbad row,x,y,\n'


def write_list(name, text):
    os.makedirs(tag_autocomplete.TAGS_FOLDER, exist_ok=True)
    with open(os.path.join(tag_autocomplete.TAGS_FOLDER, name), "w", encoding="utf-8") as file:
        file.write(text)


def test_parse_skips_rows_that_are_not_tags():
    tags = parse_tags("﻿tag,type,count,aliases\n" + DANBOORU)
    assert tags[0] == ("long_hair", 0, 5000000, ["longhair", "long-hair"]) and len(tags) == 7 # The header and the bad row are left out.


def test_search_by_prefix_most_used_first_with_aliases():
    write_list("danbooru.csv", DANBOORU)
    index = TagIndex().load()
    assert [tag["tag"] for tag in index.search("lo")] == ["long_hair", "long_sleeves", "lo"]
    assert [tag["tag"] for tag in index.search("long h")] == ["long_hair"] # Spaces typed for underscores.
    assert index.search("mik") == [{"tag": "hatsune_miku", "type": "character", "count": 90000, "alias": "miku"}]
    assert [tag["tag"] for tag in index.search("hair", limit=2)] == ["long_hair", "short_hair"] # Few start with it: the ones that contain it.
    assert index.search("") == [] and index.search("zzz") == []


def test_lists_are_merged_and_read_again_when_changed():
    write_list("danbooru.csv", DANBOORU)
    write_list("e621.csv", "long_hair,0,10,\nfur,0,700000,\n")
    index = TagIndex().load()
    assert index.search("long_hair")[0]["count"] == 5000000 and index.search("fur")[0]["tag"] == "fur" # A tag in both: once, its higher count.
    write_list("e621.csv", "feathers,0,5,\n")
    os.utime(os.path.join(tag_autocomplete.TAGS_FOLDER, "e621.csv"), (1, 1))
    assert index.load().search("fur") == [] and index.search("feath")[0]["tag"] == "feathers"


def test_browse_gives_each_tag_its_site_for_the_wiki_link():
    write_list("danbooru.csv", DANBOORU)
    write_list("e621.csv", "long_hair,0,10,\nfur,0,700000,\n")
    index = TagIndex().load()
    sites = {tag["tag"]: tag["site"] for tag in index.browse(limit=100)["tags"]}
    assert sites["fur"] == "e621" and sites["long_hair"] == "danbooru" and sites["1girl"] == "danbooru" # In both: the list it came from.


def test_routes(api):
    status, body = api("GET", "/diceforge/tags?q=lo")
    assert status == 200 and body == {"tags": [], "ready": False}
    write_list("danbooru.csv", DANBOORU)
    assert [tag["tag"] for tag in api("GET", "/diceforge/tags?q=lo&limit=1")[1]["tags"]] == ["long_hair"]
    lists = api("GET", "/diceforge/tags/lists")[1]
    assert lists["files"] == ["danbooru.csv"] and [(item["name"], item["here"]) for item in lists["lists"]] == [("danbooru", True), ("e621", False)]
    assert api("POST", "/diceforge/tags/download", json={"list": "nope"})[0] == 400


@pytest.fixture
def tag_server(monkeypatch):
    """A stand-in for the tag lists' host: danbooru is a list, e621 an HTML page."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            text = DANBOORU + "".join(f"extra_tag_{number},0,{number},\n" for number in range(self.server.extra))
            data = (text if self.path.endswith("danbooru.csv") else "<html>not found</html>").encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            for start in range(0, len(data), 4096): # In pieces with pauses, as a real host sends a big file.
                self.wfile.write(data[start:start + 4096])
                self.wfile.flush()
                if self.server.extra:
                    time.sleep(0.005)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.extra = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(tag_autocomplete, "TAGS_URL", f"http://127.0.0.1:{server.server_port}/tags/{{name}}.csv")
    yield server
    server.shutdown()


def test_download_saves_the_list_and_refuses_what_is_not_one(api, tag_server):
    status, body = api("POST", "/diceforge/tags/download", json={"list": "danbooru"})
    assert status == 200 and body == {"list": "danbooru", "tags": 7}
    assert sorted(os.listdir(tag_autocomplete.TAGS_FOLDER)) == ["danbooru.csv"]
    assert api("GET", "/diceforge/tags?q=1g")[1]["tags"][0]["tag"] == "1girl"
    status, text = api("POST", "/diceforge/tags/download", json={"list": "e621"})
    assert status == 502 and "not a tag list" in text and not os.path.exists(os.path.join(tag_autocomplete.TAGS_FOLDER, "e621.csv"))


def test_download_reads_a_big_list_to_the_end(api, tag_server):
    tag_server.extra = 20000 # About 450 KB in 4 KB pieces: a list cut after the first piece would have a hundred tags or so.
    status, body = api("POST", "/diceforge/tags/download", json={"list": "danbooru"})
    assert status == 200 and body == {"list": "danbooru", "tags": 20007}
    assert TagIndex().load().browse()["total"] == 20007


def test_download_without_the_host_says_so(api):
    status, text = api("POST", "/diceforge/tags/download", json={"list": "danbooru"})
    assert status == 502 and "can't download" in text


def test_browse_by_type_text_and_order():
    write_list("danbooru.csv", DANBOORU)
    index = TagIndex().load()
    everything = index.browse()
    assert everything["total"] == 7 and [tag["tag"] for tag in everything["tags"][:3]] == ["1girl", "long_hair", "short_hair"] # Most used first.
    assert [tag["tag"] for tag in index.browse(kind="character")["tags"]] == ["hatsune_miku"]
    assert [tag["tag"] for tag in index.browse("hair")["tags"]] == ["long_hair", "short_hair"]
    assert [tag["tag"] for tag in index.browse("long")["tags"]] == ["long_hair", "long_sleeves"]
    assert [tag["tag"] for tag in index.browse("miku")["tags"]] == ["hatsune_miku"] # By its alias.
    assert [tag["tag"] for tag in index.browse(sort="name", limit=3)["tags"]] == ["1girl", "^_^", "hatsune_miku"]
    page = index.browse(offset=5, limit=10)
    assert page["total"] == 7 and len(page["tags"]) == 2
    favorites = index.browse(kind="favorites", favorites=frozenset({"lo", "smile"}))
    assert [(tag["tag"], tag["favorite"]) for tag in favorites["tags"]] == [("lo", True)] # A favorite not in the lists isn't shown.


def test_browse_and_favorite_routes(api):
    write_list("danbooru.csv", DANBOORU)
    assert api("POST", "/diceforge/tags/favorite", json={"tag": "long_hair", "favorite": True})[1] == {"favorites": 1}
    status, body = api("GET", "/diceforge/tags/browse?type=favorites")
    assert status == 200 and body["ready"] and [tag["tag"] for tag in body["tags"]] == ["long_hair"] and body["tags"][0]["favorite"]
    assert api("POST", "/diceforge/tags/favorite", json={"tag": "long_hair", "favorite": False})[1] == {"favorites": 0}
    assert api("GET", "/diceforge/tags/browse?type=favorites")[1]["total"] == 0
    assert api("GET", "/diceforge/tags/browse?q=hair&limit=1")[1]["total"] == 2
    for query in ("type=nope", "sort=nope"):
        assert api("GET", f"/diceforge/tags/browse?{query}")[0] == 400
    for body in ({"tag": "", "favorite": True}, {"tag": "x"}, {"tag": 5, "favorite": True}):
        assert api("POST", "/diceforge/tags/favorite", json=body)[0] == 400


RELATED = {"query": "1girl", "related_tags": [{"tag": {"name": "1girl", "category": 0, "post_count": 6}}, {"tag": {"name": "solo", "category": 0, "post_count": 5}},
                                              {"tag": {"name": "hatsune_miku", "category": 4, "post_count": 9}}, {"tag": {"name": "solo"}}, "junk", {"tag": 5}]}


@pytest.fixture
def related_server(monkeypatch):
    """A stand-in for Danbooru's related_tag.json: RELATED for 1girl, 404 for anything else; it counts the requests."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            self.server.requests.append(url.path)
            found = url.path == "/related_tag.json" and parse_qs(url.query).get("query") == ["1girl"]
            data = json.dumps(RELATED).encode() if found else b'{"error": "not found"}'
            self.send_response(200 if found else 404)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    from DiceForge import danbooru_enhancer
    monkeypatch.setattr(danbooru_enhancer, "DANBOORU_URL", f"http://127.0.0.1:{server.server_port}")
    tag_autocomplete.related_cache.clear()
    yield server
    server.shutdown()
    tag_autocomplete.related_cache.clear()


def test_related_tags_come_from_danbooru_once_per_tag(api, related_server):
    status, body = api("GET", "/diceforge/tags/related?tag=1girl")
    assert status == 200 and body["related"] == [{"tag": "solo", "type": "general", "count": 5}, {"tag": "hatsune_miku", "type": "character", "count": 9}]
    assert api("GET", "/diceforge/tags/related?tag=1girl")[1] == body and related_server.requests == ["/related_tag.json"] # Asked once.
    assert api("GET", "/diceforge/tags/related?tag=nothing_like_it")[1]["related"] == [] # Unknown to Danbooru: none.
    assert api("GET", "/diceforge/tags/related")[0] == 400


def test_related_tags_read_the_older_answer_and_say_when_danbooru_is_out_of_reach(api):
    assert tag_autocomplete.related_list({"related_tags": [["solo", 0], ["miku", 4], ["x"]]}, "x") == [
        {"tag": "solo", "type": "general", "count": 0}, {"tag": "miku", "type": "character", "count": 0}]
    assert tag_autocomplete.related_list(None, "x") == [] and tag_autocomplete.related_list({"related_tags": "junk"}, "x") == []
    tag_autocomplete.related_cache.clear()
    status, text = api("GET", "/diceforge/tags/related?tag=solo") # The tests' Danbooru is out of reach.
    assert status == 502 and "Tag Browser" in text
