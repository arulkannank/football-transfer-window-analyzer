"""Parsing & normalization helpers shared across scrapers."""
from __future__ import annotations

import datetime as _dt
import re
import unicodedata

# ----- money / market value -------------------------------------------------
_NUM = re.compile(r"([\d][\d.,]*)\s*(bn|m|k|th)?", re.I)


def parse_money(text: str | None) -> dict:
    """Parse a Transfermarkt fee string.

    Returns {'eur': int|None, 'loan': bool, 'free': bool, 'known': bool}.
    'known' is False for '-', '?', 'draft' etc. (fee genuinely unknown/none).
    A free or loan move has eur=0 unless an explicit loan fee is present.
    """
    out = {"eur": None, "loan": False, "free": False, "known": False}
    if not text:
        return out
    t = text.strip().lower().replace("\xa0", " ")
    if not t or t in {"-", "?", "draft", "n.a.", "na"}:
        return out
    if "loan" in t:
        out["loan"] = True
        if "end of loan" in t or "loan transfer" in t or "loan fee" not in t:
            out["eur"] = 0
            out["known"] = True
            # a loan with an explicit fee falls through to number parsing below
            if "loan fee" not in t:
                return out
    if "free" in t:
        out["free"] = True
        out["eur"] = 0
        out["known"] = True
        return out
    m = _NUM.search(t)
    if not m:
        return out
    num = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    mult = {"bn": 1_000_000_000, "m": 1_000_000, "k": 1_000, "th": 1_000}.get(unit, 1)
    out["eur"] = int(round(num * mult))
    out["known"] = True
    return out


def parse_mv(text: str | None) -> int | None:
    """Parse a market-value string like '€75.00m' -> 75000000."""
    if not text:
        return None
    t = text.strip().lower()
    if not t or t in {"-", "?"}:
        return None
    m = _NUM.search(t)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    mult = {"bn": 1_000_000_000, "m": 1_000_000, "k": 1_000, "th": 1_000}.get(unit, 1)
    return int(round(num * mult))


# ----- text / names ---------------------------------------------------------
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def norm_name(name: str | None) -> str:
    """Normalize a player name for cross-source matching."""
    if not name:
        return ""
    s = strip_accents(name).lower()
    s = s.replace(".", " ").replace("-", " ").replace("'", " ")
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def name_keys(name: str) -> set[str]:
    """Candidate match keys: full normalized name + 'firstinitial lastname'."""
    n = norm_name(name)
    keys = {n}
    parts = n.split()
    if len(parts) >= 2:
        keys.add(f"{parts[0][0]} {parts[-1]}")
        keys.add(parts[-1])  # surname only (weak; used as last resort)
    return {k for k in keys if k}


# ----- ids / dates ----------------------------------------------------------
_VEREIN = re.compile(r"/verein/(\d+)")
_SPIELER = re.compile(r"/spieler/(\d+)")


def club_id_from_href(href: str | None) -> str | None:
    if not href:
        return None
    m = _VEREIN.search(href)
    return m.group(1) if m else None


def player_id_from_href(href: str | None) -> str | None:
    if not href:
        return None
    m = _SPIELER.search(href)
    return m.group(1) if m else None


def parse_date(s: str | None) -> _dt.date | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y", "%d.%m.%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def window_of(date: _dt.date | None) -> str:
    """Map a transfer date to its window. Jan/Feb -> winter, else summer."""
    if date is None:
        return "summer"
    return "winter" if date.month in (1, 2) else "summer"


def season_label(year: int) -> str:
    return f"{year % 100:02d}/{(year + 1) % 100:02d}"


def season_end_date(year: int) -> _dt.date:
    """End of the <year>/<year+1> season (used for 'end of season' MV lookup)."""
    return _dt.date(year + 1, 6, 30)


def parse_int(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def parse_minutes(text: str | None) -> int:
    """'2.788'' -> 2788 ; '-' -> 0. TM uses '.' as a thousands separator."""
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0
