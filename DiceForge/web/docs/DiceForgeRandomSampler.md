Picks a sampler and scheduler pair from the listed ones for KSampler, with the DiceForge seed modes (deck, sequential... go through every pair once).

![Random Int, Random Float and Random Sampler in Nodes 2.0](images/random_numbers_sampler.png)

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `samplers` | STRING | `euler, euler_ancestral,…` | Samplers to pick from, separated by commas or new lines (the names in KSampler's list). \* for every sampler. |
| `schedulers` | STRING | `normal, karras` | Schedulers to pick from, separated by commas or new lines. \* for every scheduler. Every sampler is paired with every scheduler. |
| `seed` | INT | `0` | Seed for the pick. With deck or sequential, set control after generate to increment. |

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

| Input | Type | Default | Description |
|---|---|---|---|
| `seed_mode` | COMBO | `random` | How the pick changes from run to run. random: every pick is independent, so the same one can come up again soon. deck: the seed steps through a shuffled order of the sampler and scheduler pairs; with control after generate on increment, every one comes once before any repeats. Reproducible. shuffle: like shuffle in a music player, the node remembers the sampler and scheduler pairs already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same pick again. balanced: one just picked gets a low chance, and those not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same pick again. sequential: the seed is the position in the list (each sampler with every scheduler, in the listed order), so seeds 0, 1, 2... go through the sampler and scheduler pairs in order. Reproducible. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `sampler_name` | COMBO | Connect to the sampler\_name input of KSampler (or KSampler Advanced). |
| `scheduler` | COMBO | Connect to the scheduler input of KSampler (or KSampler Advanced). |
| `label` | STRING | "sampler / scheduler", for example for the label of Dice Grid. |
| `sampler_text` | STRING | The sampler name as text, for example for the row\_label of an XY Dice Grid. |
| `scheduler_text` | STRING | The scheduler name as text, for example for the label of an XY Dice Grid. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#random-sampler): examples, tips, and how it works with the other nodes.
