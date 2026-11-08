"""Check key authentication and a minimal Gemini reply without printing secrets."""

import os
import queue
import threading
import time

import httpx
from dotenv import dotenv_values, load_dotenv

from jeel_portfolio.database import ROOT


def bounded(label, method, url, key, **kwargs):
    result = queue.Queue(maxsize=1)

    def invoke():
        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                response = client.request(method, url, headers={"x-goog-api-key": key}, **kwargs)
            result.put((response.status_code, response.json()))
        except Exception as exc:
            result.put((None, type(exc).__name__))

    started = time.monotonic()
    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    worker.join(20)
    if worker.is_alive():
        print(f"{label}: network timeout after 20 seconds (key validity untested)")
        return None, None
    code, payload = result.get_nowait()
    print(f"{label}: HTTP {code or payload} in {time.monotonic()-started:.1f} seconds")
    return code, payload


def main():
    file_key = (dotenv_values(ROOT / ".env").get("GEMINI_API_KEY") or "").strip()
    ambient_key = os.getenv("GEMINI_API_KEY", "").strip()
    load_dotenv(ROOT / ".env", override=False)
    key = os.getenv("GEMINI_API_KEY", "").strip()
    print("Effective key present:", bool(key))
    print("An ambient key overrides .env:", bool(ambient_key and file_key and ambient_key != file_key))
    if not key:
        return 2
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
    code, _ = bounded("Model access", "GET", endpoint, key)
    if code != 200:
        print("A non-200 result or timeout prevents a valid generation test.")
        return 1
    code, payload = bounded("Minimal generation", "POST", endpoint + ":generateContent", key,
                            json={"contents":[{"parts":[{"text":"Reply OK."}]}],
                                  "generationConfig":{"maxOutputTokens":32,"thinkingConfig":{"thinkingLevel":"minimal"}}})
    if code == 200:
        print("Gemini returned a candidate:", bool(payload.get("candidates")))
        return 0 if payload.get("candidates") else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
