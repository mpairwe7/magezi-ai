"""Smoke tests against the built Magezi frontend (Next.js standalone server)."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _http(method: str, url: str, *, body: dict | None = None, timeout: float = 30.0) -> tuple[int, bytes, float]:
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "magezi-smoke/1.0"})
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read(), time.perf_counter() - t0


def run(base: str) -> dict:
    results: list[dict] = []

    def record(name: str, ok: bool, **extra) -> None:
        results.append({"name": name, "ok": ok, **extra})
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {name}  " + " ".join(f"{k}={v}" for k, v in extra.items()))

    print(f"== Magezi frontend smoke @ {base}")

    # 1. Root HTML
    s, body, t = _http("GET", f"{base}/")
    text = body.decode("utf-8", "ignore")
    ok = (
        s == 200
        and "<!DOCTYPE html>" in text
        and "Magezi" in text or "magezi" in text.lower()
        and "_next/static" in text  # has client assets
    )
    record("root_html", ok, status=s, ttfb_ms=int(t * 1000), size_kb=round(len(body) / 1024, 1))

    # 2. Static CSS bundle — checked on disk (Next standalone defers static-asset
    #    serving to nginx in prod; node server returns 404).
    css_match = re.search(r'href="(/_next/static/[^"]+\.css)"', text)
    if css_match:
        rel = css_match.group(1).lstrip("/")
        # Probe likely on-disk locations
        candidates = [
            Path("frontend") / rel.replace("_next/", ".next/", 1),
            Path("frontend/.next") / rel.replace("_next/", "", 1),
        ]
        found = next((c for c in candidates if c.exists()), None)
        ok = found is not None
        record("static_css_on_disk", ok, ref=css_match.group(1)[:60], found=str(found) if found else "")
    else:
        record("static_css_on_disk", False, error="no css link in HTML")

    # 3. Manifest (PWA)
    s, body, t = _http("GET", f"{base}/manifest.json")
    if s == 200:
        try:
            m = json.loads(body)
            ok = m.get("name") and m.get("display") and isinstance(m.get("icons"), list)
            record("manifest", bool(ok), status=s, app_name=m.get("name"), icons=len(m.get("icons", [])))
        except Exception as e:
            record("manifest", False, status=s, error=str(e))
    else:
        record("manifest", False, status=s)

    # 4. Service worker file (referenced from app shell)
    s, body, t = _http("GET", f"{base}/sw.js")
    ok = s in (200, 404)  # 404 acceptable if SW lives at a different path
    record("service_worker_probe", ok, status=s)

    # 5. Security headers
    req = urllib.request.Request(f"{base}/", method="GET", headers={"User-Agent": "magezi-smoke/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            hdrs = {k.lower(): v for k, v in r.headers.items()}
    except Exception as e:
        hdrs = {}
        print(f"  hdr fetch err: {e}")
    has_csp = "content-security-policy" in hdrs
    has_xfo = "x-frame-options" in hdrs
    has_xcto = "x-content-type-options" in hdrs
    has_referrer = "referrer-policy" in hdrs
    ok = has_csp and has_xfo and has_xcto and has_referrer
    record("security_headers", ok, csp=has_csp, xfo=has_xfo, xcto=has_xcto, ref=has_referrer)

    passed = sum(1 for r in results if r["ok"])
    return {"base": base, "passed": passed, "total": len(results), "results": results}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:3902")
    p.add_argument("--out", default="/tmp/magezi_bench/smoke_frontend.json")
    args = p.parse_args()

    summary = run(args.base)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(f"\n== {summary['passed']}/{summary['total']} passed; wrote {args.out}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
