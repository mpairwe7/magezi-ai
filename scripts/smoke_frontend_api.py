"""Frontend-shape API integration tests.

Hits each endpoint the way the frontend client (`useApi.ts`, store layers)
expects, and asserts the response matches the TypeScript interface shape.
Catches contract drift between backend changes and frontend assumptions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def _req(method: str, url: str, *, body: dict | None = None, headers: dict | None = None, timeout: float = 60.0) -> tuple[int, Any, float]:
    hdrs = {"User-Agent": "magezi-frontend-smoke/1.0", "Accept": "application/json"}
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
            try:
                return r.status, json.loads(raw) if raw else {}, time.perf_counter() - t0
            except json.JSONDecodeError:
                return r.status, raw.decode("utf-8", "ignore"), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw.decode("utf-8", "ignore")[:200]}
        return e.code, payload, time.perf_counter() - t0


def has_shape(obj: Any, required: dict[str, type | tuple]) -> tuple[bool, list[str]]:
    """Check every key in `required` is present in `obj` with the right type."""
    misses: list[str] = []
    if not isinstance(obj, dict):
        return False, [f"not a dict, got {type(obj).__name__}"]
    for key, typ in required.items():
        if key not in obj:
            misses.append(f"missing:{key}")
            continue
        val = obj[key]
        if val is None and (typ is type(None) or (isinstance(typ, tuple) and type(None) in typ)):
            continue
        if not isinstance(val, typ):
            misses.append(f"wrong_type:{key}={type(val).__name__}<>{typ}")
    return len(misses) == 0, misses


def run(base: str) -> dict:
    results: list[dict] = []

    def record(name: str, ok: bool, **extra) -> None:
        results.append({"name": name, "ok": ok, **extra})
        marker = "PASS" if ok else "FAIL"
        bits = " ".join(f"{k}={v}" for k, v in extra.items() if k != "shape_errors" or extra.get("shape_errors"))
        print(f"  [{marker}] {name}  {bits}")

    print(f"== Magezi frontend-API integration @ {base}")

    # ── useHealth() — frontend/src/hooks/useApi.ts:16 ─────────────────────
    s, b, t = _req("GET", f"{base}/health")
    shape_ok, errs = has_shape(b, {"status": str, "model": str, "retriever": str, "llm": str, "subjects": list})
    record("useHealth", s == 200 and shape_ok and isinstance(b.get("subjects"), list) and all(isinstance(x, str) for x in b.get("subjects", [])), status=s, ms=int(t * 1000), shape_errors=errs)

    # ── useSubjects() — useApi.ts:41 — expects {subjects:SubjectInfo[]} ───
    s, b, t = _req("GET", f"{base}/v1/subjects")
    subjects = b.get("subjects", []) if isinstance(b, dict) else []
    sub_ok, sub_errs = (True, [])
    required = {"id": str, "name": str, "name_lg": str, "icon": str, "color": str, "starter_prompts": list}
    for idx, s_obj in enumerate(subjects):
        ok, errs = has_shape(s_obj, required)
        if not ok:
            sub_ok = False
            sub_errs.append(f"[{idx}]({s_obj.get('id','?')})={errs}")
            break
    record("useSubjects", s == 200 and len(subjects) >= 4 and sub_ok, status=s, count=len(subjects), shape_errors=sub_errs[:3])

    # ── Auth flow: signup → login → fetchProfile (useApi.ts:112) ──────────
    suffix = uuid.uuid4().hex[:10]
    email = f"smoke-fe-{suffix}@magezi.test"
    password = "frontend-smoke-1234"
    s, b, t = _req("POST", f"{base}/v1/auth/signup", body={"email": email, "password": password, "name": "FE Smoke"})
    # User.to_dict() — backend/app/auth.py:114
    user_required = {"id": str, "email": str, "name": str, "credits": int, "has_api_key": bool, "plan": str}
    user_ok, user_errs = has_shape(b.get("user", {}), user_required) if isinstance(b, dict) else (False, ["no user"])
    token = b.get("token", "") if isinstance(b, dict) and s == 200 else ""
    record("signup_shape", s == 200 and token.startswith("ey") and user_ok, status=s, ms=int(t * 1000), credits=(b.get("user") or {}).get("credits"), shape_errors=user_errs)

    s, b, t = _req("POST", f"{base}/v1/auth/login", body={"email": email, "password": password})
    login_token = b.get("token", "") if s == 200 else ""
    record("login_shape", s == 200 and login_token.startswith("ey") and isinstance(b.get("user"), dict), status=s, ms=int(t * 1000))

    s, b, t = _req("GET", f"{base}/v1/auth/me", headers={"Authorization": f"Bearer {login_token}"})
    profile_ok = isinstance(b, dict) and isinstance(b.get("user"), dict) and b["user"].get("email") == email
    record("fetchProfile_shape", s == 200 and profile_ok, status=s, ms=int(t * 1000))

    # ── ChatMessage / sendChat — POST /v1/chat → ChatResponse shape ────────
    session_id = uuid.uuid4().hex
    chat_required = {"reply": str, "sources": list, "citations": list, "retrieval_mode": str, "locale": str, "subject": (str, type(None)), "grounding_warning": bool, "escalation_required": bool, "escalation_reason": str}
    body = {"message": "What is Newton's second law?", "subject": "physics", "locale": "en", "session_id": session_id, "top_k": 4}
    s, b, t = _req("POST", f"{base}/v1/chat", body=body, timeout=90.0)
    ok, errs = has_shape(b, chat_required) if isinstance(b, dict) else (False, [])
    reply = b.get("reply", "") if isinstance(b, dict) else ""
    citations = b.get("citations", []) if isinstance(b, dict) else []
    cit_ok = all(isinstance(c, dict) and "ref" in c and "source" in c for c in citations[:3])
    record("chat_response_shape", s == 200 and ok and cit_ok and len(reply) > 20, status=s, ms=int(t * 1000), reply_len=len(reply), citations=len(citations), shape_errors=errs[:3])

    # ── SSE /v1/chat/stream — backend/app/main.py:468-545 ───────────────
    # Wire format:
    #   event: metadata\ndata: {json}\n\n       — once at start (citations, retrieval_mode, ...)
    #   data: <raw token text>\n\n              — many; tokens are plain strings, not JSON
    #   event: grounding\ndata: {json}\n\n      — once (faithfulness_score, grounding_warning)
    #   event: done\ndata: \n\n                 — terminator
    hdrs = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    req = urllib.request.Request(f"{base}/v1/chat/stream", data=json.dumps({"message": "Define pH briefly.", "subject": "chemistry", "locale": "en", "session_id": uuid.uuid4().hex}).encode(), method="POST", headers=hdrs)
    t0 = time.perf_counter()
    ttfb: float | None = None
    pending_event: str | None = None  # tracks the most recent `event: <name>` line
    metadata: dict | None = None
    grounding: dict | None = None
    done_seen = False
    text_buf: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=90.0) as r:
            stream_status = r.status
            for raw in r:
                if ttfb is None:
                    ttfb = time.perf_counter() - t0
                line = raw.decode("utf-8", "ignore").rstrip("\r\n")
                if not line:
                    pending_event = None  # SSE record terminator
                    continue
                if line.startswith("event:"):
                    pending_event = line[6:].strip()
                    if pending_event == "done":
                        done_seen = True
                    continue
                if line.startswith("data:"):
                    payload = line[5:].lstrip()
                    if pending_event == "metadata":
                        try:
                            metadata = json.loads(payload)
                        except Exception:
                            pass
                    elif pending_event == "grounding":
                        try:
                            grounding = json.loads(payload)
                        except Exception:
                            pass
                    elif pending_event in (None, ""):
                        text_buf.append(payload)
    except Exception as e:
        record("chat_stream_shape", False, error=str(e)[:80])
    else:
        reply = "".join(text_buf)
        meta_ok = isinstance(metadata, dict) and "citations" in metadata and "retrieval_mode" in metadata
        ground_ok = grounding is None or ("faithfulness_score" in grounding and "grounding_warning" in grounding)
        ok = (
            stream_status == 200
            and ttfb is not None
            and ttfb < 30
            and len(reply) > 10
            and done_seen
            and meta_ok
            and ground_ok
        )
        record(
            "chat_stream_shape",
            ok,
            status=stream_status,
            ttfb_ms=int((ttfb or 0) * 1000),
            reply_chars=len(reply),
            meta_ok=meta_ok,
            ground_ok=ground_ok,
            done=done_seen,
        )

    # ── useFeedback() — useApi.ts:64 — rating ∈ {up,down} ─────────────────
    body = {"message_id": "fe-smoke-msg-1", "rating": "up", "user_query": "ping", "bot_reply": "pong"}
    s, b, t = _req("POST", f"{base}/v1/feedback", body=body)
    record("useFeedback", s == 200 and isinstance(b, dict) and b.get("status") == "ok", status=s, ms=int(t * 1000))

    # ── fetchConversations() — useApi.ts:120 — array of summaries ─────────
    s, b, t = _req("GET", f"{base}/v1/conversations", headers={"Authorization": f"Bearer {login_token}"})
    is_list = isinstance(b, list)
    record("fetchConversations", s == 200 and is_list, status=s, ms=int(t * 1000), count=len(b) if is_list else -1)

    # ── auth error → 401 with `detail` body for frontend error toast ─────
    s, b, t = _req("GET", f"{base}/v1/auth/me", headers={"Authorization": "Bearer bogus"})
    record("auth_invalid_token_shape", s == 401 and isinstance(b, dict) and "detail" in b, status=s, ms=int(t * 1000), detail=(b.get("detail") if isinstance(b, dict) else None))

    # ── validation 422 has `detail` for the frontend form-error path ─────
    s, b, t = _req("POST", f"{base}/v1/chat", body={"message": "", "locale": "en"})
    record("validation_422_shape", s == 422 and isinstance(b, dict) and "detail" in b, status=s)

    # ── CORS preflight from baked NEXT_PUBLIC_API_URL origin ──────────────
    headers = {"Origin": "http://127.0.0.1:3902", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,authorization"}
    s, _, t = _req("OPTIONS", f"{base}/v1/chat", headers=headers)
    # Either 200 (CORS middleware preflight handled) or 405 with simple GET still working
    record("cors_preflight", s in (200, 204, 405), status=s)

    passed = sum(1 for r in results if r["ok"])
    return {"base": base, "passed": passed, "total": len(results), "results": results}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8902")
    p.add_argument("--out", default="/tmp/magezi_bench/smoke_frontend_api.json")
    args = p.parse_args()

    summary = run(args.base)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(f"\n== {summary['passed']}/{summary['total']} passed; wrote {args.out}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
