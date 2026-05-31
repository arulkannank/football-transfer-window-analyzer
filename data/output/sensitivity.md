# Sensitivity analysis

Baseline overall mean: **2.908/10**. Each threshold is moved down and up; high Spearman ρ and top-20 overlap mean the club rankings barely move (robust conclusion).

| Threshold | Tested | Spearman ρ vs baseline | Top-20 kept | Mean Δ |
|---|---|---:|---:|---:|
| Starter minutes share | 0.65→0.55 | 0.942 | 15/20 | +0.153 |
| Starter minutes share | 0.65→0.75 | 0.955 | 16/20 | -0.115 |
| Efficiency cutoff | 0.3→0.2 | 1.0 | 20/20 | +0.002 |
| Efficiency cutoff | 0.3→0.4 | 1.0 | 20/20 | -0.002 |
| Profit pivot (×) | 2.5→2.0 | 0.995 | 19/20 | -0.021 |
| Profit pivot (×) | 2.5→3.0 | 0.998 | 20/20 | +0.002 |
| Starter minutes full | 0.9→0.8 | 0.997 | 19/20 | +0.218 |
| Starter minutes full | 0.9→1.0 | 0.997 | 19/20 | -0.198 |
| Insignificant fee ratio | 0.2→0.1 | 0.998 | 20/20 | -0.014 |
| Insignificant fee ratio | 0.2→0.3 | 0.998 | 20/20 | +0.013 |
| Insignificant minutes | 0.1→0.05 | 0.991 | 18/20 | -0.042 |
| Insignificant minutes | 0.1→0.15 | 0.992 | 19/20 | +0.031 |
| Rotation min age | 24→23 | 0.996 | 19/20 | +0.01 |
| Rotation min age | 24→26 | 0.992 | 19/20 | -0.018 |

Lowest Spearman ρ across all perturbations: **0.942**. Rankings are **robust** — every perturbation keeps ρ high.