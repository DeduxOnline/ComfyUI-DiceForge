"""Builds ResolutionForge/prompt_director/tag_groups.json from the Danbooru tag groups export.

Source: tag_groups_flat.jsonl from https://github.com/PBandDev/danbooru-tag-groups-scraper/releases (MIT license).
Usage: python tools/build_tag_library.py path/to/tag_groups_flat.jsonl data-2026-09
"""
import json
import os
import re
import sys

# Tag pools per Prompt Director slot group: (page, section prefixes); an empty tuple takes the whole page.
POOLS = {
    "character": [
        ("Hair Styles", ("Length and volume", "Hairstyles")),
        ("Hair Color", ("Specific colors", "Multiple colors")),
        ("Hair", ("Objects",)),
        ("Eyes Tags", ("Iris", "Pupils")),
        ("Ears Tags", ()),
    ],
    "outfit": [
        ("Attire", ()),
        ("Headwear", ("Types", "Hats", "Helmets", "Crowns", "Other")),
        ("Legwear", ()),
        ("Handwear", ("Gloves",)),
        ("Neck And Neckwear", ("Detached Neckwear", "Collared clothes", "Ascots", "Bowties", "Chokers", "Neckties", "Scarves")),
        ("Accessories", ("Jewelry", "Bags", "By body part")),
        ("Eyewear", ()),
    ],
    "expression": [
        ("Face Tags", ("Main", "Emotions", "Smile", "Smug", "Surprised / Scared / Sad")),
        ("Eyes Tags", ("Emotions and expressions", "One or two eyes closed")),
    ],
    "pose": [
        ("Posture", ()),
        ("Gestures", ()),
        ("Holding Tags", ()),
        ("Face Tags", ("Looking at...",)),
        ("Image Composition", ("View Angle",)),
    ],
    "location": [
        ("Locations", ("Indoors", "Outdoors", "Buildings", "Other")),
        ("Water", ("Geography",)),
    ],
    "details": [
        ("Lighting", ()),
        ("Water", ("Meteorology",)),
        ("Flowers", ()),
    ],
}
# Sections that are only allowed with the sensitive rating.
SENSITIVE = [
    ("Nudity", ("Partial nudity", "Dressing / Covering body parts", "Touching clothes")),
    ("Sexual Attire", ("Lingerie",)),
    ("Breasts Tags", ("Main", "Breast sizes", "Visibility", "Clothes for breasts", "Descriptions of breasts")),
    ("Ass", ("Anatomy of the ass",)),
    ("Attire", ("Swimsuits and Bodysuits",)),
    ("Pussy", ("Pussy attire",)),
]
# Sections that are never allowed.
EXPLICIT = [
    ("Sex Acts", ()), ("Sex Objects", ()), ("Sexual Positions", ()), ("Simulated Sex Acts", ()), ("Bdsm And Torture", ()), ("Censorship", ()),
    ("Pussy", ("Anatomy of the pussy", "Pussy under clothes", "Hands on pussy", "Visible parts of the pussy", "Pussy and fluids", "Sexual objects and acts involving the pussy", "Pussy adornments")),
    ("Ass", ("Anatomy of the anus", "Ass and hands", "Ass and heads", "Ass with cum", "Misc")),
    ("Nudity", ("Complete (or mostly complete) nudity", "Nudity by gender", "Naughty points of view", "Misc / more")),
    ("Sexual Attire", ("BDSM", "Exposure", "More / Miscellaneous")),
    ("Breasts Tags", ("Breasts and other parts of the body", "Misc")),
    ("Face Tags", ("Sexual",)),
]
# Clothing pages whose own (not implied) tags count as safe, even when the tag is also listed in a sensitive or explicit section (thighhighs is Legwear as well as Lingerie).
SAFE_PAGES = {"Attire", "Legwear", "Headwear", "Handwear", "Neck And Neckwear", "Accessories", "Shoulders", "Sleeves", "Eyewear"}
# Everyday tags that are listed in a sensitive or explicit section too (barefoot on a beach is fine).
SAFE_EXTRA = {"feet", "barefoot", "toes", "armpits", "bare_legs", "bare_arms"}
# Explicit tags that Danbooru files under body parts or postures rather than in the sections above.
EXPLICIT_EXTRA = {"nude", "completely_nude", "topless", "bottomless", "nipples", "areolae", "pussy", "penis", "testicles", "anus", "erection", "cum", "sex",
                  "vaginal", "oral", "fellatio", "masturbation", "spread_legs", "spread_pussy", "cameltoe", "pubic_hair", "uncensored", "censored", "nsfw"}
SAFE_EXCEPT = [("Attire", ("Swimsuits and Bodysuits",)), ("Face Tags", ("Sexual",))]
# Groups of tags that contradict each other: only one of each is kept in a prompt.
EXCLUSIVE = {
    "hair length": ("Hair Styles", ("Length and volume",), {"big_hair", "bald", "balding"}),
    "framing": ("Image Composition", ("Subject matter > Framing the body",), {"arm_out_of_frame", "cropped_arms", "cropped_head", "cropped_legs", "cropped_shoulders", "cropped_torso", "cut-in", "eyes_out_of_frame", "feet_out_of_frame", "foot_out_of_frame", "group_profile", "head_out_of_frame", "knees_out_of_frame", "profile", "split_crop", "close-up"}),
}


def section_of(row):
    return " > ".join(row["section_path"][1:])


def in_sections(row, rules):
    return any(row["page_title"] == page and (not prefixes or section_of(row).startswith(prefixes)) for page, prefixes in rules)


def main(path, release):
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    rows = [row for row in rows if row["page_kind"] == "tag_group"]
    wiki = [row for row in rows if row["source"] == "wiki"]
    pools = {group: sorted({row["canonical_name"] for row in wiki if in_sections(row, rules)}) for group, rules in POOLS.items()}
    safe = {row["canonical_name"] for row in wiki if row["page_title"] in SAFE_PAGES and not in_sections(row, SAFE_EXCEPT)} | SAFE_EXTRA
    # Only a tag's own listings count here: implied rows would flag everything a broad tag implies (every breast size implies breasts).
    sensitive = {row["canonical_name"] for row in wiki if in_sections(row, SENSITIVE)} - safe
    explicit = sorted(({row["canonical_name"] for row in wiki if in_sections(row, EXPLICIT)} - safe - sensitive) | EXPLICIT_EXTRA)
    sensitive -= EXPLICIT_EXTRA
    sensitive = sorted(sensitive)
    exclusive = {name: sorted({row["canonical_name"] for row in wiki if in_sections(row, [(page, prefixes)])} - skip) for name, (page, prefixes, skip) in EXCLUSIVE.items()}
    blocked = set(explicit)
    # Pools skip explicit tags and emoticons like +_+ (they stay valid tags, they are just poor hints).
    pools = {group: [tag for tag in tags if tag not in blocked and re.search(r"[a-z]{3}", tag)] for group, tags in pools.items()}
    data = {
        "source": f"Danbooru tag groups, {release} release of https://github.com/PBandDev/danbooru-tag-groups-scraper (MIT license, Copyright (c) 2026 PBandDev)",
        "pools": pools,
        "exclusive": exclusive,
        "sensitive": sensitive,
        "explicit": explicit,
    }
    out = os.path.join(os.path.dirname(__file__), "..", "ResolutionForge", "prompt_director", "tag_groups.json")
    with open(out, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {os.path.normpath(out)}: " + ", ".join(f"{group} {len(tags)}" for group, tags in pools.items()) + f", sensitive {len(sensitive)}, explicit {len(explicit)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "unknown")
