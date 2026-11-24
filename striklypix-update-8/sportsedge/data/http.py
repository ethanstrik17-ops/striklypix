"""Tiny HTTP client with on-disk JSON caching, retries and polite rate limiting."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import requests

_LAST_CALL = [0.0]


class CachedClient:
    def __init__(self, cache_dir: str, delay: float = 0.35, headers: dict | None = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (sportsedge research tool)"})
        if headers:
            self.session.headers.update(headers)

    def _key(self, url: str, params: dict | None) -> Path:
        raw = url + "?" + json.dumps(params or {}, sort_keys=True)
        return self.cache_dir / (hashlib.sha1(raw.encode()).hexdigest() + ".json")

    def get_json(self, url: str, params: dict | None = None, ttl: float | None = 3600,
                 headers: dict | None = None, retries: int = 3, timeout: int = 30):
        """ttl=None caches forever (use for finished games); ttl=0 always refetches."""
        path = self._key(url, params)
        if path.exists() and (ttl is None or time.time() - path.stat().st_mtime < ttl):
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                path.unlink(missing_ok=True)
        last_err = None
        for attempt in range(retries):
            wait = self.delay - (time.time() - _LAST_CALL[0])
            if wait > 0:
                time.sleep(wait)
            try:
                _LAST_CALL[0] = time.time()
                r = self.session.get(url, params=params, headers=headers, timeout=timeout)
                if r.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data))
                os.replace(tmp, path)
                self.last_headers = r.headers
                return data
            except (requests.RequestException, ValueError) as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"GET failed for {url}: {last_err}")
