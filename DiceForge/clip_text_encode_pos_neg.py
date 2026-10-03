import fnmatch
import hashlib
import itertools
import logging
import math
import os
import random
import re
import folder_paths
import yaml
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .seed_modes import MEMORY, Picker, RandomPicker, DeckPicker, ShufflePicker, BalancedPicker, fingerprint
# Wildcards: __name__ in a prompt is replaced by a random line of name.txt from the wildcards folders (ComfyUI/models/wildcards by default, more can be added in extra_model_paths.yaml).
folder_paths.add_model_folder_path("wildcards", os.path.join(folder_paths.models_dir, "wildcards"), is_default=True)
# * and ? match several files (__hair/*__, __*/color__); ${name} takes a variable's value (__outfit/${gender}__; \x00name\x00 once the prompt is scanned).
# Names can have single spaces inside, like file names (__hair color__), but not at the start or end, so "__ text__" stays text.
NAME_PART = r"(?:[\w\-./*?]|\$\{\w+\}|\x00\w+\x00)+?"
WILDCARD_PATTERN = re.compile(rf"__({NAME_PART}(?: {NAME_PART})*?)__")
NAME_VARIABLE = re.compile(r"\$\{(\w+)\}|\x00(\w+)\x00")
MAX_DEPTH = 50 # Nesting limit for wildcards and {a|b} choices, to stop wildcards that include each other forever.
WILDCARD_FILES = (".txt", ".yaml", ".yml")
# Wildcard .txt file lookup: name may contain subfolders (__colors/warm__ -> colors/warm.txt), and must stay inside a wildcards folder.
def find_wildcard(name):
    for folder in folder_paths.get_folder_paths("wildcards"):
        folder = os.path.abspath(folder)
        path = os.path.abspath(os.path.join(folder, *name.split("/")) + ".txt")
        if path.startswith(folder + os.sep) and os.path.isfile(path):
            return path
    return None
# Wildcard files in the wildcards folders, in folder order: (subfolder prefix like "hair/", file name, path).
def wildcard_files():
    for folder in folder_paths.get_folder_paths("wildcards"):
        for root, dirs, files in os.walk(folder):
            dirs.sort()
            relative = os.path.relpath(root, folder).replace("\\", "/")
            for name in sorted(files):
                if name.lower().endswith(WILDCARD_FILES):
                    yield "" if relative == "." else relative + "/", name, os.path.join(root, name)
# Wildcard files signature (paths and modification times), so the node runs again when a wildcard file changes.
def wildcards_signature():
    return hashlib.sha256(repr([(path, os.path.getmtime(path)) for _prefix, _name, path in wildcard_files()]).encode()).hexdigest()
# YAML wildcards (the Dynamic Prompts and Impact Pack format): nested keys lead to lists of lines. {hair: {color: [red, blue]}} in a file of the root
# wildcards folder is __hair/color__ (in a subfolder, the folder comes first: styles/pack.yaml gives __styles/hair/color__). A single text counts as one line.
def yaml_wildcards(data, name):
    if isinstance(data, dict):
        for key, value in data.items():
            yield from yaml_wildcards(value, f"{name}/{key}" if name else str(key))
    elif name and data is not None:
        items = data if isinstance(data, list) else [data]
        yield name, [str(item).strip() for item in items if item is not None and not isinstance(item, (dict, list))]
# YAML lines are text as written: "yes", "no", "12:30" or "0123" stay as they are instead of becoming True, False, 750 or 83 (YAML 1.1 rules);
# only null (~, null, an empty item) means no line.
class TextLoader(yaml.SafeLoader):
    yaml_implicit_resolvers = {first: [(tag, pattern) for tag, pattern in resolvers if tag == "tag:yaml.org,2002:null"]
                               for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()}
