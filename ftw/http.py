"""Cached, rate-limited, browser-impersonating HTTP client.

Both Transfermarkt and SofaScore fingerprint TLS / inspect headers, so we use
curl_cffi's Chrome impersonation. Every response is cached to disk so re-runs and
crashes are cheap and resumable; only cache misses hit the network (and only those
are rate-limited).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import random
import threading
import time
from pathlib import Path

from curl_cffi import requests as cffi

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = DATA_DIR / "cache"

# Politeness: random delay between *live* requests (cache hits are free).
# Per-client; with N worker threads the aggregate rate is ~N/avg_delay.
MIN_DELAY = 0.9
MAX_DELAY = 2.0
MAX_RETRIES = 4
TIMEOUT = 30

_DESKTOP_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class FetchError(RuntimeError):
    pass


class Client:
    """One client per data source ('tm' or 'sofa') -> isolated cache namespace."""

    def __init__(self, namespace: str, *, referer: str | None = None,
                 want_json: bool = False, verbose: bool = True):
        self.namespace = namespace
        self.referer = referer
        self.want_json = want_json
        self.verbose = verbose
        self.cache_dir = CACHE_DIR / namespace
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._session = cffi.Session(impersonate="chrome")
        self.stats = {"hits": 0, "misses": 0, "errors": 0}

    # -- cache --------------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{h}.gz"

    def _read_cache(self, path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def _write_cache(self, path: Path, text: str) -> None:
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            f.write(text)
        tmp.replace(path)

    # -- fetch --------------------------------------------------------------
    def _throttle(self) -> None:
        with self._lock:
            wait = (self._last_request + random.uniform(MIN_DELAY, MAX_DELAY)) - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.time()

    def get(self, url: str, *, params: dict | None = None,
            force: bool = False) -> str:
        """Return response text, from cache when available."""
        full = url
        if params:
            from urllib.parse import urlencode
            full = f"{url}?{urlencode(params)}"
        path = self._cache_path(full)
        if not force:
            cached = self._read_cache(path)
            if cached is not None:
                self.stats["hits"] += 1
                return cached

        headers = dict(_DESKTOP_HEADERS)
        if self.referer:
            headers["Referer"] = self.referer
        if self.want_json:
            headers["Accept"] = "application/json, text/plain, */*"

        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            try:
                r = self._session.get(full, headers=headers, timeout=TIMEOUT)
            except Exception as e:  # network/TLS errors
                last_exc = e
                time.sleep(min(30, 2 ** attempt + random.random()))
                continue
            if r.status_code == 200:
                text = r.text
                self._write_cache(path, text)
                self.stats["misses"] += 1
                if self.verbose:
                    print(f"  [{self.namespace}] GET {full[:90]} ({len(text)//1024}KB)")
                return text
            if r.status_code in (404, 410):
                # Cache the miss so we don't retry forever; caller handles empty.
                self._write_cache(path, "")
                self.stats["misses"] += 1
                return ""
            if r.status_code in (403, 429, 500, 502, 503, 504):
                backoff = min(60, 2 ** attempt + random.uniform(0, 3))
                if self.verbose:
                    print(f"  [{self.namespace}] {r.status_code} on {full[:80]} "
                          f"-> retry {attempt}/{MAX_RETRIES} in {backoff:.0f}s")
                time.sleep(backoff)
                last_exc = FetchError(f"HTTP {r.status_code}")
                continue
            last_exc = FetchError(f"HTTP {r.status_code} for {full}")
            break

        self.stats["errors"] += 1
        raise FetchError(f"Failed after {MAX_RETRIES} attempts: {full} ({last_exc})")

    def get_json(self, url: str, *, params: dict | None = None,
                 force: bool = False):
        text = self.get(url, params=params, force=force)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
