# Invariants of the seed modes (DiceForge/seed_modes.py), checked on many generated inputs: what every pick must satisfy whatever the options,
# weights, counts and seeds, and the long-run promises of deck, shuffle and balanced.
import itertools
import json
import math
import random
import threading
from collections import Counter
import pytest
from hypothesis import assume, given, settings, strategies as st
from DiceForge import seed_modes
from DiceForge.seed_modes import (INDEX_LIMIT, BalancedPicker, DeckPicker, RandomPicker, SeedMemory, ShufflePicker, deck_cards, fingerprint,
                                  make_picker, pick_in_range, pick_index, pick_label, stable_seed)

names = st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _-", min_size=1, max_size=8), min_size=1, max_size=12, unique=True)
weights = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
seeds = st.integers(min_value=0, max_value=2 ** 64 - 1)
MODES = ["random", "deck", "shuffle", "balanced", "sequential"]


def weighted_list(draw_names, draw_weights):
    return [(weight, name) for weight, name in zip(draw_weights, draw_names)]


@st.composite
def weighted_options(draw, min_size=1, max_size=12):
    options = draw(st.lists(st.text(alphabet="abcdefghij", min_size=1, max_size=6), min_size=min_size, max_size=max_size, unique=True))
    return [(draw(weights), option) for option in options]


def picked(picker, weighted, count=1, plain=False):
    return [option for option, _ in picker.pick(weighted, count, plain)]


# Every picker: picks come from the options, are distinct, never more than asked, never an option of weight 0 (when another has weight).
@given(weighted=weighted_options(), count=st.integers(1, 6), seed=seeds, mode=st.sampled_from(["random", "deck", "shuffle", "balanced"]))
def test_every_picker_picks_distinct_options_with_weight(weighted, count, seed, mode):
    picker = make_picker(mode, seed)
    result = picked(picker, weighted, count)
    options = [option for _, option in weighted]
    assert len(result) == len(set(result)) <= count
    assert set(result) <= set(options)
    if any(weight > 0 for weight, _ in weighted) and mode != "deck":
        assert all(dict((o, w) for w, o in weighted)[option] > 0 for option in result)
    if mode == "deck":
        cards = deck_cards(weighted)
        assert set(result) <= set(cards)


@given(weighted=weighted_options(), seed=seeds, count=st.integers(1, 5))
def test_random_picks_are_reproducible_from_the_seed(weighted, seed, count):
    assert picked(RandomPicker(random.Random(seed)), weighted, count) == picked(RandomPicker(random.Random(seed)), weighted, count)


@given(weighted=weighted_options(), seed=seeds)
def test_deck_picks_are_reproducible_from_the_seed(weighted, seed):
    assert picked(DeckPicker(random.Random(seed), seed, {}), weighted) == picked(DeckPicker(random.Random(seed), seed, {}), weighted)


@given(options=names, first_round=st.integers(0, 10 ** 12))
def test_deck_deals_each_option_once_per_round_from_any_round(options, first_round):
    weighted = [(1.0, option) for option in options]
    size = len(options)
    for round_number in (first_round, first_round + 1):
        dealt = [picked(DeckPicker(random.Random(seed), seed, {}), weighted)[0] for seed in range(round_number * size, (round_number + 1) * size)]
        assert sorted(dealt) == sorted(options)


@given(options=names, round_number=st.integers(0, 10 ** 9))
def test_deck_never_repeats_across_the_end_of_a_round(options, round_number):
    assume(len(options) >= 3) # One option repeats by force; two simply alternate.
    weighted = [(1.0, option) for option in options]
    size = len(options)
    last = picked(DeckPicker(random.Random(0), round_number * size + size - 1, {}), weighted)[0]
    first = picked(DeckPicker(random.Random(0), (round_number + 1) * size, {}), weighted)[0]
    assert last != first


@given(copies=st.lists(st.integers(1, 5), min_size=1, max_size=6))
def test_deck_cards_follow_whole_weights(copies):
    weighted = [(float(count), f"o{index}") for index, count in enumerate(copies)]
    cards = deck_cards(weighted)
    assert Counter(cards) == {f"o{index}": count for index, count in enumerate(copies)}
    total = len(cards)
    dealt = Counter(picked(DeckPicker(random.Random(seed), seed, {}), weighted)[0] for seed in range(total))
    assert dealt == Counter(cards) # One round deals every copy.