# Wildcard index: every wildcard name ("hair/color") and where it comes from ({"path"} for a .txt file, {"path", "lines"} for a yaml key). A name in an
# earlier folder hides the same name in a later one, and a .txt file hides a yaml key of the same name. Rebuilt when a file changes; the node checks
# that once per run, and a name that is not found checks again.
index_cache = {"signature": None, "entries": {}}
def wildcard_index(refresh=False):
    if refresh or index_cache["signature"] is None:
        signature = wildcards_signature()
        if signature != index_cache["signature"]:
            files = list(wildcard_files())
            entries = {}
            for prefix, name, path in files:
                if name.lower().endswith(".txt"):
                    entries.setdefault(prefix + name[:-4], {"path": path})
            for prefix, name, path in files:
                if not name.lower().endswith(".txt"):
                    try:
                        with open(path, encoding="utf-8-sig") as file:
                            data = yaml.load(file, Loader=TextLoader)
                    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
                        logging.warning(f"[DiceForge] Wildcards: skipping {path}, it is not valid UTF-8 YAML: {error}")
                        continue
                    for key, lines in yaml_wildcards(data, prefix.rstrip("/")):
                        entries.setdefault(key, {"path": path, "lines": lines})
            index_cache.update(signature=signature, entries=entries)
    return index_cache["entries"]
# Every wildcard name, sorted.
def wildcard_names(refresh=False):
    return sorted(wildcard_index(refresh), key=str.lower)
# Wildcard text files: UTF-8, with or without the BOM Windows Notepad adds. A file in another encoding, or one that can't be read, is a clear error.
def read_text_lines(path):
    try:
        with open(path, encoding="utf-8-sig") as file:
            return [line.rstrip("\r\n") for line in file]
    except UnicodeDecodeError as error:
        raise ValueError(f"Wildcard file {path} is not UTF-8 text ({error.reason} at byte {error.start}): save it as UTF-8.") from None
    except OSError as error:
        raise ValueError(f"Wildcard file {path} can't be read: {error.strerror or error}.") from None
# The lines of an index entry, with empty lines and # comments skipped.
def entry_lines(entry):
    lines = entry["lines"] if "lines" in entry else [line.strip() for line in read_text_lines(entry["path"])]
    return [line for line in lines if line and not line.startswith("#")]
# Wildcard reading: the lines of one wildcard, as written ("3::red" keeps its weight; see weighted_lines). A name with * or ? (__hair/*__: every file
# in hair and its subfolders; __*/color__: every color file) joins the lines of all the wildcards it matches, in name order.
def read_wildcard(name):
    if "*" in name or "?" in name:
        matches = [match for match in wildcard_names() if fnmatch.fnmatchcase(match, name)] or [match for match in wildcard_names(refresh=True) if fnmatch.fnmatchcase(match, name)]
        if not matches:
            raise ValueError(f"Wildcard __{name}__ matches no wildcard files.")
        options = []
        for match in matches:
            try:
                options += read_wildcard(match)
            except ValueError:
                pass # An empty file among the matches adds nothing.
        if not options:
            raise ValueError(f"Wildcard __{name}__: the files it matches ({', '.join(matches)}) have no lines to choose from.")
        return options
    entry = wildcard_index().get(name) or wildcard_index(refresh=True).get(name)
    if entry is None:
        folders = ", ".join(folder_paths.get_folder_paths("wildcards"))
        raise ValueError(f"Wildcard __{name}__ not found: put {name}.txt (or a yaml file with that key) in one of the wildcards folders ({folders}).")
    options = entry_lines(entry)
    if not options:
        raise ValueError(f"Wildcard __{name}__ is empty: {entry['path']} has no lines to choose from.")
    return options
# Line weights in wildcard files, like in choices: "3::blonde hair" comes 3 times as often as a line without a weight, "0::..." never.
def weighted_lines(name):
    weighted = [(option_weight(found.group(1)), found.group(2).strip()) if (found := OPTION_WEIGHT.match(line)) else (1.0, line) for line in read_wildcard(name)]
    if not any(weight > 0 for weight, _ in weighted):
        raise ValueError(f"Wildcard __{name}__: every line has weight 0, so there is nothing to choose from.")
    return weighted
# Variables in wildcard names: __outfit/${gender}__ reads outfit/male or outfit/female, from the value of ${gender}. Wildcards are filled in after their
# prompt is scanned, so the variable can be set anywhere in the same prompt (or in the positive prompt, for the negative). variables=None (counting
# combinations) cannot know it.
def wildcard_name(name, variables):
    def value(match):
        variable = match.group(1) or match.group(2)
        shown = NAME_VARIABLE.sub(lambda found: "${" + (found.group(1) or found.group(2)) + "}", name)
        if variables is None:
            raise ValueError(f"Seed mode combinations cannot count __{shown}__: the wildcard it reads depends on ${{{variable}}}. Use another seed mode, or a wildcard name without a variable.")
        if variable not in variables:
            raise ValueError(f"Wildcard __{shown}__ uses ${{{variable}}}, which is not set: set ${{{variable}=...}} in the same prompt (or in the positive prompt, for the negative).")
        return fill_variables(variables[variable], variables).strip()
    return NAME_VARIABLE.sub(value, name)
