Picks a sampler and scheduler pair from the listed ones for KSampler, with the DiceForge seed modes (deck, sequential... go through every pair once).

## Inputs

| Input | Type | Description |
|---|---|---|
| `samplers` | STRING | Samplers to pick from, separated by commas or new lines (the names in KSampler's list). \* for every sampler. |
| `schedulers` | STRING | Schedulers to pick from, separated by commas or new lines. \* for every scheduler. Every sampler is paired with every scheduler. |
| `seed` | INT | Seed for the pick. With deck or sequential, set control after generate to increment. |

## Advanced inputs

Under **Show advanced inputs** on the node.

| Input | Type | Description |
|---|---|---|
| `seed_mode` | COMBO | How the pick changes from run to run. random: every pick is independent, so the same one can come up again soon. deck: the seed steps through a shuffled order of the sampler and scheduler pairs; with control after generate on increment, every one comes once before any repeats. Reproducible. shuffle: like shuffle in a music player, the node remembers the sampler and scheduler pairs already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same pick again. balanced: one just picked gets a low chance, and those not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same pick again. sequential: the seed is the position in the list (each sampler with every scheduler, in the listed order), so seeds 0, 1, 2... go through the sampler and scheduler pairs in order. Reproducible. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `sampler_name` | ['euler', 'euler_cfg_pp', 'euler_ancestral', 'euler_ancestral_cfg_pp', 'heun', 'heunpp2', 'exp_heun_2_x0', 'exp_heun_2_x0_sde', 'dpm_2', 'dpm_2_ancestral', 'lms', 'dpm_fast', 'dpm_adaptive', 'dpmpp_2s_ancestral', 'dpmpp_2s_ancestral_cfg_pp', 'dpmpp_sde', 'dpmpp_sde_gpu', 'dpmpp_2m', 'dpmpp_2m_cfg_pp', 'dpmpp_2m_sde', 'dpmpp_2m_sde_gpu', 'dpmpp_2m_sde_heun', 'dpmpp_2m_sde_heun_gpu', 'dpmpp_3m_sde', 'dpmpp_3m_sde_gpu', 'ddpm', 'lcm', 'ipndm', 'ipndm_v', 'deis', 'cfgpp_ud10_ab', 'res_multistep', 'res_multistep_cfg_pp', 'res_multistep_ancestral', 'res_multistep_ancestral_cfg_pp', 'gradient_estimation', 'gradient_estimation_cfg_pp', 'er_sde', 'seeds_2', 'seeds_3', 'sa_solver', 'sa_solver_pece', 'ddim', 'uni_pc', 'uni_pc_bh2'] | Connect to the sampler\_name input of KSampler (or KSampler Advanced). |
| `scheduler` | ['simple', 'sgm_uniform', 'karras', 'exponential', 'ddim_uniform', 'beta', 'normal', 'linear_quadratic', 'kl_optimal'] | Connect to the scheduler input of KSampler (or KSampler Advanced). |
| `label` | STRING | "sampler / scheduler", for example for the label of Dice Grid. |
| `sampler_text` | STRING | The sampler name as text, for example for the row\_label of an XY Dice Grid. |
| `scheduler_text` | STRING | The scheduler name as text, for example for the label of an XY Dice Grid. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#random-sampler): examples, tips, and how it works with the other nodes.