@given(weights=st.lists(st.one_of(st.floats(0, 1e12), st.integers(0, 10 ** 12).map(float)), min_size=1, max_size=20))
def test_deck_cards_stay_within_the_limit_and_keep_every_option(weights):
    weighted = [(weight, f"o{index}") for index, weight in enumerate(weights)]
    cards = deck_cards(weighted)
    positive = [option for weight, option in weighted if weight > 0]
    assert len(cards) <= max(seed_modes.DECK_LIMIT + len(positive), len(positive))
    assert set(cards) == set(positive) # Every option with weight keeps a card, however heavy the others.
    counts = Counter(cards)
    for (weight_a, a), (weight_b, b) in itertools.combinations([item for item in weighted if item[0] > 0], 2):
        if weight_a >= weight_b:
            assert counts[a] >= counts[b] # Heavier never gets fewer cards.


@given(options=names, counts=st.lists(st.integers(1, 4), min_size=1, max_size=6), position=st.integers(0, 10 ** 12))
def test_deck_picks_in_one_run_never_repeat_until_every_option_came(options, counts, position):
    weighted = [(1.0, option) for option in options]
    picker = DeckPicker(random.Random(1), position, {})
    dealt = []
    for count in counts:
        result = picked(picker, weighted, count)
        assert len(result) == len(set(result)) == min(count, len(options))
        dealt += result
    # The same list again in the same run takes the next cards, also across the end of a round: no repeat before every option came up once.
    for start in range(0, len(dealt), len(options)):
        window = dealt[start:start + len(options)]
        assert len(window) == len(set(window)), (dealt, options)


@given(options=names, count=st.integers(1, 4), position=st.integers(0, 10 ** 12))
def test_deck_first_pick_of_a_run_is_the_same_as_a_lone_pick(options, count, position):
    weighted = [(1.0, option) for option in options]
    shared = DeckPicker(random.Random(1), position, {})
    first = picked(shared, weighted, count)
    picked(shared, weighted, count)
    assert first == picked(DeckPicker(random.Random(1), position, {}), weighted, count) # Another use later in the prompt doesn't change the first.


@settings(max_examples=60)
@given(options=st.lists(st.text(alphabet="xyz", min_size=3, max_size=6), min_size=2, max_size=8, unique=True), rounds=st.integers(2, 4))
def test_shuffle_covers_every_option_per_round_and_never_repeats_at_the_seam(options, rounds):
    weighted = [(1.0, option) for option in options]
    dealt = [picked(ShufflePicker(), weighted)[0] for _ in range(rounds * len(options))]
    for start in range(0, len(dealt), len(options)):
        assert sorted(dealt[start:start + len(options)]) == sorted(options)
    if len(options) >= 3:
        assert all(a != b for a, b in zip(dealt, dealt[1:]))


def test_shuffle_survives_a_restart(tmp_path, monkeypatch):
    path = str(tmp_path / "memory.sqlite")
    weighted = [(1.0, name) for name in "abcdef"]
    monkeypatch.setattr(seed_modes, "MEMORY", SeedMemory(path))
    first = [picked(ShufflePicker(), weighted)[0] for _ in range(3)]
    seed_modes.MEMORY.save()
    seed_modes.MEMORY.connection.close()
    monkeypatch.setattr(seed_modes, "MEMORY", SeedMemory(path)) # ComfyUI restarted: a new memory object on the same file.
    rest = [picked(ShufflePicker(), weighted)[0] for _ in range(3)]
    assert sorted(first + rest) == list("abcdef")


@settings(max_examples=40)
@given(weighted=weighted_options(min_size=2, max_size=6))
def test_balanced_credits_always_sum_to_zero(weighted):
    assume(sum(weight for weight, _ in weighted) > 0)
    for _ in range(25):
        BalancedPicker().pick(weighted, 1, False)
    credits = seed_modes.MEMORY.get("balanced", seed_modes.MEMORY.key(weighted))
    assert credits is not None and abs(sum(credits)) < 1e-3 # Every pick hands out exactly what it takes.


@pytest.mark.parametrize("weights", [[1, 1, 1, 1, 1], [3, 1], [1, 2, 3, 4], [5, 0.5, 0.5]])
def test_balanced_long_run_matches_the_weights_and_nothing_waits_too_long(weights):
    weighted = [(float(weight), f"w{index}") for index, weight in enumerate(weights)]
    runs = 3000
    dealt = [picked(BalancedPicker(), weighted)[0] for _ in range(runs)]
    total = sum(weights)
    counts = Counter(dealt)
    for weight, name in weighted:
        assert abs(counts[name] / runs - weight / total) < 0.02, (name, counts)
    for weight, name in weighted:
        gaps = [index for index, option in enumerate(dealt) if option == name]
        longest = max(b - a for a, b in zip(gaps, gaps[1:]))
        assert longest < 8 * total / weight + 10, (name, longest)