# Choice block parser for {a|b|{c|d}}, same syntax as the ComfyUI frontend dynamic prompts: returns the options and the position after the closing brace.
def parse_choice(text, i):
    options, choice, depth = [], "", 0
    while i < len(text):
        char = text[i]
        i += 1
        if char == "\\" and i < len(text):
            choice += char + text[i]
            i += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            if not depth:
                break
            depth -= 1
        elif char == "|" and not depth:
            options.append(choice)
            choice = ""
            continue
        choice += char
    options.append(choice)
    return options, i
# Choice options with the sd-dynamic-prompts extras: "{2$$a|b|c}" picks 2 different options (also "1-3", "-2", "2-"), "{2$$ and $$a|b}" sets the separator
# (", " by default), and "2::a" gives an option weight 2 (1 by default). Returns the weighted options, the count range (None for a single pick) and the separator.
# The separator has no braces, so a multi-pick as the first option ({2$${2$$a|b}|c}) stays an option.
CHOICE_COUNT = re.compile(r"^\s*(\d+(?:-\d*)?|-\d+)\$\$(?:([^{}]*?)\$\$)?(.*)$", re.S)
OPTION_WEIGHT = re.compile(r"^\s*(\d+(?:\.\d+)?)::(.*)$", re.S)
WEIGHT_LIMIT = 1e12 # Bigger weights count as this, so a long run of digits can't make an infinite weight.
def option_weight(digits):
    return min(float(digits), WEIGHT_LIMIT)
# A multi-pick whose only option is a wildcard picks from its lines (sd-dynamic-prompts style): {2$$__color__} gives 2 different colors.
def parse_options(options, variables=None):
    count_range, separator = None, ", "
    match = CHOICE_COUNT.match(options[0])
    if match:
        low, dash, high = match.group(1).partition("-")
        options = [match.group(3), *options[1:]]
        if len(options) == 1 and (wildcard := WILDCARD_PATTERN.fullmatch(options[0].strip())):
            options = read_wildcard(wildcard_name(wildcard.group(1), variables))
        separator = match.group(2) if match.group(2) is not None else separator
        low = int(low or 0)
        high = (int(high) if high else len(options)) if dash else low
        count_range = (min(low, len(options)), min(max(low, high), len(options)))
    weighted, locked = [], []
    for option in options:
        lock = option.lstrip().startswith("!")
        option = option.lstrip()[1:] if lock else option
        found = OPTION_WEIGHT.match(option)
        weight, option = (option_weight(found.group(1)), found.group(2)) if found else (1.0, option)
        if option.lstrip().startswith("!") and not lock:
            lock, option = True, option.lstrip()[1:] # "3::!a" works like "!3::a".
        weighted.append((weight, option))
        if lock:
            locked.append(option)
    return weighted, count_range, separator, locked
def pick_choices(options, picker, variables):
    weighted, count_range, separator, locked = parse_options(options, variables)
    plain = count_range is None and all(weight == 1.0 for weight, _ in weighted) # NOSONAR: 1.0 is the exact default weight, never computed.
    if locked:
        return picker.lock(weighted, count_range, plain, locked), separator
    if count_range is None:
        return picker.pick(weighted, 1, plain), separator
    return picker.pick_range(weighted, *count_range), separator
# Variables: "${name=value}" fills in value once (choices and wildcards included) and outputs nothing; "${name}" outputs that value anywhere in either prompt.
VARIABLE = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?:=!?(.*))?$", re.S)
VARIABLE_USE = re.compile("\x00(\\w+)\x00") # Placeholder for "${name}", filled in after both prompts are expanded, so a variable can be used before it's set.
def parse_variable(text, i):
    options, end = parse_choice(text, i + 1)
    found = VARIABLE.match("|".join(options))
    return (found.group(1), found.group(2) and found.group(2).strip(), end) if found else None
