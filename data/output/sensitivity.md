# Sensitivity analysis

Baseline overall mean: **3.355/10**. Each threshold is moved down and up; high Spearman ρ and top-20 overlap mean the club rankings barely move (robust conclusion).

| Threshold | Tested | Spearman ρ vs baseline | Top-20 kept | Mean Δ |
|---|---|---:|---:|---:|
| Starter minutes share | 0.65→0.55 | 0.994 | 19/20 | +0.052 |
| Starter minutes share | 0.65→0.75 | 0.995 | 19/20 | -0.052 |
| Efficiency cutoff | 0.3→0.2 | 1.0 | 20/20 | +0.002 |
| Efficiency cutoff | 0.3→0.4 | 1.0 | 20/20 | -0.001 |
| Profit pivot (×) | 2.5→2.0 | 0.992 | 19/20 | -0.041 |
| Profit pivot (×) | 2.5→3.0 | 0.997 | 20/20 | +0.01 |
| Starter minutes full | 0.9→0.8 | 0.996 | 19/20 | +0.288 |
| Starter minutes full | 0.9→1.0 | 0.997 | 20/20 | -0.267 |
| Insignificant fee ratio | 0.2→0.1 | 0.999 | 20/20 | -0.004 |
| Insignificant fee ratio | 0.2→0.3 | 0.999 | 19/20 | +0.009 |
| Insignificant minutes | 0.1→0.05 | 0.988 | 18/20 | -0.049 |
| Insignificant minutes | 0.1→0.15 | 0.991 | 19/20 | +0.036 |
| Rotation min age | 24→23 | 1.0 | 20/20 | +0.0 |
| Rotation min age | 24→26 | 1.0 | 20/20 | +0.0 |

Lowest Spearman ρ across all perturbations: **0.988**. Rankings are **robust** — every perturbation keeps ρ high.