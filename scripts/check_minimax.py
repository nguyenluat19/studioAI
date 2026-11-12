#!/usr/bin/env python3
"""Check your MiniMax-H3 key and endpoints against the live API (one short paid clip: 4s, 768P).

    python scripts/check_minimax.py --dry-run     # print the request, call nothing
    python scripts/check_minimax.py               # create, poll, print every raw response

If the query step reports a 404, copy the path from MiniMax's docs into MINIMAX_QUERY_PATH in .env.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx  # noqa: E402

from app import minimax  # noqa: E402
from app.config import settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prompt", default="A person waving at the camera, plain background, static camera")
    args = ap.parse_args()
    payload = minimax.build_payload(args.prompt, 4, "9:16", "768P")
    print(f"POST {settings.minimax_base_url}{settings.minimax_create_path}\n{json.dumps(payload, indent=1)}\n")
    if args.dry_run:
        return 0
    if not minimax.configured():
        print("MINIMAX_API_KEY is empty in .env")
        return 1
    print("This creates one real 4-second clip and will be billed by MiniMax.")
    with httpx.Client(timeout=60) as c:
        tid = minimax.create_task(c, payload)
        print("task_id:", tid)
        end = time.time() + 600
        while time.time() < end:
            state, url, raw = minimax.query_task(c, tid)
            print(f"[{state}] {json.dumps(raw)[:300]}")
            if state != "pending":
                print("\nvideo url:", url)
                print("query path that worked:", minimax._query_template)
                return 0 if state == "ok" else 2
            time.sleep(settings.minimax_poll)
    print("timed out")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
