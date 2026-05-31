# Sensitivity analysis

Baseline overall mean: **3.403/10**. Each threshold is moved down and up; high Spearman ρ and top-20 overlap mean the club rankings barely move (robust conclusion).

| Threshold | Tested | Spearman ρ vs baseline | Top-20 kept | Mean Δ |
|---|---|---:|---:|---:|
| Starter minutes share | 0.65→0.55 | 0.972 | 18/20 | +0.096 |
| Starter minutes share | 0.65→0.75 | 0.976 | 18/20 | -0.083 |
| Efficiency cutoff | 0.3→0.2 | 1.0 | 20/20 | +0.002 |
| Efficiency cutoff | 0.3→0.4 | 1.0 | 20/20 | -0.001 |
| Profit pivot (×) | 2.5→2.0 | 0.992 | 19/20 | -0.034 |
| Profit pivot (×) | 2.5→3.0 | 0.997 | 20/20 | +0.007 |
| Starter minutes full | 0.9→0.8 | 0.996 | 20/20 | +0.272 |
| Starter minutes full | 0.9→1.0 | 0.997 | 19/20 | -0.253 |
| Insignificant fee ratio | 0.2→0.1 | 0.999 | 20/20 | -0.004 |
| Insignificant fee ratio | 0.2→0.3 | 0.999 | 20/20 | +0.008 |
| Insignificant minutes | 0.1→0.05 | 0.988 | 19/20 | -0.047 |
| Insignificant minutes | 0.1→0.15 | 0.99 | 18/20 | +0.034 |
| Rotation min age | 24→23 | 1.0 | 20/20 | +0.0 |
| Rotation min age | 24→26 | 1.0 | 20/20 | +0.0 |

Lowest Spearman ρ across all perturbations: **0.972**. Rankings are **robust** — every perturbation keeps ρ high.