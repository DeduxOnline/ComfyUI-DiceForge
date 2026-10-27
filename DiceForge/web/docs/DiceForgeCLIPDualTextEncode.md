Encodes a positive and a negative prompt with the same CLIP model, outputting a conditioning and the filled-in text for each (without a CLIP, just the text, for other text encoders). Supports {a|b} choices, \_\_name\_\_ wildcards and ${name} variables, picked from the seed.

![CLIP Dual Text Encode in Nodes 2.0 with wildcards, variables and choices](images/clip_dual_text_encode.png)

Its right-click menu has the prompt tools: **📖 Syntax guide**, **🕘 Prompt history**, **🎲 Wildcard Browser**, **✂ Selection → new wildcard…**, **🎴 LoRA Browser** (to insert trigger words), **🏷 Tag autocomplete** (download tag lists), **🏷 Tag Browser** and **🎨 Prompt styles**.

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `positive` | STRING |  | The positive prompt: what the image should contain. Supports {a\|b} choices, \_\_name\_\_ wildcards and ${name=value} / ${name} variables. |
| `model` (optional) | MODEL |  | The model, for &lt;lora:name:weight> in the prompts: the LoRAs go on it (model output) and on the CLIP. Passed through when the prompts have none. |
| `clip` (optional) | CLIP |  | The CLIP model used for encoding both prompts. Leave it unconnected to use the node for the text only (positive\_text and negative\_text), for example with a Flux or SD3 text encoder. |

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

| Input | Type | Default | Description |
|---|---|---|---|
| `negative` | STRING |  | The negative prompt: what the image should avoid. Supports {a\|b} choices, \_\_name\_\_ wildcards and ${name=value} / ${name} variables. |
| `seed` | INT | `0` | Seed for {a\|b} choices and \_\_name\_\_ wildcards. The same seed always gives the same prompts, in every mode. |
| `seed_mode` | COMBO | `random` | How choices and wildcards change from run to run. random: every pick is independent, so the same option can come up again soon. deck: the seed steps through a shuffled order of the options; with control after generate on increment, every option comes once before any repeats. Reproducible. shuffle: like shuffle in a music player, the node remembers the options already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same result again. balanced: an option just picked gets a low chance, and options not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file, so it continues after a restart. The same seed gives the same result again. combinations: the seed numbers every combination of the options, so seeds 0, 1, 2... go through all of them once (the console shows how many). Reproducible. mutate: keeps the last prompt and changes just one choice each run with a new seed, to explore variations of a good result. Remembered in a file, so it continues after a restart. The same seed gives the same result again. |
| `trim` | BOOLEAN | on | Remove extra spaces from both prompts: at the start and end of lines, double spaces, spaces before , . ; : ! ? ) and after (, and extra empty lines. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `model` | MODEL | The model with the prompts' &lt;lora:name:weight> LoRAs: connect it to KSampler instead of the loader's model. |
| `positive` | CONDITIONING | Conditioning from the positive prompt. |
| `negative` | CONDITIONING | Conditioning from the negative prompt. |
| `positive_text` | STRING | The positive prompt as encoded: choices, wildcards and variables filled in. Connect it to another text encoder (Flux, SD3...) or a Save Image file name. |
| `negative_text` | STRING | The negative prompt as encoded: choices, wildcards and variables filled in. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#clip-dual-text-encode-wildcards-lora): examples, tips, and how it works with the other nodes.
