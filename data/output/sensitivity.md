# Sensitivity analysis

Baseline overall mean: **2.818/10**. Each threshold is moved down and up; high Spearman ρ and top-20 overlap mean the club rankings barely move (robust conclusion).

| Threshold | Tested | Spearman ρ vs baseline | Top-20 kept | Mean Δ |
|---|---|---:|---:|---:|
| Starter minutes share | 0.65→0.55 | 0.974 | 19/20 | +0.085 |
| Starter minutes share | 0.65→0.75 | 0.985 | 19/20 | -0.071 |
| Efficiency cutoff | 0.3→0.2 | 1.0 | 20/20 | +0.002 |
| Efficiency cutoff | 0.3→0.4 | 1.0 | 20/20 | -0.002 |
| Profit pivot (×) | 2.5→2.0 | 0.993 | 19/20 | -0.022 |
| Profit pivot (×) | 2.5→3.0 | 0.997 | 20/20 | +0.002 |
| Starter minutes full | 0.9→0.8 | 0.997 | 19/20 | +0.225 |
| Starter minutes full | 0.9→1.0 | 0.997 | 19/20 | -0.205 |
| Insignificant fee ratio | 0.2→0.1 | 0.998 | 20/20 | -0.012 |
| Insignificant fee ratio | 0.2→0.3 | 0.997 | 19/20 | +0.013 |
| Insignificant minutes | 0.1→0.05 | 0.99 | 17/20 | -0.04 |
| Insignificant minutes | 0.1→0.15 | 0.994 | 19/20 | +0.028 |
| Rotation min age | 24→23 | 1.0 | 20/20 | +0.0 |
| Rotation min age | 24→26 | 1.0 | 20/20 | +0.0 |

Lowest Spearman ρ across all perturbations: **0.974**. Rankings are **robust** — every perturbation keeps ρ high.