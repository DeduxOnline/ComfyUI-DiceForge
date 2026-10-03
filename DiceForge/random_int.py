import logging
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .seed_modes import MEMORY, SEED_MODES, make_picker, pick_index
SEED_MODE_TOOLTIP = ("How the value changes from run to run.\n"
    "random: every pick is independent, so the same value can come up again soon.\n"
    "deck: the seed steps through a shuffled order of the values; with control after generate on increment, every value comes once before any repeats. Reproducible.\n"
    "shuffle: like shuffle in a music player, the node remembers the values already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same result again.\n"
    "balanced: a value just picked gets a low chance, and values not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same result again.\n"
    "sequential: the seed is the position, so seeds 0, 1, 2... give min, min + step, min + 2 x step... then start over. Reproducible.\n"
    "Past 1000 possible values, deck, shuffle and balanced take turns between 100 equal parts of the range instead, with a random value inside each part.")
# Node schema (V3 / Nodes 2.0): a random whole number between min and max (in steps of step), picked from the seed with the same seed modes as the
# DiceForge resolution nodes, so values can go through the range without repeats instead of clustering.
class RandomIntSeedModes(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeRandomInt",
            display_name="Random Int",
            category="DiceForge/random",
            description="A random whole number between min and max, picked from the seed. Seed modes can go through every value before repeating one.",
            search_aliases=["random", "random number", "integer", "int", "randint", "random int", "seed modes"],
            inputs=[
                io.Int.Input(
                    "min",
                    default=0,
                    min=-0xFFFFFFFFFFFFFFFF,
                    max=0xFFFFFFFFFFFFFFFF,
                    tooltip="The smallest value (included).",
                ),
                io.Int.Input(
                    "max",
                    default=10,
                    min=-0xFFFFFFFFFFFFFFFF,
                    max=0xFFFFFFFFFFFFFFFF,
                    tooltip="The largest value (included when it is on a step from min).",
                ),
                io.Int.Input(
                    "step",
                    default=1,
                    min=1,
                    max=0xFFFFFFFFFFFFFFFF,
                    tooltip="Only values min, min + step, min + 2 x step... up to max (for example 4 for steps of 4).",
                ),
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Seed for the random value. With deck or sequential, set control after generate to increment.",
                ),
                io.Combo.Input(
                    "seed_mode",
                    options=SEED_MODES,
                    default="random",
                    tooltip=SEED_MODE_TOOLTIP,
                    advanced=True,
                ),
            ],
            outputs=[
                io.Int.Output(display_name="value", tooltip="The random value."),
            ],
        )
    # Main method: the possible values are min, min + step... up to max; the seed mode picks the position of one of them.
    @classmethod
    def execute(cls, min=0, max=10, step=1, seed=0, seed_mode="random"):
        low, high = (min, max) if min <= max else (max, min) # A reversed range still works.
        step = step if step > 0 else 1
        count = (high - low) // step + 1
        value = low + pick_index(count, make_picker(seed_mode, seed), seed, f"Int {low} {high} {step}") * step
        MEMORY.save()
        logging.info(f"[DiceForge] Random Int | Value: {value} | Range: {low} to {high}, step {step} | Seed: {seed} ({seed_mode})")
        return io.NodeOutput(value)
# Extension entry point for ComfyUI V3 node registration.
class RandomIntSeedModesExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [RandomIntSeedModes]
async def comfy_entrypoint():
    return RandomIntSeedModesExtension()
