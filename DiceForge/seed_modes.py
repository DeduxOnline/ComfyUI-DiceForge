import hashlib
import json
import logging
import math
import os
import random
import sqlite3
import threading
import time
import folder_paths
# Seed modes shared by the DiceForge nodes: how random picks change from one run to the next. Each picker picks from weighted options and
# returns the picked options, each with the picker to go on with inside it (for nested choices in CLIP Dual Text Encode).
class Picker:
    def pick_range(self, weighted, low, high):
        return self.pick(weighted, self.rng.randint(low, high), False) # Multi-pick: how many options, then which.
    def sub(self, text):
        return self # The picker to fill in a variable's value with.
    def lock(self, weighted, count_range, plain, locked):
        return [(option, self) for option in locked] # "{!a|b}": always the options marked with !, in every mode.
def stable_seed(*parts):
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:8], "big") # Unlike hash(), the same in every ComfyUI run.
DECK_LIMIT = 10000 # Cards in a deck at most: bigger weights are scaled down to fit (every option keeps a card), so 99999999::a can't hang the run.
def deck_cards(weighted):
    copies = [max(1, round(weight)) if weight > 0 else 0 for weight, _ in weighted] # Weight = copies of the option in the deck.
    if sum(copies) > DECK_LIMIT:
        total = sum(weight for weight, _ in weighted if weight > 0)
        copies = [max(1, round(weight / total * DECK_LIMIT)) if weight > 0 else 0 for weight, _ in weighted]
    return [option for (_, option), count in zip(weighted, copies) for _ in range(count)]
def avoid_first(deck, last):
    if deck and deck[0] == last:
        swap = next((index for index in range(1, len(deck) - 1) if deck[index] != last), None) # Never the last card, so the next deck can still check it.
        if swap is not None:
            deck[0], deck[swap] = deck[swap], deck[0]
    return deck
# random: every pick independent, from the seed (the same pick as before seed modes existed, so saved seeds give the same prompt).
class RandomPicker(Picker):
    def __init__(self, rng):
        self.rng = rng
    def pick(self, weighted, count, plain):
        if plain:
            return [(self.rng.choice([option for _, option in weighted]), self)]
        weighted, picked = list(weighted), []
        while weighted and len(picked) < count and sum(weight for weight, _ in weighted) > 0:
            index = self.rng.choices(range(len(weighted)), weights=[weight for weight, _ in weighted])[0]
            picked.append((weighted.pop(index)[1], self)) # Picked without repeats.
        return picked
    def lock(self, weighted, count_range, plain, locked):
        self.pick(weighted, 1, plain) if count_range is None else self.pick_range(weighted, *count_range) # Same randomness as without the lock, so the other choices keep their picks for this seed.
        return super().lock(weighted, count_range, plain, locked)
# deck: the seed is a position in a shuffled deck of the options, so with control after generate on increment every option comes once before any repeats,
# and a new shuffle each round, like dealing from a deck. Options inside a picked option move one step each time that option comes up. Fully reproducible from the seed.
class DeckPicker(Picker):
    def __init__(self, rng, position, draws):
        self.rng, self.position, self.draws = rng, position, draws
    @staticmethod
    def deck(cards, round_number):
        if len(cards) <= 2:
            round_number = 0 # Two options simply alternate.
        deck = list(cards)
        random.Random(stable_seed(cards, round_number)).shuffle(deck) # NOSONAR: picks prompt options from the seed (reproducible on purpose), not security.
        if round_number:
            last = list(cards)
            random.Random(stable_seed(cards, round_number - 1)).shuffle(last) # NOSONAR: as above.
            avoid_first(deck, last[-1]) # No repeat across the end of one round and the start of the next.
        return deck
    def pick(self, weighted, count, plain):
        cards = tuple(deck_cards(weighted))
        if not cards:
            return []
        key, distinct = (cards, self.position), len(set(cards))
        drawn, dealt = self.draws.get(key, (0, set())) # The same deck again in this run takes the next cards and skips the ones it already dealt
        position, picked, seen = self.position + drawn, [], set() # (also across the end of a round), so it doesn't repeat within the prompt.
        for _ in range(4 * len(cards)):
            if len(picked) == count:
                break
            if len(dealt) == distinct:
                dealt = set() # Every option came up in this run: start over.
            round_number, index = divmod(position, len(cards))
            card = self.deck(cards, round_number)[index]
            position += 1
            if card not in seen and card not in dealt:
                seen.add(card)
                dealt.add(card)
                picked.append((card, DeckPicker(self.rng, round_number, self.draws)))
        self.draws[key] = (position - self.position, dealt)
        return picked
    def lock(self, weighted, count_range, plain, locked):
        if count_range is not None:
            self.rng.randint(*count_range) # Same randomness as without the lock, for the multi-pick counts after it.
        return super().lock(weighted, count_range, plain, locked)
