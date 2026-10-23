### Random Int and Random Float

![Random Int, Random Float and Random Sampler in Nodes 2.0](images/random_numbers_sampler.png)

A random number between `min` and `max`, picked from the seed with the same [seed modes](https://github.com/DeduxOnline/ComfyUI-DiceForge#seed-modes-for-sizes) as the resolution nodes, so values can go through the whole range instead of clustering. Connect the `value` output to any number input (converted to an input), for example KSampler's `cfg` or `steps`.

#### Inputs

| Input | Where | Default | Description |
|---|---|---|---|
| `min` | main | `0` | The smallest value. |
| `max` | main | `10` (Int), `1.0` (Float) | The largest value. A reversed range (`min` above `max`) works too. |
| `step` | main | `1` (Int), `0` (Float) | Only `min`, `min + step`, `min + 2 x step`… up to `max`. For Random Float, `0` means any value; for example `min` 5, `max` 8, `step` 0.5 gives CFG 5.0, 5.5 … 8.0. |
| `seed` | main | `0` | Seed for the random value. With `deck` or `sequential`, set *control after generate* to *increment*. |
| `seed_mode` | Advanced | `random` | `random`, `deck`, `shuffle`, `balanced` or `sequential`, as for the resolution nodes. |
| `parts` | Advanced (Float) | `10` | With `step` 0: how many equal parts of the range the modes other than `random` take turns between. |

#### Outputs

| Output | Description |
|---|---|
| `value` | The random value (`INT` or `FLOAT`). |

#### How the modes pick numbers

- **Values on a step** (every Random Int, Random Float with `step` above 0): each possible value is an option, like a size in a list. `deck` and `shuffle` give every value once before any repeats (1 to 6: six runs, six different values), and `sequential` counts up from `min` by `step`, then starts over.
- **More than 1000 possible values** (for example 0 to 1,000,000): `deck`, `shuffle` and `balanced` take turns between 100 equal parts of the range instead, with a random value inside the part, so 100 runs land in 100 different parts. `sequential` still counts up.
- **Random Float with `step` 0**: the range is split into `parts` equal parts, like Random Chaos: in 10 runs over 0–1, `deck` and `shuffle` hit all 10 tenths (about 7 with `random`). `sequential` gives the middle of each part in order (0.05, 0.15 … 0.95).
- The value is written to the console on every run.
