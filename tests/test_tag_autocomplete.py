# Tag autocomplete (DiceForge/tag_autocomplete.py): tag lists in tagcomplete's CSV format, the search, merging lists, and the download.
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
            data = (DANBOORU if self.path.endswith("danbooru.csv") else "<html>not found</html>").encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(tag_autocomplete, "TAGS_URL", f"http://127.0.0.1:{server.server_port}/tags/{{name}}.csv")
    yield
    server.shutdown()


def test_download_saves_the_list_and_refuses_what_is_not_one(api, tag_server):
    status, body = api("POST", "/diceforge/tags/download", json={"list": "danbooru"})
    assert status == 200 and body == {"list": "danbooru", "tags": 7}
    assert sorted(os.listdir(tag_autocomplete.TAGS_FOLDER)) == ["danbooru.csv"]
    assert api("GET", "/diceforge/tags?q=1g")[1]["tags"][0]["tag"] == "1girl"
    status, text = api("POST", "/diceforge/tags/download", json={"list": "e621"})
    assert status == 502 and "not a tag list" in text and not os.path.exists(os.path.join(tag_autocomplete.TAGS_FOLDER, "e621.csv"))


def test_download_without_the_host_says_so(api):
    status, text = api("POST", "/diceforge/tags/download", json={"list": "danbooru"})
    assert status == 502 and "can't download" in text
