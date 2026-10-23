### LoRA Stack

![LoRA Stack after Load Checkpoint: a random strength, a group of two LoRAs taking turns, and base model warnings](images/lora_stack.png)

Node id: `DiceForgeLoraStack`. Several LoRAs in one node, like rgthree's *Power Lora Loader*, applied in order to the model and CLIP.

Each row: **⋮⋮** (drag to reorder), on/off, the LoRA (click its name to pick another one in the [LoRA Browser](https://github.com/DeduxOnline/ComfyUI-DiceForge#lora-browser)), **ℹ** ([Model info](https://github.com/DeduxOnline/ComfyUI-DiceForge#model-info)), **🏷** (trigger words), a **group**, **🎲**, the strength and **✕** (remove). **＋ Add LoRA** opens the LoRA Browser: **+ Add** adds a row, as many as you like. The browser starts on **Fits the model (…)**: the LoRAs made for the connected model's base, the same family (marked ⚠️, for example Pony LoRAs on an Illustrious model) and the ones not looked up on Civitai yet; LoRAs of another family are hidden. *All base models* in the filter shows every LoRA. The mouse wheel over a strength changes it by 0.05. A row whose file is missing is outlined in red.

- **Separate CLIP strength** (under the rows): each row gets a second strength (*C*) for the CLIP; otherwise the same strength is used for both.
- **🎲 Random strength:** the row gets two values, and each run picks a strength between them (in steps of 0.05) by the seed mode. With `deck` or `sequential` and *control after generate* on *increment*, 0.50–0.90 goes through all 9 strengths before repeating one. With a separate CLIP strength, the range is for the model strength only.
- **🏷 Trigger words:** which of the LoRA's trigger words go to the `triggers` output. The list shows the words you gave in Model info (*yours*) and Civitai's (*Civitai*); tick the ones you want, or type your own words (*added*). **Default** follows the LoRA's trigger words (yours, else Civitai's), also when they change; **None** adds no words from this LoRA. With your own choice the button shows the number of words (🏷3), with None it is struck through. The choice is kept in the row, so presets keep it too.
- **Groups (A–D):** the LoRAs of a group take turns. Under the rows, *Group A: use 1 to 1 of 3* sets how many of them each run uses (0 to all of them). Every set of LoRAs is one option of the seed mode, so `deck` or `shuffle` goes through every combination before repeating one: three style LoRAs with *use 1 to 2* give 6 combinations. LoRAs turned off do not take part.

| Input | Description |
|---|---|
| `model` | The diffusion model the LoRAs are applied to. |
| `clip` | Optional. The CLIP model they are applied to; unconnected, only the model changes. |
| `seed` | Seed for random strengths and groups. |
| `seed_mode` | Advanced. `random`, `deck`, `shuffle`, `balanced` or `sequential`, as in [Seed modes for sizes](https://github.com/DeduxOnline/ComfyUI-DiceForge#seed-modes-for-sizes). Without 🎲 and groups the seed changes nothing. |

| Output | Description |
|---|---|
| `model`, `clip` | With the LoRAs applied. |
| `triggers` | The trigger words of the LoRAs that were applied, as set with 🏷 (by default your own from Model info, else Civitai's; each word once), for example to connect to a text node or to put in CLIP Dual Text Encode. |
| `lora_info` | What was applied, for example `detail 0.65, style_b 1` (with the CLIP strength after a `/` when it differs), for a file name, a note or Dice Grid. |

**Base model check.** The node follows its `model` input back to the loader (**Load Checkpoint**, **Load Diffusion Model**, **Load Diffusion Model + CLIP**…, through nodes in between like other LoRA loaders or *Model Sampling*) and shows the model's base under the rows, for example *Model: waiNSFW · Illustrious*. Each LoRA's base is compared with it:

- **⚠️ (orange):** same model family, another base, for example a Pony LoRA on an Illustrious model. It may work, but not as well.
- **⛔ (red):** another family, for example a Flux or SD 1.5 LoRA on an SDXL-type model. It does not work.

Hover the sign for the details. The bases are the Civitai data of [Model info](https://github.com/DeduxOnline/ComfyUI-DiceForge#model-info): a model or LoRA that was never looked up (🔍 Civitai in its browser, or Model info) gets no warning, and the check never hashes anything by itself. It follows changes in the graph within a few seconds.

**Presets.** **💾 Save preset** saves the rows (strengths, 🎲 ranges, groups, separate CLIP) as a file in `ComfyUI/user/DiceForge/lora_presets`, named as you like. **📂 Presets** lists them:

- **Replace** puts a preset's rows in the node, instead of its rows; **+ Add** adds them after its rows.
- **⬇ File** downloads the preset file, to share it or keep a copy; **⬆ Import file…** reads preset files (several at once), and they appear in the list of every LoRA Stack.
- **🗑** deletes a preset.

A preset refers to the LoRAs by their file names in the loras folder: on another computer, a LoRA that is not there is outlined in red.

The rows are saved in the workflow (in the node's hidden `loras` input, as JSON). The node reads each LoRA file once and keeps it in memory while it is in the stack, and runs again when you change trigger words in Model info.
