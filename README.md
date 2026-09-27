# DiceForge

**Controlled randomness for ComfyUI.** Every random pick in these nodes (a prompt choice, a wildcard line, an image size, a number) follows a *seed mode* you choose. Plain random repeats itself: roll 5 skies 5 times and you get about 3 different ones. DiceForge can deal them like cards, shuffle them like a playlist, balance the odds like a game, go through every combination, or change one detail at a time.

| Seed mode | What it does | Same seed, same result |
|---|---|---|
| `random` | Every pick is independent, as usual. | Yes |
| `deck` | The seed deals from a shuffled deck: with *increment*, every option comes once per round. | Yes |
| `shuffle` | Like shuffle in a music player: remembers what came up and picks from the rest, whatever the seed. | No |
| `balanced` | Like pseudo-random odds in games: repeats are rare but possible, nothing waits too long. | No |
| `sequential` | The seed is the position in the list: seeds 0, 1, 2… in order (sizes and numbers). | Yes |
| `combinations` | Seeds 0, 1, 2… go through every combination of the whole prompt (prompts). | Yes |
| `mutate` | Keeps the last prompt and changes one choice per run (prompts). | No |

The remembering modes keep their memory in a small file, so they continue after a restart. Details: [seed modes for prompts](#seed-modes), [seed modes for sizes and numbers](#seed-modes-for-sizes), [memory file](#memory-file).

| Node | Menu | File | Use it when |
|---|---|---|---|
| **CLIP Dual Text Encode** | DiceForge/conditioning | `DiceForge/clip_text_encode_pos_neg.py` | You want positive and negative prompts in one node, with wildcards, `{a\|b}` choices, variables and locked choices that follow the seed modes. |
| **SDXL Resolution List (Latent)** | DiceForge/latent | `DiceForge/sdxl_resolution_list_latent.py` | You want the standard SDXL sizes (1024x1024, 1216x832, ...) from a fixed list, or picked at random. |
| **Resolution Selector (Random, Latent)** | DiceForge/latent | `DiceForge/resolution_selector_random_latent.py` | You want to set an aspect ratio and a megapixel target, like the core *Resolution Selector* node, or pick the ratio at random. |
| **Random Int** | DiceForge/random | `DiceForge/random_int.py` | You want a random whole number (steps, an index, anything) that can go through every value before repeating. |
| **Random Float** | DiceForge/random | `DiceForge/random_float.py` | You want a random number (CFG, denoise, LoRA strength) spread evenly over a range. |
| **Random LoRA** | DiceForge/loaders | `DiceForge/random_lora.py` | You want to try the LoRAs of a folder one after another, like **Load LoRA** with the file picked for you. |
| **Random Checkpoint** | DiceForge/loaders | `DiceForge/random_checkpoint.py` | You want to compare the checkpoints of a folder, like **Load Checkpoint** with the file picked for you. |
| **Random Diffusion Model** | DiceForge/loaders | `DiceForge/random_diffusion_model.py` | The same for diffusion models (`models/diffusion_models`, Flux and the like), like **Load Diffusion Model**. |

All nodes use the ComfyUI V3 node schema: in the Nodes 2.0 frontend, the secondary inputs (including `seed_mode`) sit in the node's **Advanced** section.

The anime prompt builder *Prompt Director* lives in its own repository: [DeduxOnline/ComfyUI-PromptDirector](https://github.com/DeduxOnline/ComfyUI-PromptDirector).

### Coming from ResolutionForge

DiceForge was called *ResolutionForge* while it was a resolution pack. To update, delete `ComfyUI/custom_nodes/ResolutionForge` and install the `DiceForge` folder (having both loads the nodes twice).

- Saved workflows keep working: the nodes keep their ids, only their menu moved to **DiceForge**.
- *Random Int* and *Random Float* got new ids (`DiceForgeRandomInt`, `DiceForgeRandomFloat`): add them again in workflows saved with the first version.
- The memory file moves by itself from `ComfyUI/user/ResolutionForge` to `ComfyUI/user/DiceForge` on the first run.
- Earlier versions also had *SDXL Resolution List* and *Resolution Selector (Random)*, which output `width`, `height` and `batch` for **Empty Latent Image**. They were removed: use the *Latent* nodes, which take the same inputs.

## Installation

Copy the `DiceForge` folder into `ComfyUI/custom_nodes` and restart ComfyUI:

```sh
git clone https://github.com/DeduxOnline/ComfyUI-DiceForge.git
cp -r ComfyUI-DiceForge/DiceForge ComfyUI/custom_nodes/
```

Cloning the whole repository straight into `custom_nodes` does not work: the nodes are in the `DiceForge` subfolder, so ComfyUI does not find them.

`DiceForge/__init__.py` registers all the nodes. Each node is one file, and all of them share `DiceForge/seed_modes.py` (the seed modes and their memory file), so install the whole folder. The live previews also use the small frontend extension in `DiceForge/web`, which only loads with the whole folder: without it, *SDXL Resolution List (Latent)* shows "—" and *Resolution Selector (Random, Latent)* shows fixed ratios only, like the core node.

**Requirements:** a recent ComfyUI that includes `comfy_api.latest` (the V3 node API). *Resolution Selector (Random, Latent)* also needs the resolution preview widget, which ships with the core *Resolution Selector* node. Older ComfyUI versions will not load these nodes.

## Typical use

- Connect the `latent` output of a resolution node to the `latent_image` input of **KSampler**.
- Connect the `CLIP` output of your checkpoint loader to **CLIP Dual Text Encode**, then its `positive` and `negative` outputs to the matching inputs of **KSampler**.
- To drive the image and the canvas size from one seed, connect the `seed` output of a resolution node to the `seed` input of **KSampler**.
- To compare LoRAs or checkpoints, use **Random LoRA** or **Random Checkpoint** with `seed_mode` `deck` and *increment*: every file of the folder comes once before any repeats.
- To try a range of values, convert a KSampler input such as `cfg` to an input and connect **Random Float** (`min` 4, `max` 8, `step` 0.5) to it.
- For a series of images without repeats, set `seed_mode` to `deck` and *control after generate* to *increment* on each DiceForge node (reproducible), or use `shuffle` with any seed (not reproducible, continues after a restart).

## SDXL Resolution List (Latent)

Node id: `SDXLResolutionListLatent`.

The resolution is a nested list: first pick a group in `resolution`, then a size of that group in `size`. The Random Chaos group also shows `max_aspect`.

### Inputs

| Input | Section | Default | Description |
|---|---|---|---|
| `resolution` | main | `Standard` | Group: `Standard`, `High-Res`, `Random` or `Random Chaos` (see below). |
| `size` | main | `1024 x 1024` | A size of the chosen group: a fixed size for Standard and High-Res, a list to pick from for Random, an orientation for Random Chaos (`Any`, `Portrait` or `Landscape`). |
| `max_aspect` | main (Random Chaos only) | `2.0` | The most stretched aspect ratio Random Chaos may pick (1.0–4.0): 2.0 means up to 2:1 or 1:2, 1.0 gives only squares. |
| `preview` | main | — | Live preview of the output size and megapixels, the same widget as in the core *Resolution Selector*. For the Random and Random Chaos groups it shows the size of the last run, as long as the settings other than `seed` stay the same, and "—" before a run or after a change. |
| `seed` | main | `0` | Seed for the random options. The same seed always gives the same size. |
| `scale` | Advanced | `1.0` | Scales width and height by this factor (0.1–10), before rounding to `multiple`. Note that 2.0 gives 4x the pixels. |
| `multiple` | Advanced | `8` | Rounds width and height to the nearest multiple of this value (8–256, in steps of 8). Use 64 for SDXL training sizes. |
| `batch` | Advanced | `1` | Number of latents in the batch (1–32). |
| `seed_mode` | Advanced | `random` | How the random groups change from run to run: `random`, `deck`, `shuffle`, `balanced` or `sequential`. See [Seed modes for sizes](#seed-modes-for-sizes). |

### Outputs

| Output | Description |
|---|---|
| `latent` | Empty latent batch, identical to what **Empty Latent Image** makes for this size and `batch`. Connect it to the `latent_image` input of **KSampler**. |
| `width` | Width in pixels, for example for an upscale or hires-fix step. |
| `height` | Height in pixels. |
| `seed` | The seed used for this run, the same as the node's `seed` input. For example, connect it to the `seed` input of **KSampler**. |

### Fixed sizes

The `size` list shows width x height; the aspect ratios are given here for reference.

| Standard | High-Res |
|---|---|
| 1024 x 1024 (1:1) | 1536 x 1536 (1:1) |
| 1152 x 896 (9:7) / 896 x 1152 (7:9) | 1536 x 1152 (4:3) / 1152 x 1536 (3:4) |
| 1216 x 832 (3:2) / 832 x 1216 (2:3) | 1536 x 1024 (3:2) / 1024 x 1536 (2:3) |
| 1344 x 768 (16:9) / 768 x 1344 (9:16) | 1536 x 864 (16:9) / 864 x 1536 (9:16) |
| 1536 x 640 (21:9) / 640 x 1536 (9:21) | |

### Random groups

- **Random**: picks one of the listed sizes at random from the seed.
  - **Any Listed / Any High-Res Listed**: one of the Standard or High-Res sizes above.
  - **Vertical Listed / Horizontal Listed** (and their **High-Res** versions): only portrait or only landscape sizes.
- **Random Chaos**: a random aspect ratio up to `max_aspect`, at about 1024x1024 pixels (the SDXL native size; use `scale` for larger or smaller images).
  - **Any**: wide or tall, equally likely (the ratio is picked evenly in log scale).
  - **Portrait / Landscape**: only taller than wide, or only wider than tall; never a square.
  - The size rounds down to `multiple`, so it never exceeds 1024x1024 pixels before `scale` (it lands at about 0.9–1.0 of that).

### Notes

- Rounding to `multiple` applies to fixed sizes too. With the default 8 every listed size stays exact; with 64, 864 becomes 896.
- Like any `seed` input, it gets the frontend's *control after generate* option, which is *randomize* by default, so the random options give a new size on each run. Set it to *fixed* to keep the same size.

## Resolution Selector (Random, Latent)

Node id: `ResolutionSelectorRandomLatent`.

It works like the core ComfyUI *Resolution Selector* followed by **Empty Latent Image**, using the same size calculation, and adds random aspect ratios. For fixed ratios, the size is identical to the core node's.

### Inputs

| Input | Section | Default | Description |
|---|---|---|---|
| `aspect_ratio` | main | `1:1 (Square)` | A fixed ratio, or one of the random options below. |
| `megapixels` | main | `1.0` | Target total size (0.1–16). 1.0 MP = 1024x1024 for a square. |
| `preview` | main | — | Live preview of the output size and megapixels. For random options it shows the size of the last run, as long as the settings other than `seed` stay the same, and "—" before a run or after a change. |
| `seed` | main | `0` | Seed for the random options. By default it is randomized after each run (*control after generate*), so every run gets a new random ratio. Set it to *fixed* to repeat a result. |
| `multiple` | Advanced | `8` | Rounds width and height to the nearest multiple of this value (8–256, in steps of 8). Use 64 for SDXL training sizes. Random Chaos rounds down. |
| `batch` | Advanced | `1` | Number of latents in the batch (1–32). |
| `max_aspect` | Advanced | `2.0` | Random Chaos only: the most stretched ratio allowed (1.0–4.0). 2.0 means up to 2:1 or 1:2. |
| `seed_mode` | Advanced | `random` | How the random options change from run to run, as in SDXL Resolution List. See [Seed modes for sizes](#seed-modes-for-sizes). |

### Outputs

| Output | Description |
|---|---|
| `latent` | Empty latent batch, identical to what **Empty Latent Image** makes for this size and `batch`. Connect it to the `latent_image` input of **KSampler**. |
| `width` | Width in pixels, for example for an upscale or hires-fix step. |
| `height` | Height in pixels. |
| `seed` | The seed used for this run, the same as the node's `seed` input. For example, connect it to the `seed` input of **KSampler**. |

### Aspect ratios

1:1, 2:3, 3:2, 3:4, 4:3, 7:9, 9:7, 9:16, 16:9, 9:21, 21:9.

### Random options

- **Random Any / Random Portrait / Random Landscape**: one of the listed ratios (any, only portrait or only landscape), each equally likely.
- **Random Chaos Any / Random Chaos Portrait / Random Chaos Landscape**: any ratio up to `max_aspect`. Wide and tall ratios are equally likely.

### Notes

- Fixed and Random ratios round to the nearest `multiple`, like the core node, so the size can be slightly above or below `megapixels` (about 0.94–1.06 at 1.0 MP).
- Random Chaos rounds down, so it never exceeds `megapixels` (it lands at about 0.9–1.0 of it), and Random Chaos Portrait/Landscape never return a square.

## Seed modes for sizes

Both resolution nodes (and [Random Int and Random Float](#random-int-and-random-float) and the [random loaders](#random-lora-random-checkpoint-and-random-diffusion-model)) have a `seed_mode` input (Advanced) for their random options, with the same modes as [CLIP Dual Text Encode](#seed-modes). Fixed sizes and ratios ignore it.

| Mode | Listed sizes and ratios | Seed |
|---|---|---|
| `random` | Every pick is random, so a size can come up twice in a row. Same as before seed modes existed. | The same seed gives the same size. |
| `deck` | The seed is a position in a shuffled order: with *control after generate* on *increment*, every size comes once per round (9 runs for Any Listed), then a new order. | The same seed gives the same size. |
| `shuffle` | Like shuffle in a music player: the node remembers which sizes were used and picks from the rest, whatever the seed. | Not used. |
| `balanced` | A size that just came up gets a low chance, and the longer one is missed, the higher its chance: repeats are rare but possible. | Not used. |
| `sequential` | The seed is the position in the list: seeds 0, 1, 2… go through the sizes in order, then start over. | The same seed gives the same size. |

**Random Chaos** has no list, so the modes other than `random` split the aspect range into 8 equal parts (4 for Portrait or Landscape), take turns between the parts as above, and pick a random ratio inside the part. Runs then cover tall, square-ish and wide shapes evenly: in 8 runs about 8 of the 8 parts, against about 5 with `random`. `sequential` takes the middle of each part in order, sweeping from the tallest to the widest shape (at 1 MP and `max_aspect` 2.0: 752x1384, 824x1264 … 1384x752).

`shuffle` and `balanced` keep their memory in the same [memory file](#memory-file) as CLIP Dual Text Encode, so they continue after a restart; with them the node runs every time instead of using ComfyUI's cache (only while a random option is selected).

## Random Int and Random Float

A random number between `min` and `max`, picked from the seed with the same [seed modes](#seed-modes-for-sizes) as the resolution nodes, so values can go through the whole range instead of clustering. Connect the `value` output to any number input (converted to an input), for example KSampler's `cfg` or `steps`.

### Inputs

| Input | Where | Default | Description |
|---|---|---|---|
| `min` | main | `0` | The smallest value. |
| `max` | main | `10` (Int), `1.0` (Float) | The largest value. A reversed range (`min` above `max`) works too. |
| `step` | main | `1` (Int), `0` (Float) | Only `min`, `min + step`, `min + 2 x step`… up to `max`. For Random Float, `0` means any value; for example `min` 5, `max` 8, `step` 0.5 gives CFG 5.0, 5.5 … 8.0. |
| `seed` | main | `0` | Seed for the random value. With `deck` or `sequential`, set *control after generate* to *increment*. |
| `seed_mode` | Advanced | `random` | `random`, `deck`, `shuffle`, `balanced` or `sequential`, as for the resolution nodes. |
| `parts` | Advanced (Float) | `10` | With `step` 0: how many equal parts of the range the modes other than `random` take turns between. |

### Outputs

| Output | Description |
|---|---|
| `value` | The random value (`INT` or `FLOAT`). |

### How the modes pick numbers

- **Values on a step** (every Random Int, Random Float with `step` above 0): each possible value is an option, like a size in a list. `deck` and `shuffle` give every value once before any repeats (1 to 6: six runs, six different values), and `sequential` counts up from `min` by `step`, then starts over.
- **More than 1000 possible values** (for example 0 to 1,000,000): `deck`, `shuffle` and `balanced` take turns between 100 equal parts of the range instead, with a random value inside the part, so 100 runs land in 100 different parts. `sequential` still counts up.
- **Random Float with `step` 0**: the range is split into `parts` equal parts, like Random Chaos: in 10 runs over 0–1, `deck` and `shuffle` hit all 10 tenths (about 7 with `random`). `sequential` gives the middle of each part in order (0.05, 0.15 … 0.95).
- The value is written to the console on every run.

## Random LoRA, Random Checkpoint and Random Diffusion Model

Loaders that pick the file from a folder with the [seed modes](#seed-modes-for-sizes), then load it with the core loader (**Load LoRA**, **Load Checkpoint**, **Load Diffusion Model**), so the result is the same as picking that file by hand.

| Input | Where | Description |
|---|---|---|
| `folder` | main | A folder in `models/loras`, `models/checkpoints` or `models/diffusion_models`, subfolders included; `(all)` for every file. After adding folders, refresh the node definitions (**R**). |
| `seed` | main | Seed for the pick. With `deck` or `sequential`, set *control after generate* to *increment*. |
| `seed_mode` | Advanced | `random`, `deck`, `shuffle`, `balanced` or `sequential`, as for the resolution nodes. `sequential` goes through the files sorted by name. |
| `model`, `clip` | Random LoRA | The model and CLIP to apply the LoRA to. `clip` is optional: leave it unconnected to change only the model. |
| `strength_model`, `strength_clip` | Random LoRA | As in **Load LoRA**. Connect **Random Float** to them to vary the strength too. |
| `include_none` | Random LoRA, Advanced | Adds "no LoRA" as one more option, so some runs use the model as it is. |
| `weight_dtype` | Random Diffusion Model, Advanced | As in **Load Diffusion Model**. |

Each loader outputs what its core loader does (`model`, `clip`, `vae`) plus the picked file name (`lora_name`, `ckpt_name`, `model_name`, empty for "no LoRA"), for example to put it in the image file name. The picked file is also written to the console.

- Adding or removing files in the folder makes the node pick again, and `deck`, `shuffle` and `balanced` start a new round for the new list.
- An empty folder stops the run with an error that names it.
- With `deck` and *increment*, a checkpoint comparison shows every checkpoint once before any repeats; with `shuffle` it continues after a restart.

## About the latent

Like the output of **Empty Latent Image**, the latent works with any model you would use that node with: the core samplers adapt an empty latent to the model's latent format.

## CLIP Dual Text Encode

Node id: `CLIPTextEncodePositiveNegative`.

Works like two core *CLIP Text Encode (Prompt)* nodes sharing one CLIP model: each prompt is encoded exactly the same way, so the conditioning is identical to the core node's for the same text. On top of that, both prompts support wildcards and `{a|b}` choices, picked from a seed.

### Inputs

| Input | Section | Description |
|---|---|---|
| `clip` | main | The CLIP model used for encoding both prompts. |
| `positive` | main | The positive prompt (top text field): what the image should contain. |
| `negative` | main | The negative prompt (bottom text field): what the image should avoid. |
| `seed` | Advanced | Seed for choices and wildcards. The same seed always gives the same prompts (except in *shuffle*, *balanced* and *mutate* modes). By default it is randomized after each run (*control after generate*); set it to *fixed* to repeat a result. |
| `seed_mode` | Advanced | How choices and wildcards change from run to run: `random` (default), `deck`, `shuffle`, `balanced`, `combinations` or `mutate`. See [Seed modes](#seed-modes). |

### Outputs

| Output | Description |
|---|---|
| `positive` | Conditioning from the positive prompt. |
| `negative` | Conditioning from the negative prompt. |

When choices or wildcards change a prompt, the filled-in prompts and the seed are printed to the ComfyUI console.

### Prompt syntax

| Syntax | Result |
|---|---|
| `__name__` | A random line from the wildcard file `name.txt`. |
| `__folder/name__` | A random line from `folder/name.txt` inside a wildcards folder. |
| `{red\|green\|blue}` | One of the options at random. Options can be empty (`{big\|}`) and can nest (`{a\|{b\|c}}`). |
| `{3::cat\|dog}` | Weighted choice: `cat` is 3 times as likely as `dog`. Options without a weight count as 1. |
| `{2$$a\|b\|c}` | Two different options, joined with `, `. |
| `{1-3$$a\|b\|c}` | From 1 to 3 different options. `-2$$` means 0 to 2, and `2-$$` means 2 up to all of them. |
| `{2$$ and $$a\|b\|c}` | Two options joined with ` and ` instead of `, `. |
| `${hair=__color__}` | Sets the variable `hair`: its value is filled in once (choices and wildcards included) and outputs nothing. `${hair=!...}` (sd-dynamic-prompts style) works the same. |
| `${hair}` | The value of `hair`, anywhere in the positive or negative prompt: `${hair=__color__}${hair} hair, ${hair} ribbon` gives `red hair, red ribbon`. |
| `{sky\|!sea\|forest}` | Locked choice: always `sea`, in every seed mode, without rewriting the prompt. Remove the `!` to unlock. With several `!` options all of them are used. In `random` and `deck` the other choices keep their picks for the same seed; in `combinations` a locked choice counts once; in `mutate` it is never the one that changes. `3::!sea` works like `!3::sea`. |
| `// ...`, `/* ... */` | Comments, removed before encoding. |

To write `{`, `}` or `|` literally, put a backslash before it: `\{`, `\}`, `\|`. An option that should start with a real `!` is written `\!`.

Weights and counts can be combined, for example `{2$$3::hat|scarf|bow}`. Plain `{a|b}` choices give the same result for the same seed as before these options were added.

Commas left behind by empty options are cleaned up: `a girl, {|cat}, smile` becomes `a girl, smile` rather than `a girl, , smile`. Doubled commas, spaces before commas and commas at the start or end of the prompt are removed too.

Variables are shared by both prompts and can be set in a wildcard file line too (for example a character file that sets `${hair=...}`). A variable can be used before or after it is set; if it is set twice, the last value is used everywhere. Using a variable that is never set stops the run with an error that names it.

Prompt weights such as `(word:1.2)` and embeddings work as in the core node.

Lines picked from a wildcard file can themselves contain wildcards and `{a|b}` choices; they are filled in too, up to 50 levels deep (a wildcard that includes itself stops with an error instead of looping forever).

### Seed modes

In `random` mode every pick is independent, so `blue sky` can come up twice in a row while other options wait. `deck` and `shuffle` go through all the options before repeating one; `balanced` makes repeats rare instead of impossible. `combinations` goes through every combination of the whole prompt, and `mutate` changes one choice at a time.

| Mode | How it works | Seed |
|---|---|---|
| `random` | Every pick is random. Same as before seed modes existed. | The same seed gives the same prompt. |
| `deck` | Like dealing cards: the seed is a position in a shuffled deck of the options. Set *control after generate* to *increment*: each run takes the next card, every option comes once per round, then the deck is reshuffled (never starting with the option that just came). Rounds start at seeds that are multiples of the number of options (0, 5, 10… for 5 options), so start from such a seed (for example 0) to get no repeats from the first run. Options inside a picked option (`{cat {small\|big}\|dog}`, lines of a wildcard inside a wildcard) also take turns. | The same seed gives the same prompt, so a good result can be repeated. |
| `shuffle` | Like shuffle in a music player: the node remembers which options were already used and picks from the rest; when all were used, it starts over. Works with any *control after generate*, even *fixed*. The memory is kept in a file, so it continues after a restart. | Not used: the prompt is different every run and cannot be repeated from the seed (the filled-in prompt is in the console). |
| `balanced` | Like the pseudo-random distribution in games: an option that just came up gets a low chance, and the longer an option is missed, the higher its chance grows. Repeats are rare but possible (with 5 options: about 4% in a row instead of 20% in `random`, and no option waits more than about 13 runs instead of 40+). In the long run every option comes exactly as often as its weight says (`{3::cat\|dog}`: 75% / 25%). Works with any *control after generate*; the memory is kept in a file, as in `shuffle`. | Not used, as in `shuffle`. |
| `combinations` | The seed numbers every combination of all the choices, wildcards and variables in both prompts, so seeds 0, 1, 2… go through each combination exactly once, then start over (the seed is taken modulo the number of combinations). For example `{sky\|sea}, __color__ hair` with 3 colors has 6 combinations: seeds 0–5. The first choice changes fastest. The console shows the number, for example *combination 4 of 6*. Weights only matter as `0::` (never used); `{2$$a\|b\|c}` counts every set of 2 options once. Good for trying every character in every style: set *control after generate* to *increment* and start from 0. | The same seed gives the same prompt. |
| `mutate` | The first run picks at random; every next run keeps the last prompt and changes just one choice to a different option (a choice inside a newly picked option is picked fresh). Good for exploring variations of a result you like: keep running, and every image differs from the one before in one detail. The node remembers the last picks for these prompts in the memory file, so it continues after a restart; editing the prompt starts from a fresh random pick. | Not used, as in `shuffle`. |

In `deck` and `shuffle` modes:

- The same wildcard or choice used more than once in a prompt gives different options: `__color__ hair, __color__ eyes` never gives `red hair, red eyes` (unless the file has only one line).
- A weight is the number of times the option comes per round: `{3::cat|dog}` gives `cat` 3 times and `dog` once. Weights are rounded to whole numbers, at least 1.
- `{2$$a|b|c}` takes the next options in the order, still without duplicates in one pick.

### Memory file

`shuffle`, `balanced` and `mutate` remember what came up before in `ComfyUI/user/DiceForge/seed_memory.sqlite`, so they continue where they stopped after ComfyUI restarts, and the memory doesn't take RAM: only the list being picked from is read, when it is picked from.

- One entry per list of options (a `{a|b}` choice or a wildcard file) and mode, plus one per prompt for `mutate`. Editing a list or a wildcard file starts that list over.
- `shuffle` stores just its place in the shuffled order, a few bytes even for a wildcard file with thousands of lines. `balanced` stores a number per option (about 7 bytes each).
- The least recently used entries are forgotten past 20,000 entries.
- To start everything over, delete the file (ComfyUI can stay running).

### Wildcard files

- Put wildcard files in `ComfyUI/models/wildcards`, for example `ComfyUI/models/wildcards/color.txt`. Subfolders work too: `ComfyUI/models/wildcards/styles/photo.txt` is `__styles/photo__`.
- More folders can be added with a `wildcards:` entry in ComfyUI's `extra_model_paths.yaml`.
- One option per line. Empty lines and lines starting with `#` are skipped. Files are read as UTF-8.
- A missing or empty wildcard file stops the run with an error that names the file and the wildcards folders.
- The node runs again when a wildcard file changes, even if the prompts and the seed stay the same.

Example `color.txt`:

```text
# colors for __color__
crimson red
deep {navy|royal} blue
emerald green
```

### Notes

- Choices and wildcards are filled in by the node, from its `seed`, not by the ComfyUI frontend. The saved workflow keeps the prompts with `__name__` and `{a|b}`, and the same seed gives the same result again.
- Positive and negative are filled in from the same seed, one after the other, so the same wildcard can pick different lines in each.