# Memory for shuffle, balanced and mutate: kept in a SQLite file in the ComfyUI user folder, so it survives restarts and doesn't fill up RAM (only the
# list being picked from is read). Delete the file to start over. The least recently used entries are forgotten past MEMORY_LIMIT. Besides where each
# list is now, it keeps where it was when each seed came, so a seed gives its picks again (recall).
MEMORY_FILE = os.path.join(folder_paths.get_user_directory(), "DiceForge", "seed_memory.sqlite")
MEMORY_LIMIT = 100000
class SeedMemory:
    def __init__(self, path):
        self.path, self.lock, self.connection, self.writes, self.opened = path, threading.Lock(), None, 0, None
    def identity(self):
        try:
            stat = os.stat(self.path)
        except OSError:
            return None
        return stat.st_dev, stat.st_ino
    def database(self):
        if self.connection is not None and self.identity() != self.opened:
            self.connection.close() # The file was deleted to start over, or replaced by another one: open what is there now.
            self.connection = None
        if self.connection is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.connection = sqlite3.connect(self.path, check_same_thread=False)
            self.opened = self.identity()
            self.connection.execute("CREATE TABLE IF NOT EXISTS memory (mode TEXT, key TEXT, value TEXT, used REAL, PRIMARY KEY (mode, key))")
        return self.connection
    # A query, with the lock held. A damaged file (not a database, or a malformed one) is kept aside and a new memory starts, instead of failing every
    # run; a busy or locked database is not damage and still raises.
    def execute(self, sql, parameters=()):
        try:
            return self.database().execute(sql, parameters)
        except sqlite3.DatabaseError as error:
            if isinstance(error, sqlite3.OperationalError):
                raise
            if self.connection is not None:
                self.connection.close()
                self.connection = None
            broken = f"{self.path}.broken-{int(time.time())}"
            if os.path.exists(self.path):
                os.replace(self.path, broken)
            logging.warning(f"[DiceForge] Seed memory: {self.path} is damaged ({error}). Kept as {broken}; starting a new memory.")
            return self.database().execute(sql, parameters)
    @staticmethod
    def key(*parts):
        return hashlib.sha256(repr(parts).encode()).hexdigest()
    def get(self, mode, key):
        with self.lock:
            row = self.execute("SELECT value FROM memory WHERE mode = ? AND key = ?", (mode, key)).fetchone()
        try:
            return json.loads(row[0]) if row else None
        except (TypeError, ValueError):
            return None # A damaged value: as if nothing was remembered.
    def set(self, mode, key, value):
        with self.lock:
            self.execute("INSERT OR REPLACE INTO memory VALUES (?, ?, ?, ?)", (mode, key, json.dumps(value), time.time()))
            self.writes += 1
    def save(self):
        with self.lock:
            if self.connection is not None and self.writes:
                self.execute("DELETE FROM memory WHERE rowid IN (SELECT rowid FROM memory ORDER BY used DESC LIMIT -1 OFFSET ?)", (MEMORY_LIMIT,))
                self.connection.commit() # Once per run, not per pick.
                self.writes = 0
MEMORY = SeedMemory(MEMORY_FILE)
# The remembered state a remembering mode (shuffle, balanced, mutate) picks from, and whether this is a seed that came before. A new seed picks from
# where the list is now and goes on from there; the state is also kept under that seed, so the same seed later picks from the same state again and,
# with its choices drawn from the seed, gives the same result (without moving the list on). occurrence: the same list picked again in one run.
# A picker without a seed (seed None) only uses the state of now, as before seeds counted.
def recall(mode, key, seed, occurrence=0):
    if seed is None:
        return MEMORY.get(mode, key), False
    snapshot = MEMORY.key(key, seed, occurrence)
    saved = MEMORY.get(f"{mode}@seed", snapshot)
    if isinstance(saved, dict) and "state" in saved:
        return saved["state"], True
    state = MEMORY.get(mode, key)
    MEMORY.set(f"{mode}@seed", snapshot, {"state": state})
    return state, False
