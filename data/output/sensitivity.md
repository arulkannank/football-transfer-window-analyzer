# Sensitivity analysis

Baseline overall mean: **3.284/10**. Each threshold is moved down and up; high Spearman ρ and top-20 overlap mean the club rankings barely move (robust conclusion).

| Threshold | Tested | Spearman ρ vs baseline | Top-20 kept | Mean Δ |
|---|---|---:|---:|---:|
| Starter minutes share | 0.65→0.55 | 0.999 | 20/20 | +0.039 |
| Starter minutes share | 0.65→0.75 | 0.999 | 19/20 | -0.04 |
| Efficiency cutoff | 0.3→0.2 | 1.0 | 20/20 | +0.002 |
| Efficiency cutoff | 0.3→0.4 | 1.0 | 20/20 | +0.0 |
| Profit pivot (×) | 2.5→2.0 | 0.995 | 19/20 | -0.055 |
| Profit pivot (×) | 2.5→3.0 | 0.998 | 19/20 | +0.018 |
| Starter minutes full | 0.9→0.8 | 0.998 | 19/20 | +0.305 |
| Starter minutes full | 0.9→1.0 | 0.998 | 19/20 | -0.283 |
| Insignificant fee ratio | 0.2→0.1 | 1.0 | 20/20 | -0.003 |
| Insignificant fee ratio | 0.2→0.3 | 0.999 | 20/20 | +0.007 |
| Insignificant minutes | 0.1→0.05 | 0.996 | 16/20 | -0.031 |
| Insignificant minutes | 0.1→0.15 | 0.996 | 19/20 | +0.026 |
| Rotation min age | 24→23 | 1.0 | 20/20 | +0.0 |
| Rotation min age | 24→26 | 1.0 | 20/20 | +0.0 |

Lowest Spearman ρ across all perturbations: **0.995**. Rankings are **robust** — every perturbation keeps ρ high.