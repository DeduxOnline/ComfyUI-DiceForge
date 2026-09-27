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
# Pages whose sections Prompt Director data can pick from with `pool` (as "Page > Section > Subsection").
SECTION_PAGES = ["Attire", "Accessories", "Headwear", "Legwear", "Handwear", "Neck And Neckwear", "Eyewear", "Hair", "Hair Styles", "Hair Color", "Eyes Tags",
                 "Face Tags", "Posture", "Gestures", "Holding Tags", "Locations", "Lighting", "Water", "Flowers"]
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
    ("Holding Tags", ("Sexual Intercourse", "Body Part > Other", "Smoking", "Medical Equipment")),
    ("Hair", ("Miscellaneous",)),
]
# Clothing pages whose own (not implied) tags count as safe, even when the tag is also listed in a sensitive or explicit section (thighhighs is Legwear as well as Lingerie).
SAFE_PAGES = {"Attire", "Legwear", "Headwear", "Handwear", "Neck And Neckwear", "Accessories", "Shoulders", "Sleeves", "Eyewear"}
# Everyday tags that are listed in a sensitive or explicit section too (barefoot on a beach is fine).
SAFE_EXTRA = {"feet", "barefoot", "toes", "armpits", "bare_legs", "bare_arms", "covering_own_mouth", "covering_own_eyes", "covering_own_ears", "covering_face",
              "covering_head", "covering_one_eye", "adjusting_clothes", "open_coat", "open_jacket", "open_hoodie", "open_vest", "sleeveless", "bathrobe", "jumpsuit",
              "short_jumpsuit", "romper", "kesa", "tunic", "racing_suit", "wetsuit", "rash_guard", "shoe_pull", "sock_pull", "hip_vent", "side_slit", "zettai_ryouiki",
              "bad_ass", "apron_grab", "cape_lift", "lifting_covers", "wringing_clothes", "clothes_grab"}
# Explicit tags that Danbooru files under body parts or postures rather than in the sections above.
EXPLICIT_EXTRA = {"nude", "completely_nude", "topless", "bottomless", "nipples", "areolae", "pussy", "penis", "testicles", "anus", "erection", "cum", "sex",
                  "vaginal", "oral", "fellatio", "masturbation", "spread_legs", "spread_pussy", "cameltoe", "pubic_hair", "uncensored", "censored", "nsfw",
                  "areola_slip", "nipple_slip", "clitoris_slip", "penis_peek", "pussy_peek", "bandaid_on_pussy", "maebari", "breasts_out", "one_breast_out",
                  "topless_female", "topless_male", "no_panties", "no_bra", "underwear_only", "naked_apron", "nearly_naked_apron", "naked_bandage", "naked_cape",
                  "naked_capelet", "naked_chocolate", "naked_cloak", "naked_coat", "naked_hoodie", "naked_jacket", "naked_overalls", "naked_ribbon", "naked_robe",
                  "naked_scarf", "naked_sheet", "naked_shirt", "naked_suspenders", "naked_tabard", "naked_towel", "nude_cover", "breastless_clothes", "cupless_bra",
                  "cupless_bikini", "nipple_cutout", "crotch_cutout", "pearl_thong", "slingshot_swimsuit", "micro_bikini", "rei_no_himo", "penis_sheath",
                  "covering_privates", "covering_crotch", "covering_anus", "spread_ass", "hand_in_bra", "panties_on_breasts", "undressing", "skirt_lift",
                  "dress_lift", "shirt_lift", "panty_pull", "panty_lift", "wedgie", "breast_slip", "towel_slip", "robe_slip", "shirt_slip",
                  "fellatio_gesture", "handjob_gesture", "oral_invitation", "love_hotel", "straddling", "sex_toy", "groping_motion", "groping"}
# Revealing tags that Danbooru files under ordinary attire.
SENSITIVE_EXTRA = {"bikini_armor", "reverse_bunnysuit", "revealing_clothes", "string_panties", "highleg", "highleg_leotard", "underbust"}
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
    sensitive = (sensitive | SENSITIVE_EXTRA) - EXPLICIT_EXTRA
    sensitive = sorted(sensitive)
    exclusive = {name: sorted({row["canonical_name"] for row in wiki if in_sections(row, [(page, prefixes)])} - skip) for name, (page, prefixes, skip) in EXCLUSIVE.items()}
    blocked = set(explicit)
    # Pools skip explicit tags and emoticons like +_+ (they stay valid tags, they are just poor hints).
    pools = {group: [tag for tag in tags if tag not in blocked and re.search(r"[a-z]{3}", tag)] for group, tags in pools.items()}
    # Sections for `pool`: every level of each section path, so "Posture > Arms" also holds the tags of its subsections.
    sections = {}
    for row in wiki:
        if row["page_title"] in SECTION_PAGES and row["canonical_name"] not in blocked:
            path = [row["page_title"], *row["section_path"][1:]]
            for depth in range(1, len(path) + 1):
                sections.setdefault(" > ".join(path[:depth]), set()).add(row["canonical_name"])
    data = {
        "source": f"Danbooru tag groups, {release} release of https://github.com/PBandDev/danbooru-tag-groups-scraper (MIT license, Copyright (c) 2026 PBandDev)",
        "pools": pools,
        "sections": {name: sorted(tags) for name, tags in sorted(sections.items())},
        "exclusive": exclusive,
        "sensitive": sensitive,
        "explicit": explicit,
    }
    out = os.path.join(os.path.dirname(__file__), "..", "ResolutionForge", "prompt_director", "tag_groups.json")
    with open(out, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {os.path.normpath(out)}: " + ", ".join(f"{group} {len(tags)}" for group, tags in pools.items()) + f", sensitive {len(sensitive)}, explicit {len(explicit)}, sections {len(sections)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "unknown")