@given(labels=names, seed=seeds)
def test_pick_label_sequential_is_the_seed_position(labels, seed):
    assert pick_label(labels, None, seed) == labels[seed % len(labels)]


@given(low=st.floats(-1e6, 1e6), span=st.floats(0, 1e6), parts=st.integers(1, 50), seed=seeds, mode=st.sampled_from(MODES))
def test_pick_in_range_stays_in_range(low, span, parts, seed, mode):
    high = low + span
    value = pick_in_range(low, high, parts, make_picker(mode, seed), seed, "range")
    assert low - 1e-6 * max(1, abs(low)) <= value <= high + 1e-6 * max(1, abs(high))


@given(parts=st.integers(1, 30), first=st.integers(0, 10 ** 9))
def test_pick_in_range_deck_spreads_over_every_part(parts, first):
    start = first * parts
    values = [pick_in_range(0.0, 1.0, parts, DeckPicker(random.Random(seed), seed, {}), seed, "spread") for seed in range(start, start + parts)]
    assert sorted(min(int(value * parts), parts - 1) for value in values) == list(range(parts))


@given(count=st.integers(1, 10 ** 15), seed=seeds, mode=st.sampled_from(MODES))
def test_pick_index_is_always_a_valid_position(count, seed, mode):
    index = pick_index(count, make_picker(mode, seed), seed, "positions")
    assert isinstance(index, int) and 0 <= index < count


@pytest.mark.parametrize("count", [1, 2, 7, INDEX_LIMIT - 1, INDEX_LIMIT])
def test_pick_index_deck_covers_every_position_up_to_the_limit(count):
    first = 5 * count
    assert sorted(pick_index(count, DeckPicker(random.Random(seed), seed, {}), seed, "cover") for seed in range(first, first + count)) == list(range(count))


def test_pick_index_past_the_limit_covers_every_part():
    count = INDEX_LIMIT * 7 + 3
    parts = seed_modes.INDEX_PARTS
    indexes = [pick_index(count, DeckPicker(random.Random(seed), seed, {}), seed, "big") for seed in range(parts)]
    assert sorted(index * parts // count for index in indexes) == list(range(parts))


@given(parts=st.lists(st.one_of(st.text(), st.integers(), st.floats(allow_nan=False)), max_size=5))
def test_stable_seed_is_a_64_bit_number_that_depends_on_the_parts(parts):
    value = stable_seed(*parts)
    assert 0 <= value < 2 ** 64 and value == stable_seed(*parts)
    assert stable_seed(*parts, "x") != value


@given(mode=st.sampled_from(MODES + ["combinations", "mutate", "nonsense"]))
def test_fingerprint_is_none_or_a_fresh_json_string(mode):
    first, second = fingerprint(mode), fingerprint(mode)
    json.dumps([first, second])
    if mode in seed_modes.REMEMBERING_MODES:
        assert isinstance(first, str) and first != second
    else:
        assert first is None and second is None


def test_seed_memory_is_safe_with_many_threads(tmp_path):
    memory = SeedMemory(str(tmp_path / "threads.sqlite"))
    errors = []

    def work(worker):
        try:
            for index in range(200):
                memory.set("shuffle", f"{worker}-{index % 20}", {"position": index})
                memory.get("shuffle", f"{worker}-{(index * 7) % 20}")
                if index % 50 == 0:
                    memory.save()
        except Exception as error: # noqa: BLE001
            errors.append(error)
    threads = [threading.Thread(target=work, args=(worker,)) for worker in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    memory.save()
    assert errors == []
    assert all(memory.get("shuffle", f"{worker}-19") == {"position": 199} for worker in range(8))


def test_seed_memory_starts_over_when_its_file_is_deleted(tmp_path):
    path = tmp_path / "memory.sqlite"
    memory = SeedMemory(str(path))
    memory.set("shuffle", "k", {"position": 3})
    memory.save()
    path.unlink()
    assert memory.get("shuffle", "k") is None
    memory.set("shuffle", "k", {"position": 1})
    memory.save()
    assert path.exists() and memory.get("shuffle", "k") == {"position": 1}


@given(values=st.lists(st.one_of(st.integers(), st.text(), st.lists(st.integers()), st.dictionaries(st.text(), st.integers())), min_size=1, max_size=5))
def test_seed_memory_round_trips_any_json_value(values, tmp_path_factory):
    memory = SeedMemory(str(tmp_path_factory.mktemp("roundtrip") / "m.sqlite"))
    for index, value in enumerate(values):
        memory.set("balanced", str(index), value)
    memory.save()
    assert [memory.get("balanced", str(index)) for index in range(len(values))] == values
