"""Transfer classification.

A signing can carry several labels. The rubric bucket (starter-type vs
rotation-type) and the window weight (2 vs 1) follow from them.

Labels
  addresses_problem  : bought into a flagged problem position (no prior starter)
  improves_problem   : bought into a position whose avg rating trails the league
  replaces_sold      : same position group as a player sold in the same season
  significant_outlay : fee > 1.25x the club's average spend per transfer
  rotation_option    : age > 26, non-problem area, fee < 0.5x avg spend

Bucket
  rotation-type (weight 1) when the signing is a clear low-investment depth buy
  (labelled rotation_option, or simply cheap < 0.5x avg in a non-problem area
  that neither replaces a sale nor improves a weak position). Everything else is
  starter-type (weight 2).
"""
from __future__ import annotations

import config
from .dataset import Dataset
from .models import Signing
from .problems import ProblemFlag


def compute_avg_spend(ds: Dataset) -> dict[str, float]:
    """{club_id: average spend per incoming transfer} over the full period.

    Frees count as 0 spend; transfers with an unknown fee are excluded from the
    count (we can't say what was spent)."""
    spend: dict[str, list[int]] = {}
    for (club_id, season, window), tr in ds.transfers.items():
        for a in tr.get("arrivals", []):
            fee = a.get("fee", {})
            if fee.get("known"):
                spend.setdefault(club_id, []).append(fee.get("eur") or 0)
    return {c: (sum(v) / len(v)) for c, v in spend.items() if v}


def departed_groups(ds: Dataset, club_id: str, season: int) -> dict[str, int]:
    """{group: count} of players sold by the club across both windows of season."""
    out: dict[str, int] = {}
    for window in config.WINDOWS:
        tr = ds.transfers.get((club_id, season, window))
        if not tr:
            continue
        for d in tr.get("departures", []):
            if d.get("fee", {}).get("loan"):
                continue                      # a loan-out isn't a sale to replace
            g = d.get("group")
            if g:
                out[g] = out.get(g, 0) + 1
    return out


def classify(signing: Signing, flags: dict[str, ProblemFlag],
             avg_spend: float | None, sold_groups: dict[str, int]) -> None:
    """Mutate `signing`: set classification labels, bucket, weight."""
    g = signing.group
    flag = flags.get(g)
    fee = signing.fee_eur if (signing.fee_known and signing.fee_eur is not None) else None

    labels: list[str] = []
    addresses = bool(flag and flag.is_problem)
    improves = bool(flag and flag.rating_below_avg)
    replaces = sold_groups.get(g, 0) > 0
    if addresses:
        labels.append("addresses_problem")
    if improves:
        labels.append("improves_problem")
    if replaces:
        labels.append("replaces_sold")

    sig_outlay = bool(avg_spend and fee is not None and fee > 1.25 * avg_spend)
    if sig_outlay:
        labels.append("significant_outlay")

    cheap = bool(avg_spend is not None and fee is not None and fee < 0.5 * avg_spend)
    # free signings (fee known == 0) count as cheap regardless of avg
    if signing.is_free or (signing.fee_known and (signing.fee_eur or 0) == 0):
        cheap = True
    non_problem = not addresses
    # the slot is already well covered if an existing player there rates above the
    # league average -> a new signing in it is depth, not a starter need
    covered = bool(flag and flag.has_above_avg_incumbent)

    rotation_option = bool(
        non_problem and (
            ((signing.age_at_signing or 0) > 24 and cheap)   # older, cheap depth buy
            or covered                                        # slot already well covered
        ))
    if rotation_option:
        labels.append("rotation_option")

    # rubric bucket: a clear need (addresses/improves a problem) is always starter-type
    is_rotation = (not addresses and not improves) and (
        rotation_option or (cheap and not replaces))
    signing.classification = labels or ["squad_addition"]
    signing.addressed_problem = addresses
    signing.is_starter_signing = not is_rotation
    signing.weight = 2.0 if signing.is_starter_signing else 1.0
