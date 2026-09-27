import csv
import json
import math
import os
import re
import urllib.request
import folder_paths
# Danbooru tag library for Prompt Director: which tags the image model knows (downloaded once), and the tag groups bundled with the node.
KNOWN_TAGS_URL = "https://raw.githubusercontent.com/BetaDoggo/danbooru-tag-list/1a33931c472556ba249beb1ecbe98450534f6eb5/illustriousV1.0_underscore.csv"
KNOWN_TAGS_FILE = "danbooru_tags_illustrious_v1.0.csv" # Danbooru tags with post counts and aliases, up to the Illustrious v1.0 cutoff (2024-06-30), from https://github.com/BetaDoggo/danbooru-tag-list.
TAG_GROUPS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt_director", "tag_groups.json")
KNOWN_CATEGORIES = {"0", "3", "4"} # general, copyright and character tags; artist and meta tags are left out.
WEIGHTED = re.compile(r"^\((.+):([\d.]+)\)$")
_library = None
_download_error = None
# Tag key used for lookups: lowercase, underscores, no weight or escapes.
def tag_key(tag):
    match = WEIGHTED.match(tag.strip())
    tag = match.group(1) if match else tag
    return tag.replace("\\(", "(").replace("\\)", ")").strip().lower().replace(" ", "_")
# Prompt form of a tag key: spaces, and escaped qualifiers like "bar \(place\)".
def prompt_form(key):
    tag = key if key.startswith(("score_", "source_", "rating_")) else key.replace("_", " ")
    return tag.replace("(", "\\(").replace(")", "\\)")
# Known tags file location (the first prompt_director models folder), downloading it once when it is missing.
def known_tags_path():
    global _download_error
    folder = os.path.join(folder_paths.get_folder_paths("prompt_director")[0], "library")
    path = os.path.join(folder, KNOWN_TAGS_FILE)
    if os.path.isfile(path) or _download_error:
        return path if os.path.isfile(path) else None
    try:
        os.makedirs(folder, exist_ok=True)
        print(f"[Prompt Director] Downloading the Danbooru tag list to {path} (once)...")
        with urllib.request.urlopen(KNOWN_TAGS_URL, timeout=30) as response:
            data = response.read()
        with open(path + ".part", "wb") as file:
            file.write(data)
        os.replace(path + ".part", path)
        return path
    except Exception as error: # Offline or blocked: the node keeps working without the known tags list, and does not retry until ComfyUI restarts.
        _download_error = f"{type(error).__name__}: {error}"
        print(f"[Prompt Director] Could not download the Danbooru tag list ({_download_error}). Put {KNOWN_TAGS_FILE} from {KNOWN_TAGS_URL} in {folder} to enable tag checks.")
        return None
# Library data: post counts and aliases of known tags (when available), tag pools per slot group, content lists and groups of contradicting tags.
class TagLibrary:
    def __init__(self):
        with open(TAG_GROUPS_FILE, encoding="utf-8") as file:
            groups = json.load(file)
        self.pools = groups["pools"]
        self.sensitive, self.explicit = set(groups["sensitive"]), set(groups["explicit"])
        self.exclusive = [set(tags) for tags in groups["exclusive"].values()]
        self.counts, self.aliases = {}, {}
        path = known_tags_path()
        if path:
            with open(path, encoding="utf-8") as file:
                for row in csv.reader(file):
                    if len(row) < 3 or row[1] not in KNOWN_CATEGORIES:
                        continue
                    self.counts[row[0]] = int(row[2])
                    for alias in (row[3].split(",") if len(row) > 3 and row[3] else []):
                        self.aliases.setdefault(alias.strip(), row[0])
    @property
    def status(self):
        return f"{len(self.counts)} known tags" if self.counts else f"known tags unavailable ({_download_error or 'no file'}), content and conflict checks only"
    # Canonical key of a tag: itself when known, its alias target, or itself when there is no known tags list.
    def canonical(self, key):
        if key in self.counts or not self.counts:
            return key
        return self.aliases.get(key, key)
    # Content check: explicit tags never pass, sensitive tags only with the sensitive rating.
    def allowed(self, key, rating):
        return key not in self.explicit and (rating == "sensitive" or key not in self.sensitive)
    # Tag check for LLM output: fixes aliases, drops explicit (and, when general, sensitive) tags, unknown or rare tags when `drop_unknown`, and tags that contradict an earlier or fixed one.
    def check(self, tags, rating, min_count, drop_unknown, taken):
        kept, dropped = [], []
        for tag in tags:
            match = WEIGHTED.match(tag)
            key = self.canonical(tag_key(tag))
            reason = None
            if not self.allowed(key, rating):
                reason = "content"
            elif drop_unknown and self.counts and self.counts.get(key, 0) < min_count:
                reason = "unknown"
            elif any(key in group and taken & group - {key} for group in self.exclusive):
                reason = "conflict"
            if reason:
                dropped.append(f"{tag} ({reason})")
                continue
            taken.add(key)
            kept.append(f"({prompt_form(key)}:{match.group(2)})" if match else prompt_form(key))
        return kept, dropped
    # Tag ideas for the LLM: real, allowed tags of a slot group, picked at random with popular tags more likely.
    def hints(self, group, count, rating, min_count, rng):
        pool = [key for key in self.pools.get(group, []) if self.allowed(key, rating) and (not self.counts or self.counts.get(key, 0) >= min_count)]
        weights = [math.sqrt(self.counts.get(key, 1)) for key in pool]
        picked = set()
        while pool and len(picked) < min(count, len(pool)):
            picked.add(rng.choices(pool, weights=weights)[0])
        return [prompt_form(key) for key in sorted(picked, key=lambda key: -self.counts.get(key, 0))]
# Shared library instance, loaded on first use.
def get_library():
    global _library
    if _library is None:
        _library = TagLibrary()
    return _library
