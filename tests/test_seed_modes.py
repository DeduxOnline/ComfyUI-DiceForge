# Seed modes (DiceForge/seed_modes.py): how picks follow the seed, and the memory of shuffle and balanced.
import random
from collections import Counter
import pytest
from DiceForge import seed_modes
from DiceForge.seed_modes import (BalancedPicker, DeckPicker, RandomPicker, SeedMemory, ShufflePicker, deck_cards, make_picker,
                                  pick_in_range, pick_index, pick_label, stable_seed)

OPTIONS = [(1.0, name) for name in "abcde"]


def picks(picker, weighted=OPTIONS, count=1, plain=True):
    return [option for option, _ in picker.pick(weighted, count, plain)]


def test_stable_seed_is_the_same_every_time_and_differs_by_parts():
    first, again = stable_seed("a", 1), stable_seed("a", 1)
    assert first == again
    assert stable_seed("a", 1) != stable_seed("a", 2)


def test_deck_cards_repeat_options_by_weight_and_drop_zero_weights():
    assert deck_cards([(2.0, "a"), (1.0, "b"), (0.0, "c"), (0.4, "d")]) == ["a", "a", "b", "d"]


def test_random_picker_is_reproducible_from_the_seed():
    first = [picks(RandomPicker(random.Random(seed))) for seed in range(50)]
    again = [picks(RandomPicker(random.Random(seed))) for seed in range(50)]
    assert first == again
    assert len({tuple(pick) for pick in first}) > 1


def test_random_multi_pick_has_no_repeats():
    for seed in range(100):
        chosen = picks(RandomPicker(random.Random(seed)), count=3, plain=False)
        assert len(chosen) == len(set(chosen)) == 3


def test_random_picker_follows_weights():
    weighted = [(3.0, "cat"), (1.0, "dog")]
    counts = Counter(picks(RandomPicker(random.Random(seed)), weighted, plain=False)[0] for seed in range(2000))
    assert 0.70 < counts["cat"] / 2000 < 0.80


@pytest.mark.parametrize("size", [2, 3, 5, 8])
def test_deck_deals_every_option_once_per_round_without_a_repeat_between_rounds(size):
    weighted = [(1.0, f"o{index}") for index in range(size)]
    dealt = [picks(DeckPicker(random.Random(seed), seed, {}), weighted)[0] for seed in range(size * 6)]
    for start in range(0, len(dealt), size):
        assert sorted(dealt[start:start + size]) == sorted(option for _, option in weighted)
    assert all(a != b for a, b in zip(dealt, dealt[1:])), dealt


def test_deck_takes_the_next_card_when_the_same_list_comes_twice_in_one_run():
    picker = DeckPicker(random.Random(0), 0, {})
    first, second = picks(picker), picks(picker)
    assert first != second


def test_shuffle_goes_through_every_option_before_repeating_and_remembers_between_runs():
    dealt = [picks(ShufflePicker())[0] for _ in range(15)]
    for start in range(0, 15, 5):
        assert sorted(dealt[start:start + 5]) == list("abcde")
    assert all(a != b for a, b in zip(dealt, dealt[1:]))
    seed_modes.MEMORY.save()
    assert seed_modes.MEMORY.get("shuffle", seed_modes.MEMORY.key(deck_cards(OPTIONS)))["position"] == 5


def test_balanced_repeats_rarely_and_keeps_the_weights():
    dealt = [picks(BalancedPicker(), plain=False)[0] for _ in range(1000)]
    counts = Counter(dealt)
    assert all(150 < counts[name] < 250 for name in "abcde"), counts # 200 each in the long run
    repeats = sum(a == b for a, b in zip(dealt, dealt[1:]))
    assert repeats < 120 # plain random: about 200 of 1000


def test_make_picker_by_mode():
    assert isinstance(make_picker("random", 1), RandomPicker)
    assert isinstance(make_picker("deck", 1), DeckPicker)
    assert isinstance(make_picker("shuffle", 1), ShufflePicker)
    assert isinstance(make_picker("balanced", 1), BalancedPicker)
    assert make_picker("sequential", 1) is None


def test_pick_label_sequential_is_the_seed_position():
    labels = ["a", "b", "c"]
    assert [pick_label(labels, None, seed) for seed in range(7)] == ["a", "b", "c", "a", "b", "c", "a"]


def test_pick_in_range_stays_in_range_and_deck_covers_every_part():
    for seed in range(200):
        assert 2.0 <= pick_in_range(2.0, 5.0, 10, RandomPicker(random.Random(seed)), seed, "x") <= 5.0
    parts = sorted(int((pick_in_range(0.0, 10.0, 10, DeckPicker(random.Random(seed), seed, {}), seed, "x"))) for seed in range(10))
    assert parts == list(range(10))
    assert [pick_in_range(0.0, 10.0, 5, None, seed, "x") for seed in range(5)] == [1.0, 3.0, 5.0, 7.0, 9.0]


def test_pick_index_deck_and_sequential_cover_every_position():
    assert sorted(pick_index(20, DeckPicker(random.Random(seed), seed, {}), seed, "x") for seed in range(20)) == list(range(20))
    assert [pick_index(4, None, seed, "x") for seed in range(6)] == [0, 1, 2, 3, 0, 1]
    big = seed_modes.INDEX_LIMIT * 10
    assert all(0 <= pick_index(big, DeckPicker(random.Random(seed), seed, {}), seed, "x") < big for seed in range(50))


@pytest.mark.parametrize("picker, key", [(ShufflePicker, deck_cards), (BalancedPicker, list)])
def test_a_seed_gives_its_picks_again_without_moving_the_memory_on(picker, key):
    options = [(1.0, name) for name in "abcdef"]
    def names(seed):
        return [option for option, _ in picker(seed).pick(options, 2, False)]
    first = {seed: names(seed) for seed in range(6)}
    now = seed_modes.MEMORY.get(picker.mode, seed_modes.MEMORY.key(key(options)))
    assert {seed: names(seed) for seed in (5, 0, 3)} == {seed: first[seed] for seed in (5, 0, 3)}
    assert seed_modes.MEMORY.get(picker.mode, seed_modes.MEMORY.key(key(options))) == now # Replays leave the memory where it was.
    assert names(6) != names(7) or picker is BalancedPicker # New seeds go on (shuffle: the next cards of the round).
    assert make_picker("shuffle", 12).seed == 12 and make_picker("balanced", 12).seed == 12


def test_the_same_list_twice_in_one_run_is_replayed_pick_by_pick():
    options = [(1.0, name) for name in "abcd"]
    def run(seed):
        picker = ShufflePicker(seed) # One run: the same list picked twice (__color__ hair, __color__ eyes).
        return [picker.pick(options, 1, True)[0][0] for _ in range(2)]
    first = run(1)
    assert first[0] != first[1] and run(1) == first


def test_seed_memory_keeps_values_and_forgets_the_oldest_past_the_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(seed_modes, "MEMORY_LIMIT", 3)
    clock = iter(range(100))
    monkeypatch.setattr(seed_modes.time, "time", lambda: next(clock)) # Distinct times, so "oldest" is clear.
    memory = SeedMemory(str(tmp_path / "memory.sqlite"))
    for index in range(5):
        memory.set("shuffle", f"k{index}", {"position": index})
    memory.save()
    assert memory.get("shuffle", "k4") == {"position": 4}
    assert memory.get("shuffle", "k0") is None
    assert SeedMemory.key("a", 1) == SeedMemory.key("a", 1) != SeedMemory.key("a", 2)
