import logging
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .seed_modes import MEMORY, SEED_MODES, make_picker, pick_index, pick_in_range
SEED_MODE_TOOLTIP = ("How the value changes from run to run.\n"
    "random: every pick is independent, so the same value (or a close one) can come up again soon.\n"
    "deck: the seed steps through a shuffled order of the values; with control after generate on increment, every value comes once before any repeats. Reproducible.\n"
    "shuffle: like shuffle in a music player, the node remembers the values already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same result again.\n"
    "balanced: a value just picked gets a low chance, and values not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same result again.\n"
    "sequential: with a step, seeds 0, 1, 2... give min, min + step, min + 2 x step...; without, the middle of each part in order. Reproducible.\n"
    "Without a step (0), deck, shuffle and balanced split the range into `parts` equal parts that take turns, with a random value inside each part.")
# Node schema (V3 / Nodes 2.0): a random number between min and max (any value, or in steps of step), picked from the seed with the same seed modes as
# the DiceForge resolution nodes, so values spread over the range run after run instead of clustering.
class RandomFloatSeedModes(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeRandomFloat",
            display_name="Random Float",
            category="DiceForge/random",
            description="A random number between min and max, picked from the seed. Seed modes spread the values over the whole range before repeating.",
            search_aliases=["random", "random number", "float", "decimal", "uniform", "random float", "seed modes"],
            inputs=[
                io.Float.Input(
                    "min",
                    default=0.0,
                    min=-1e9,
                    max=1e9,
                    step=0.01,
                    tooltip="The smallest value.",
                ),
                io.Float.Input(
                    "max",
                    default=1.0,
                    min=-1e9,
                    max=1e9,
                    step=0.01,
                    tooltip="The largest value.",
                ),
                io.Float.Input(
                    "step",
                    default=0.0,
                    min=0.0,
                    max=1e9,
                    step=0.01,
                    tooltip="0: any value between min and max. Above 0: only min, min + step, min + 2 x step... up to max (for example 0.5 for CFG 5.0, 5.5, 6.0...).",
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
                io.Int.Input(
                    "parts",
                    default=10,
                    min=2,
                    max=1000,
                    tooltip="With step 0: how many equal parts of the range deck, shuffle, balanced and sequential take turns between (more parts: a finer spread, longer rounds).",
                    advanced=True,
                ),
            ],
            outputs=[
                io.Float.Output(display_name="value", tooltip="The random value."),
            ],
        )
    # Main method: with a step, the possible values are min, min + step... up to max and the seed mode picks one of them; without, any value in the range.
    @classmethod
    def execute(cls, min=0.0, max=1.0, step=0.0, seed=0, seed_mode="random", parts=10):
        low, high = (min, max) if min <= max else (max, min) # A reversed range still works.
        picker = make_picker(seed_mode, seed)
        if step > 0:
            count = int((high - low) / step + 1e-9) + 1 # The small margin keeps max when it is on a step despite float rounding.
            value = round(low + pick_index(count, picker, seed, f"Float {low} {high} {step}") * step, 10)
        else:
            value = pick_in_range(low, high, parts, picker, seed, f"Float {low} {high}")
        MEMORY.save()
        logging.info(f"[DiceForge] Random Float | Value: {value} | Range: {low} to {high}, step {step} | Seed: {seed} ({seed_mode})")
        return io.NodeOutput(value)
# Extension entry point for ComfyUI V3 node registration.
class RandomFloatSeedModesExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [RandomFloatSeedModes]
async def comfy_entrypoint():
    return RandomFloatSeedModesExtension()
