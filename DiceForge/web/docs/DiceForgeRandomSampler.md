### Random Sampler

Picks a sampler and scheduler pair for **KSampler** (or **KSampler Advanced**) from the ones you list. Every listed sampler is paired with every listed scheduler, and each pair is one option of the [seed modes](https://github.com/DeduxOnline/ComfyUI-DiceForge#seed-modes-for-sizes): with `deck` or `sequential` and *increment*, a series tries every pair once.

| Input | Where | Description |
|---|---|---|
| `samplers` | main | Samplers to pick from, separated by commas or new lines, with the names of KSampler's list (`euler, dpmpp_2m, dpmpp_2m_sde`...). `*` for every sampler. An unknown name stops the run with the list of known ones. |
| `schedulers` | main | Schedulers to pick from, the same way (`normal, karras`...). `*` for every scheduler. |
| `seed` | main | Seed for the pick. With `deck` or `sequential`, set *control after generate* to *increment*. |
| `seed_mode` | Advanced | `random`, `deck`, `shuffle`, `balanced` or `sequential` (each sampler with every scheduler, in the listed order). |

| Output | Description |
|---|---|
| `sampler_name` | Connect to KSampler's `sampler_name`. |
| `scheduler` | Connect to KSampler's `scheduler`. |
| `label` | `"sampler / scheduler"`, for the `label` of **Dice Grid**. |
| `sampler_text`, `scheduler_text` | The two names as text, for an XY **Dice Grid** (`row_label` and `label`). |

To vary only the sampler, list one scheduler (and the other way round).
