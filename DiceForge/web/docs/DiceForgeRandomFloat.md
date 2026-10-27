A random number between min and max, picked from the seed. Seed modes spread the values over the whole range before repeating.

![Random Int, Random Float and Random Sampler in Nodes 2.0](images/random_numbers_sampler.png)

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `min` | FLOAT | `0` | The smallest value. |
| `max` | FLOAT | `1` | The largest value. |
| `step` | FLOAT | `0` | 0: any value between min and max. Above 0: only min, min + step, min + 2 x step... up to max (for example 0.5 for CFG 5.0, 5.5, 6.0...). |
| `seed` | INT | `0` | Seed for the random value. With deck or sequential, set control after generate to increment. |

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

| Input | Type | Default | Description |
|---|---|---|---|
| `seed_mode` | COMBO | `random` | How the value changes from run to run. random: every pick is independent, so the same value (or a close one) can come up again soon. deck: the seed steps through a shuffled order of the values; with control after generate on increment, every value comes once before any repeats. Reproducible. shuffle: like shuffle in a music player, the node remembers the values already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same result again. balanced: a value just picked gets a low chance, and values not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same result again. sequential: with a step, seeds 0, 1, 2... give min, min + step, min + 2 x step...; without, the middle of each part in order. Reproducible. Without a step (0), deck, shuffle and balanced split the range into `parts` equal parts that take turns, with a random value inside each part. |
| `parts` | INT | `10` | With step 0: how many equal parts of the range deck, shuffle, balanced and sequential take turns between (more parts: a finer spread, longer rounds). |

## Outputs

| Output | Type | Description |
|---|---|---|
| `value` | FLOAT | The random value. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#random-int-and-random-float): examples, tips, and how it works with the other nodes.