# Base of shuffle and balanced: the seed, the random numbers drawn from it, and how often each list was picked from in this run.
class RememberingPicker(Picker):
    mode = ""
    def __init__(self, seed=None):
        self.seed, self.calls = seed, {}
        self.rng = random.Random() if seed is None else random.Random(stable_seed(self.mode, seed)) # NOSONAR: picks options, not security.
    def recall(self, key):
        occurrence = self.calls[key] = self.calls.get(key, -1) + 1
        state, replay = recall(self.mode, key, self.seed, occurrence)
        rng = self.rng if self.seed is None else random.Random(stable_seed(self.mode, self.seed, key, occurrence)) # NOSONAR: as above.
        return state, replay, rng
# A remembered shuffle state, or a new one when it is damaged (wrong shape, or cards that aren't in the list).
def shuffle_state(state, cards):
    fresh = {"order": None, "position": 0, "last": None, "previous": None, "pending": []}
    if not isinstance(state, dict) or set(fresh) - set(state):
        return fresh
    order, position, pending = state["order"], state["position"], state["pending"]
    if order is not None and (not isinstance(order, int) or isinstance(order, bool)):
        return fresh
    if not isinstance(position, int) or isinstance(position, bool) or not 0 <= position <= len(cards):
        return fresh
    if not isinstance(pending, list) or not all(isinstance(card, str) and card in cards for card in pending):
        return fresh
    return state
# shuffle: like shuffle in a music player. The node remembers where it is in a shuffled order of the options and picks the next one, so every option
# comes once before any repeats with any new seeds (increment or randomize). The same seed again gives the same picks (recall). The order is stored
# as the seed that shuffled it and a position, so even a long wildcard file takes a few bytes.
class ShufflePicker(RememberingPicker):
    mode = "shuffle"
    def pick(self, weighted, count, plain):
        cards = deck_cards(weighted)
        key = MEMORY.key(cards)
        remembered, replay, rng = self.recall(key)
        state = shuffle_state(remembered, cards)
        decks, picked, skipped = {}, [], []
        for _ in range(2 * len(cards)):
            if len(picked) == count:
                break
            if state["pending"]:
                card = state["pending"].pop(0)
            else:
                if state["order"] is None or state["position"] >= len(cards):
                    state.update(order=rng.getrandbits(63), position=0, previous=state["last"]) # New round.
                if state["order"] not in decks:
                    deck = list(cards)
                    random.Random(state["order"]).shuffle(deck) # NOSONAR: a shuffled order of prompt options, not security.
                    decks[state["order"]] = avoid_first(deck, state["previous"])
                card = decks[state["order"]][state["position"]]
                state["position"] += 1
            state["last"] = card
            (skipped if card in picked else picked).append(card)
        state["pending"] = skipped + state["pending"] # Skipped duplicates of a multi-pick come first next time.
        if cards and not replay:
            MEMORY.set("shuffle", key, state)
        return [(card, self) for card in picked]
# balanced: like the pseudo-random distribution in games. Each option earns credit for every pick (its share of the weights) and spends 1 when picked;
# its chance is its weight x e^(5 x credit). An option just picked gets a low chance, one missed for a while a higher one, so repeats are rare but
# possible, nothing waits too long, and in the long run every option comes exactly as often as its weight says. The node remembers the credits
# (in the memory file) over new seeds; the same seed again gives the same picks (recall).
BALANCE_STRENGTH = 5.0 # Higher: fewer repeats, less randomness.
def valid_credits(credits, size):
    return isinstance(credits, list) and len(credits) == size and all(isinstance(credit, (int, float)) and not isinstance(credit, bool) and abs(credit) <= 100 for credit in credits) # Credits stay within a few units; far beyond is damage.
class BalancedPicker(RememberingPicker):
    mode = "balanced"
    def pick(self, weighted, count, plain):
        key = MEMORY.key(weighted)
        total = sum(weight for weight, _ in weighted) or 1
        credits, replay, rng = self.recall(key)
        credits = credits if valid_credits(credits, len(weighted)) else [0.0] * len(weighted) # None yet, or damaged: start over.
        candidates, picked = list(range(len(weighted))), []
        while candidates and len(picked) < count:
            weights = [weighted[index][0] * math.exp(min(BALANCE_STRENGTH * credits[index], 600.0)) for index in candidates] # Capped: no overflow.
            if sum(weights) <= 0:
                break
            index = candidates.pop(rng.choices(range(len(candidates)), weights=weights)[0])
            picked.append(index)
            credits = [credit + weighted[option][0] / total - (option == index) for option, credit in enumerate(credits)]
        if not replay:
            MEMORY.set("balanced", key, [round(credit, 6) for credit in credits])
        return [(weighted[index][1], self) for index in picked]
