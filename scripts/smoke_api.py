"""End-to-end smoke tests for the Magezi backend (CPU deployment).

Hits each public endpoint and asserts on shape, status, and content sanity.
Usage:
    python3 scripts/smoke_api.py [--base http://127.0.0.1:8902]

Exits 0 on full pass, 1 otherwise. Writes JSON results to /tmp/magezi_bench/smoke.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def _http(method: str, url: str, *, body: dict | None = None, headers: dict | None = None, timeout: float = 60.0) -> tuple[int, dict, float]:
    hdrs = {"User-Agent": "magezi-smoke/1.0"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw.decode("utf-8", "ignore")}
        return e.code, payload, time.perf_counter() - t0


def _http_stream(url: str, body: dict, headers: dict | None = None, timeout: float = 120.0) -> tuple[int, list[str], float, float]:
    """POST and consume SSE; returns (status, events, ttfb_s, total_s)."""
    hdrs = {"Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": "magezi-smoke/1.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=hdrs)
    t0 = time.perf_counter()
    first_byte = None
    events: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.status
            for line in r:
                if first_byte is None:
                    first_byte = time.perf_counter() - t0
                events.append(line.decode("utf-8", "ignore").rstrip())
    except urllib.error.HTTPError as e:
        return e.code, [e.read().decode("utf-8", "ignore")], 0.0, time.perf_counter() - t0
    return status, events, first_byte or 0.0, time.perf_counter() - t0


def run(base: str) -> dict:
    results: list[dict] = []

    def record(name: str, ok: bool, **extra) -> bool:
        results.append({"name": name, "ok": ok, **extra})
        marker = "PASS" if ok else "FAIL"
        extras = " ".join(f"{k}={v}" for k, v in extra.items() if k not in ("body",))
        print(f"  [{marker}] {name}  {extras}")
        return ok

    print(f"== Magezi smoke @ {base}")

    # 1. /health
    s, b, t = _http("GET", f"{base}/health")
    ok = s == 200 and b.get("status") == "ok" and "subjects" in b and len(b["subjects"]) == 4
    record("health", ok, status=s, latency_ms=int(t * 1000), llm=b.get("llm"), retriever=b.get("retriever"))

    # 2. /v1/subjects
    s, b, t = _http("GET", f"{base}/v1/subjects")
    ok = s == 200 and isinstance(b, dict) and len(b.get("subjects", [])) >= 4
    record("subjects", ok, status=s, latency_ms=int(t * 1000), count=len(b.get("subjects", [])) if isinstance(b, dict) else 0)

    # 3. Auth — signup
    suffix = uuid.uuid4().hex[:10]
    email = f"smoke-{suffix}@magezi.test"
    password = "smoke-pass-1234"
    s, b, t = _http("POST", f"{base}/v1/auth/signup", body={"email": email, "password": password, "name": "Smoke"})
    token = b.get("token", "") if s == 200 else ""
    ok = s == 200 and token.startswith("ey") and b.get("user", {}).get("email") == email
    record("auth.signup", ok, status=s, latency_ms=int(t * 1000), token_len=len(token))

    # 4. Auth — login (same creds)
    s, b, t = _http("POST", f"{base}/v1/auth/login", body={"email": email, "password": password})
    login_token = b.get("token", "") if s == 200 else ""
    ok = s == 200 and login_token.startswith("ey")
    record("auth.login", ok, status=s, latency_ms=int(t * 1000))

    # 5. Auth — me
    s, b, t = _http("GET", f"{base}/v1/auth/me", headers={"Authorization": f"Bearer {login_token}"})
    ok = s == 200 and b.get("user", {}).get("email") == email
    record("auth.me", ok, status=s, latency_ms=int(t * 1000), email_match=b.get("user", {}).get("email") == email)

    # 6. Auth — me without token → 401
    s, b, t = _http("GET", f"{base}/v1/auth/me")
    ok = s == 401
    record("auth.me_unauth", ok, status=s, latency_ms=int(t * 1000))

    # 7. /v1/chat — sync, real LLM call (Groq)
    session_id = uuid.uuid4().hex
    body = {"message": "State Newton's second law in one sentence.", "subject": "physics", "locale": "en", "session_id": session_id, "top_k": 4}
    s, b, t = _http("POST", f"{base}/v1/chat", body=body, timeout=90.0)
    reply = b.get("reply", "") if s == 200 else ""
    retr = b.get("retrieval_mode", "")
    ok = (
        s == 200
        and isinstance(reply, str)
        and len(reply.strip()) >= 10
        and ("newton" in reply.lower() or "force" in reply.lower() or "acceleration" in reply.lower())
    )
    record("chat.sync_physics", ok, status=s, latency_ms=int(t * 1000), reply_len=len(reply), retrieval=retr, citations=len(b.get("citations", [])) if isinstance(b, dict) else 0)

    # 8. /v1/chat/stream — SSE TTFB + completion
    body = {"message": "Define molarity briefly.", "subject": "chemistry", "locale": "en", "session_id": uuid.uuid4().hex, "top_k": 4}
    s, evs, ttfb, total = _http_stream(f"{base}/v1/chat/stream", body, timeout=90.0)
    data_lines = [e for e in evs if e.startswith("data:")]
    has_done = any('"done"' in e or "done" in e for e in evs[-10:])
    ok = s == 200 and len(data_lines) >= 1 and ttfb < 30.0
    record("chat.stream_chemistry", ok, status=s, ttfb_ms=int(ttfb * 1000), total_ms=int(total * 1000), data_chunks=len(data_lines), has_done=has_done)

    # 9. Multi-turn — keyword-anchored follow-up so the keyword retriever finds passages
    #    and we don't trip the abstention guard.
    body = {"message": "If F=ma, what is the force on a 2 kg mass accelerating at 3 m/s^2?", "subject": "physics", "locale": "en", "session_id": session_id, "top_k": 4, "history": [{"role": "user", "content": "State Newton's second law."}, {"role": "assistant", "content": "F = ma."}]}
    s, b, t = _http("POST", f"{base}/v1/chat", body=body, timeout=90.0)
    reply = b.get("reply", "") if s == 200 else ""
    retr = b.get("retrieval_mode", "")
    ok = s == 200 and len(reply.strip()) >= 10 and retr != "abstained"
    record("chat.multi_turn", ok, status=s, latency_ms=int(t * 1000), reply_len=len(reply), retrieval=retr)

    # 10. Validation — empty message rejected
    s, b, t = _http("POST", f"{base}/v1/chat", body={"message": "", "locale": "en"})
    ok = s in (400, 422)
    record("chat.empty_rejected", ok, status=s)

    # 11. Validation — invalid locale rejected
    s, b, t = _http("POST", f"{base}/v1/chat", body={"message": "Hi", "locale": "fr"})
    ok = s in (400, 422)
    record("chat.invalid_locale_rejected", ok, status=s)

    # 12. Feedback — rating is "up" | "down" per FeedbackRequest (main.py:620)
    s, b, t = _http("POST", f"{base}/v1/feedback", body={"message_id": "smoke-123", "rating": "up", "user_query": "Hi", "bot_reply": "Hello"})
    ok = s == 200 and b.get("status") == "ok"
    record("feedback", ok, status=s, latency_ms=int(t * 1000))

    # 13. Session clear
    s, b, t = _http("POST", f"{base}/v1/session/clear", body={"session_id": session_id})
    ok = s == 200
    record("session.clear", ok, status=s, latency_ms=int(t * 1000))

    # 14. Speech health (Sunbird upstream may be down — accept any 2xx/4xx other than 500)
    s, b, t = _http("GET", f"{base}/v1/speech/health")
    ok = s < 500
    record("speech.health", ok, status=s, latency_ms=int(t * 1000))

    passed = sum(1 for r in results if r["ok"])
    return {"base": base, "passed": passed, "total": len(results), "results": results}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8902")
    p.add_argument("--out", default="/tmp/magezi_bench/smoke.json")
    args = p.parse_args()

    summary = run(args.base)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(f"\n== {summary['passed']}/{summary['total']} passed; wrote {args.out}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