def fill_variables(text, variables, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("Variables are nested too deep: check for variables that include each other.")
    def value(match):
        if match.group(1) not in variables:
            raise ValueError(f"Variable ${{{match.group(1)}}} is used but never set: add ${{{match.group(1)}=...}} to a prompt or a wildcard file.")
        return fill_variables(variables[match.group(1)], variables, depth + 1)
    return VARIABLE_USE.sub(value, text)
# Seed modes: how choices and wildcards are picked from one run to the next (shared pickers in seed_modes.py, plus combinations and mutate below).
SEED_MODES = ["random", "deck", "shuffle", "balanced", "combinations", "mutate"]
# combinations: the seed numbers every combination of the options in both prompts (nested choices and wildcards included), so seeds 0, 1, 2... go
# through all of them once, then start over. The first choice changes fastest. Weights only matter as 0 (never); multi-picks count every set of options.
COMBINATION_LIMIT = 1000000 # Sets of options a multi-pick with varying options may list; more than this is an error instead of a long wait.
def count_combinations(text, memo, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("Wildcards are nested too deep: check for wildcard files that include each other.")
    if text not in memo:
        total, literal, i = 1, "", 0
        while i < len(text):
            char = text[i]
            i += 1
            if char == "\\" and i < len(text):
                literal += char + text[i]
                i += 1
            elif char == "{":
                options, i = parse_choice(text, i)
                weighted, count_range, _, locked = parse_options(options)
                total *= math.prod(count_combinations(option, memo, depth + 1) for option in locked) if locked else choice_combinations(weighted, count_range, memo, depth)
                literal += "\x01" # A choice breaks a wildcard name in two, as in expand().
            elif char == "$" and text.startswith("{", i) and (variable := parse_variable(text, i)):
                _name, value, i = variable
                total *= count_combinations(value, memo, depth + 1) if value is not None else 1
                literal += "\x01" if value is not None else f"\x00{_name}\x00" # A variable used in a wildcard name is caught by wildcard_name().
            else:
                literal += char
        for match in WILDCARD_PATTERN.finditer(literal):
            total *= choice_combinations(weighted_lines(wildcard_name(match.group(1), None)), None, memo, depth)
        memo[text] = total
    return memo[text]
def option_combinations(weighted, memo, depth):
    return [(option, count_combinations(option, memo, depth + 1)) for weight, option in weighted if weight > 0]
def option_sets(options, low, high):
    for size in range(low, high + 1):
        for subset in itertools.combinations(options, size):
            yield subset, math.prod(combos for _, combos in subset)
def choice_combinations(weighted, count_range, memo, depth):
    options = option_combinations(weighted, memo, depth)
    if count_range is None:
        return sum(combos for _, combos in options) or 1
    high = min(count_range[1], len(options))
    low = min(count_range[0], high)
    sets = sum(math.comb(len(options), size) for size in range(low, high + 1))
    if all(combos == 1 for _, combos in options):
        return sets
    if sets > COMBINATION_LIMIT:
        raise ValueError(f"Too many combinations to list in a multi-pick of {len(options)} options with choices inside: use fewer options or a smaller count.")
    return sum(combos for _, combos in option_sets(options, low, high)) or 1
def unrank_set(rank, size, count):
    picked, start = [], 0
    for remaining in range(count, 0, -1):
        for index in range(start, size):
            block = math.comb(size - index - 1, remaining - 1)
            if rank < block:
                picked.append(index)
                start = index + 1
                break
            rank -= block
    return picked
class CombinationPicker(Picker):
    def __init__(self, index, memo, depth=0):
        self.index, self.memo, self.depth = index, memo, depth
    def take(self, combos):
        index, self.index = self.index % combos, self.index // combos # One digit of the seed per choice, in a mixed-radix number.
        return index
    def child(self, index):
        return CombinationPicker(index, self.memo, self.depth + 1)
    def pick(self, weighted, count, plain):
        options = option_combinations(weighted, self.memo, self.depth)
        index = self.take(sum(combos for _, combos in options) or 1)
        for option, combos in options:
            if index < combos:
                return [(option, self.child(index))]
            index -= combos
        return []
    def pick_range(self, weighted, low, high):
        options = option_combinations(weighted, self.memo, self.depth)
        high = min(high, len(options))
        low = min(low, high)
        index = self.take(choice_combinations(weighted, (low, high), self.memo, self.depth))
        if all(combos == 1 for _, combos in options):
            for size in range(low, high + 1):
                if index < math.comb(len(options), size):
                    return [(options[picked][0], self.child(0)) for picked in unrank_set(index, len(options), size)]
                index -= math.comb(len(options), size)
            return []
        for subset, combos in option_sets(options, low, high):
            if index < combos:
                picked = []
                for option, option_combos in subset:
                    picked.append((option, self.child(index % option_combos)))
                    index //= option_combos
                return picked
            index -= combos
        return []
    def sub(self, text):
        return self.child(self.take(count_combinations(text, self.memo, self.depth + 1)))
    def lock(self, weighted, count_range, plain, locked):
        return [(option, self.sub(option)) for option in locked] # A locked choice counts once, so it doesn't repeat combinations.
# mutate: the first run picks at random; every next run keeps the last prompt and changes just one choice (a different option), to explore variations
# of a good result. The node remembers the last picks for these prompts (in the memory file), whatever the seed. Not reproducible.
class MutatePicker(Picker):
    def __init__(self, state, path=()):
        self.state, self.path, self.ordinal, self.rng = state, path, 0, state["rng"]
    def address(self):
        self.ordinal += 1
        return self.path + (self.ordinal - 1,) # Where this choice is: the choices and options above it, and its place among its siblings.
    def lock(self, weighted, count_range, plain, locked):
        address = self.address()
        self.state["now"][address] = (locked, 1) # Never the one to change.
        return [(option, MutatePicker(self.state, address + (option,))) for option in locked]
    # The last picks of this choice are kept while they still fit it: every option still there, and as many as it picks now (a wildcard file that
    # grew from 1 to 10 lines gives a {8$$__file__} 8 lines again, not the 1 it had).
    def decide(self, weighted, fresh, low=1, high=1):
        address = self.address()
        options = [option for weight, option in weighted if weight > 0]
        previous = self.state["last"].get(address, (None, 0))[0]
        fits = previous is not None and all(option in options for option in previous) and min(low, len(options)) <= len(previous) <= min(high, len(options))
        if address != self.state["mutate"] and fits:
            picked = previous
        else:
            picked = fresh()
            for _ in range(20 if address == self.state["mutate"] else 0):
                if picked != previous:
                    break
                picked = fresh()
        self.state["now"][address] = (picked, len(options))
        return [(option, MutatePicker(self.state, address + (option,))) for option in picked]
    def pick(self, weighted, count, plain):
        return self.decide(weighted, lambda: [option for option, _ in RandomPicker(self.rng).pick(weighted, count, plain)], count, count)
    def pick_range(self, weighted, low, high):
        return self.decide(weighted, lambda: [option for option, _ in RandomPicker(self.rng).pick_range(weighted, low, high)], low, high)
# The last picks of mutate as remembered: {address: (picked options, option count)}; damaged entries are left out (those choices pick afresh).
def mutate_memory(entries):
    last = {}
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, list) and len(entry) == 3 and isinstance(entry[0], list) and isinstance(entry[1], list) and isinstance(entry[2], int):
            if all(isinstance(part, (int, str)) for part in entry[0]):
                last[tuple(entry[0])] = (entry[1], entry[2])
    return last
# Comma cleanup after filling in: an empty option leaves "a, , b" or a trailing comma; this makes it "a, b".
# Runs of spaces are collapsed first, so the other patterns only meet single spaces: linear time even for a prompt with thousands of spaces in a row.
def tidy_commas(text):
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]?,(?:[ \t]?,)+", ",", text)
    text = re.sub(r"[ \t],", ",", text)
    text = re.sub(r"(^|\n)[ \t]?,[ \t]?", r"\1", text)
    return strip_commas(text)