# Seed modes of the resolution nodes (CLIP Dual Text Encode has these without sequential, plus combinations and mutate).
SEED_MODES = ["random", "deck", "shuffle", "balanced", "sequential"]
SEED_MODE_TOOLTIP = ("How random sizes change from run to run.\n"
    "random: every pick is independent, so the same size can come up again soon.\n"
    "deck: the seed steps through a shuffled order; with control after generate on increment, every size comes once before any repeats. Reproducible.\n"
    "shuffle: like shuffle in a music player, the node remembers the sizes already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same size again.\n"
    "balanced: a size just picked gets a low chance, and sizes not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same size again.\n"
    "sequential: the seed is the position in the list, so seeds 0, 1, 2... go through the sizes in order. Reproducible.\n"
    "Random Chaos: the aspect range is split into equal parts that take turns (in order for sequential), with a random ratio inside each part.")
# Seed mode tooltip for a node picking one of a list of things (files for the random loaders).
def seed_mode_tooltip(things):
    return (f"How the pick changes from run to run.\n"
        f"random: every pick is independent, so the same one can come up again soon.\n"
        f"deck: the seed steps through a shuffled order of the {things}; with control after generate on increment, every one comes once before any repeats. Reproducible.\n"
        f"shuffle: like shuffle in a music player, the node remembers the {things} already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same pick again.\n"
        f"balanced: one just picked gets a low chance, and those not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same pick again.\n"
        f"sequential: the seed is the position in the list (sorted by name), so seeds 0, 1, 2... go through the {things} in order. Reproducible.")
# Picker for a seed mode (the modes every node has; CLIP Dual Text Encode adds its own), or None for sequential.
def make_picker(seed_mode, seed):
    if seed_mode == "deck":
        return DeckPicker(random.Random(seed), seed, {})
    if seed_mode == "shuffle":
        return ShufflePicker(seed)
    if seed_mode == "balanced":
        return BalancedPicker(seed)
    if seed_mode == "sequential":
        return None
    return RandomPicker(random.Random(seed)) # Seed behavior for reproducible picks.
# One of the labels, by the seed mode: sequential goes through them in order (the seed is the position), the other modes pick as their picker does.
def pick_label(labels, picker, seed):
    if picker is None:
        return labels[seed % len(labels)]
    return picker.pick([(1.0, label) for label in labels], 1, True)[0][0]
# A value between low and high. random: uniform, as before seed modes existed. The other modes split the range into `parts` equal parts and pick a part
# like a label (so the values spread over the whole range run after run), then a uniform value inside it; sequential takes the middle of each part in order.
def pick_in_range(low, high, parts, picker, seed, name):
    if isinstance(picker, RandomPicker):
        return picker.rng.uniform(low, high)
    labels = [f"{name} {part + 1}/{parts}" for part in range(parts)]
    part = labels.index(pick_label(labels, picker, seed))
    width = (high - low) / parts
    if picker is None:
        return low + width * (part + 0.5)
    return picker.rng.uniform(low + width * part, low + width * (part + 1))
# One of `count` positions (0 to count - 1). random: uniform; sequential: the seed is the position. The other modes treat each position as an option
# up to INDEX_LIMIT positions, so every one comes once before any repeats; past that they take turns between INDEX_PARTS equal parts of the range
# (like Random Chaos), with a random position inside the part.
INDEX_LIMIT = 1000
INDEX_PARTS = 100
def pick_index(count, picker, seed, name):
    if isinstance(picker, RandomPicker):
        return picker.rng.randrange(count)
    if picker is None:
        return seed % count
    if count <= INDEX_LIMIT:
        return int(pick_label([f"{name} #{index}" for index in range(count)], picker, seed).rpartition("#")[2])
    labels = [f"{name} {part + 1}/{INDEX_PARTS}" for part in range(INDEX_PARTS)]
    part = labels.index(pick_label(labels, picker, seed))
    return picker.rng.randrange(part * count // INDEX_PARTS, (part + 1) * count // INDEX_PARTS)
# Modes that remember earlier runs (in the memory file). Like every mode, they give the same result for the same seed, so ComfyUI's cache can stand
# in for a run with the same seed and inputs.
REMEMBERING_MODES = ("shuffle", "balanced", "mutate")
