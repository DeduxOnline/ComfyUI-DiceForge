Settings for an X/Y comparison grid: each run gives KSampler the values of one cell and Dice Grid its labels; ▶ Queue on the node queues every cell.

## Inputs

| Input | Type | Description |
|---|---|---|
| `x_type` | COMBO | What changes from column to column. |
| `x_values` | STRING | Values, separated by commas or new lines. Numbers: 4, 5.5, 7 or ranges 4-8 (step 1) and 3.5-7:0.5. Sampler, scheduler: names, \* for all. LoRA: file names, with or without folder and extension, patterns like style/\*, None for no LoRA. |
| `y_type` | COMBO | What changes from row to row (none: one row). |
| `y_values` | STRING | Values, separated by commas or new lines. Numbers: 4, 5.5, 7 or ranges 4-8 (step 1) and 3.5-7:0.5. Sampler, scheduler: names, \* for all. LoRA: file names, with or without folder and extension, patterns like style/\*, None for no LoRA. |
| `index` | INT | The cell of this run, row by row (▶ Queue sets it for each run). |
| `seed` | INT | Seed of every cell, unless an axis is seed. It stays the same from cell to cell. |
| `steps` | INT | Steps of every cell, unless an axis is steps. |
| `cfg` | FLOAT | CFG of every cell, unless an axis is cfg. |
| `sampler_name` | COMBO | Sampler of every cell, unless an axis is sampler. |
| `scheduler` | COMBO | Scheduler of every cell, unless an axis is scheduler. |
| `model` (optional) | MODEL | The model, for a LoRA (lora\_name, or a lora axis). Passed through otherwise. |
| `clip` (optional) | CLIP | The CLIP, for a LoRA. Passed through otherwise. |

## Advanced inputs

Under **Show advanced inputs** on the node.

| Input | Type | Description |
|---|---|---|
| `denoise` | FLOAT | Denoise of every cell, unless an axis is denoise. |
| `lora_name` | COMBO | LoRA of every cell (for a lora strength axis), unless an axis is lora. Applied to model and clip. |
| `lora_strength` | FLOAT | LoRA strength, unless an axis is lora strength. |
| `variation_seed` (optional) | INT | Variation seed of every cell (as Variation Seed), unless an axis is variation seed. |
| `variation_strength` (optional) | FLOAT | Variation strength of every cell (0: none). A variation seed axis with strength 0.1: variations of one picture. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `model` | MODEL | The model, with this cell's LoRA. |
| `clip` | CLIP | The CLIP, with this cell's LoRA. |
| `seed` | INT | For KSampler's seed. |
| `steps` | INT | For KSampler's steps. |
| `cfg` | FLOAT | For KSampler's cfg. |
| `sampler_name` | ['euler', 'euler_cfg_pp', 'euler_ancestral', 'euler_ancestral_cfg_pp', 'heun', 'heunpp2', 'exp_heun_2_x0', 'exp_heun_2_x0_sde', 'dpm_2', 'dpm_2_ancestral', 'lms', 'dpm_fast', 'dpm_adaptive', 'dpmpp_2s_ancestral', 'dpmpp_2s_ancestral_cfg_pp', 'dpmpp_sde', 'dpmpp_sde_gpu', 'dpmpp_2m', 'dpmpp_2m_cfg_pp', 'dpmpp_2m_sde', 'dpmpp_2m_sde_gpu', 'dpmpp_2m_sde_heun', 'dpmpp_2m_sde_heun_gpu', 'dpmpp_3m_sde', 'dpmpp_3m_sde_gpu', 'ddpm', 'lcm', 'ipndm', 'ipndm_v', 'deis', 'cfgpp_ud10_ab', 'res_multistep', 'res_multistep_cfg_pp', 'res_multistep_ancestral', 'res_multistep_ancestral_cfg_pp', 'gradient_estimation', 'gradient_estimation_cfg_pp', 'er_sde', 'seeds_2', 'seeds_3', 'sa_solver', 'sa_solver_pece', 'ddim', 'uni_pc', 'uni_pc_bh2'] | For KSampler's sampler\_name. |
| `scheduler` | ['simple', 'sgm_uniform', 'karras', 'exponential', 'ddim_uniform', 'beta', 'normal', 'linear_quadratic', 'kl_optimal'] | For KSampler's scheduler. |
| `denoise` | FLOAT | For KSampler's denoise. |
| `x_label` | STRING | For Dice Grid's label: the column. |
| `y_label` | STRING | For Dice Grid's row\_label: the row. |
| `count` | INT | Images in the grid, for Dice Grid's count. |
| `columns` | INT | Values on X, for Dice Grid's columns (one row per Y value). |
| `new_grid` | BOOLEAN | True for the first cell, for Dice Grid's new\_grid: each plot starts a fresh grid. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#xy-plot): examples, tips, and how it works with the other nodes.
