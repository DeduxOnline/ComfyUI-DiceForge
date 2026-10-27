A random whole number between min and max, picked from the seed. Seed modes can go through every value before repeating one.

![Random Int, Random Float and Random Sampler in Nodes 2.0](images/random_numbers_sampler.png)

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `min` | INT | `0` | The smallest value (included). |
| `max` | INT | `10` | The largest value (included when it is on a step from min). |
| `step` | INT | `1` | Only values min, min + step, min + 2 x step... up to max (for example 4 for steps of 4). |
| `seed` | INT | `0` | Seed for the random value. With deck or sequential, set control after generate to increment. |

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

| Input | Type | Default | Description |
|---|---|---|---|
| `seed_mode` | COMBO | `random` | How the value changes from run to run. random: every pick is independent, so the same value can come up again soon. deck: the seed steps through a shuffled order of the values; with control after generate on increment, every value comes once before any repeats. Reproducible. shuffle: like shuffle in a music player, the node remembers the values already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same result again. balanced: a value just picked gets a low chance, and values not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same result again. sequential: the seed is the position, so seeds 0, 1, 2... give min, min + step, min + 2 x step... then start over. Reproducible. Past 1000 possible values, deck, shuffle and balanced take turns between 100 equal parts of the range instead, with a random value inside each part. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `value` | INT | The random value. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#random-int-and-random-float): examples, tips, and how it works with the other nodes.