def strip_commas(text):
    start, end = 0, len(text)
    while start < end and (text[start].isspace() or text[start] == ","):
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] == ","):
        end -= 1
    return text[start:end]
# Space cleanup (the trim input): no spaces at the start or end of a line, one space between words, none before , . ; : ! ? ) or after (, and at most
# one empty line in a row. Only spaces change, so the words and weights stay as written.
def trim_spaces(text):
    text = re.sub(r"[ \t]+", " ", text) # First: single spaces only, so the patterns below take linear time.
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r" ([,.;:!?)])", r"\1", text)
    text = re.sub(r"\( ", "(", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
# Prompt expansion: picks {a|b} choices and sets ${name=value} variables, then replaces __name__ wildcards, expanding the picked text again so choices
# and wildcards can nest.
def expand(text, picker, depth, variables):
    if depth > MAX_DEPTH:
        raise ValueError("Wildcards are nested too deep: check for wildcard files that include each other.")
    result, i = "", 0
    while i < len(text):
        char = text[i]
        i += 1
        if char == "\\" and i < len(text):
            result += char + text[i]
            i += 1
        elif char == "{":
            options, i = parse_choice(text, i)
            picked, separator = pick_choices(options, picker, variables)
            result += separator.join(expand(option, child, depth + 1, variables) for option, child in picked)
        elif char == "$" and text.startswith("{", i) and (variable := parse_variable(text, i)):
            name, value, i = variable
            if value is None:
                result += f"\x00{name}\x00"
            else:
                variables[name] = expand(value, picker.sub(value), depth + 1, variables)
        else:
            result += char
    def wildcard(match):
        weighted = weighted_lines(wildcard_name(match.group(1), variables))
        return expand(*picker.pick(weighted, 1, all(weight == 1.0 for weight, _ in weighted))[0], depth + 1, variables) # NOSONAR: as above.
    return WILDCARD_PATTERN.sub(wildcard, result)
# Full prompt processing: strips // and /* */ comments like the frontend, expands choices and wildcards, fills in variables (shared by both prompts),
# unescapes \{ \} \| \!, then tidies commas. Wildcard names are kept whole: the /* of __hair/*__ does not start a comment.
def strip_comments(text):
    return re.sub(r"(" + WILDCARD_PATTERN.pattern + r")|/\*[\s\S]*?\*/|//.*", lambda match: match.group(1) or "", text)
def resolve_prompts(prompts, picker):
    variables = {}
    expanded = [expand(strip_comments(text), picker, 0, variables) for text in prompts]
    return [tidy_commas(re.sub(r"\\([{}|!])", r"\1", fill_variables(text, variables))) for text in expanded]
# Node schema (V3 / Nodes 2.0) like CLIP Text Encode (Prompt), but with a positive prompt on top, a negative prompt below, and one conditioning output for each. Both prompts support {a|b} choices and __name__ wildcards, picked from the seed.
class CLIPTextEncodePositiveNegative(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="CLIPTextEncodePositiveNegative",
            display_name="CLIP Dual Text Encode",
            category="DiceForge/conditioning",
            description="Encodes a positive and a negative prompt with the same CLIP model, outputting a conditioning and the filled-in text for each (without a CLIP, just the text, for other text encoders). Supports {a|b} choices, __name__ wildcards and ${name} variables, picked from the seed.",
            search_aliases=["text", "prompt", "positive prompt", "negative prompt", "encode text", "text encoder", "encode prompt", "wildcards", "dynamic prompts"],
            inputs=[
                io.String.Input(
                    "positive",
                    multiline=True,
                    tooltip="The positive prompt: what the image should contain. Supports {a|b} choices, __name__ wildcards and ${name=value} / ${name} variables.",
                ),
                io.String.Input(
                    "negative",
                    multiline=True,
                    tooltip="The negative prompt: what the image should avoid. Supports {a|b} choices, __name__ wildcards and ${name=value} / ${name} variables.",
                    advanced=True, # Usually set once: under Show advanced inputs, with the positive prompt in view.
                ),
                io.Clip.Input(
                    "clip",
                    optional=True,
                    tooltip="The CLIP model used for encoding both prompts. Leave it unconnected to use the node for the text only (positive_text and negative_text), for example with a Flux or SD3 text encoder.",
                ),
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Seed for {a|b} choices and __name__ wildcards. The same seed always gives the same prompts (except in shuffle, balanced and mutate modes).",
                    advanced=True,
                ),
                io.Combo.Input(
                    "seed_mode",
                    options=SEED_MODES,
                    default="random",
                    tooltip="How choices and wildcards change from run to run.\n"
                    "random: every pick is independent, so the same option can come up again soon.\n"
                    "deck: the seed steps through a shuffled order of the options; with control after generate on increment, every option comes once before any repeats. Reproducible.\n"
                    "shuffle: like shuffle in a music player, the node remembers the options already used and picks from the rest, whatever the seed; remembered in a file, so it continues after a restart. Not reproducible.\n"
                    "balanced: an option just picked gets a low chance, and options not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file, so it continues after a restart. Not reproducible.\n"
                    "combinations: the seed numbers every combination of the options, so seeds 0, 1, 2... go through all of them once (the console shows how many). Reproducible.\n"
                    "mutate: keeps the last prompt and changes just one choice each run, to explore variations of a good result. Remembered in a file, so it continues after a restart. Not reproducible.",
                    advanced=True,
                ),
                io.Boolean.Input(
                    "trim",
                    default=True,
                    tooltip="Remove extra spaces from both prompts: at the start and end of lines, double spaces, spaces before , . ; : ! ? ) and after (, and extra empty lines.",
                    advanced=True,
                ),
            ],
            has_intermediate_output=True, # The prompts of the last run reach the node's preview also when the node comes from the cache.
            # Outputs for the node: positive and negative conditioning, then the prompts as encoded (with choices and wildcards filled in).
            outputs=[
                io.Conditioning.Output(display_name="positive", tooltip="Conditioning from the positive prompt."),
                io.Conditioning.Output(display_name="negative", tooltip="Conditioning from the negative prompt."),
                io.String.Output(display_name="positive_text", tooltip="The positive prompt as encoded: choices, wildcards and variables filled in. Connect it to another text encoder (Flux, SD3...) or a Save Image file name."),
                io.String.Output(display_name="negative_text", tooltip="The negative prompt as encoded: choices, wildcards and variables filled in."),
            ],
        )
    # Method to run the node again when a wildcard file changes, even if the inputs are the same.
    @classmethod
    def fingerprint_inputs(cls, seed_mode="random", **kwargs):
        return wildcards_signature(), fingerprint(seed_mode) # shuffle, balanced and mutate give a new prompt every run, so they never use the cache.
    # Encoding method, same as CLIP Text Encode (Prompt).
    @staticmethod
    def encode(clip, text):
        tokens = clip.tokenize(text)
        return clip.encode_from_tokens_scheduled(tokens)
    # Main method to fill in choices and wildcards from the seed, encode both prompts, and return the conditioning and the final prompts.
    @classmethod
    def execute(cls, positive, negative, clip=None, seed=0, seed_mode="random", trim=True):
        note = ""
        wildcard_index(refresh=True) # Wildcard files added or changed since the last run.
        if seed_mode == "combinations":
            memo = {}
            total = math.prod(count_combinations(strip_comments(text), memo) for text in (positive, negative))
            picker = CombinationPicker(seed % total, memo)
            note = f", combination {seed % total + 1} of {total}"
        elif seed_mode == "mutate":
            key = MEMORY.key(positive, negative)
            last = mutate_memory(MEMORY.get("mutate", key))
            rng = random.Random() # NOSONAR: picks prompt options, not security.
            changeable = [address for address, (_picked, options) in last.items() if options > 1]
            state = {"rng": rng, "last": last, "now": {}, "mutate": rng.choice(changeable) if changeable else None}
            picker = MutatePicker(state)
        elif seed_mode == "shuffle":
            picker = ShufflePicker()
        elif seed_mode == "balanced":
            picker = BalancedPicker()
        elif seed_mode == "deck":
            picker = DeckPicker(random.Random(seed), seed, {})
        else:
            picker = RandomPicker(random.Random(seed)) # Seed behavior for reproducible choices and wildcards.
        positive_text, negative_text = resolve_prompts((positive, negative), picker)
        if trim:
            positive_text, negative_text = trim_spaces(positive_text), trim_spaces(negative_text)
        if seed_mode == "mutate":
            MEMORY.set("mutate", key, [[list(address), picked, options] for address, (picked, options) in state["now"].items()])
        MEMORY.save()
        # Logging the prompts when choices or wildcards changed them, for debugging and verification purposes.
        if (positive_text, negative_text) != (positive, negative):
            logging.info(f"[DiceForge] CLIP Dual Text Encode | Seed: {seed} ({seed_mode}{note}) | Positive: {positive_text} | Negative: {negative_text}")
        # The prompts as encoded, for the node's preview in the page (web/prompt_preview.js), with the seed and mode they came from.
        shown = {"dice_forge_prompts": [{"positive": positive_text, "negative": negative_text, "seed": seed, "seed_mode": seed_mode, "note": note.lstrip(", ")}]}
        if clip is None:
            return io.NodeOutput(None, None, positive_text, negative_text, ui=shown) # No CLIP: only the text, for other text encoders.
        return io.NodeOutput(cls.encode(clip, positive_text), cls.encode(clip, negative_text), positive_text, negative_text, ui=shown)
# Extension entry point for ComfyUI V3 node registration.
class CLIPTextEncodePositiveNegativeExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [CLIPTextEncodePositiveNegative]
async def comfy_entrypoint():
    return CLIPTextEncodePositiveNegativeExtension()
