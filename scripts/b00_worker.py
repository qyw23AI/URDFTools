#!/usr/bin/env python3
"""Process one queued external-result import; intended for disposable workers."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from urdftools.results.jobs import ImportFailure, ImportQueue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("store")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--chunk-size", type=int, default=1024 * 1024)
    parser.add_argument("--pause-seconds", type=float, default=0)
    args = parser.parse_args()
    with ImportQueue(args.store) as queue:
        job = queue.claim(args.owner)
        if job is None:
            print(json.dumps({"status": "empty"}))
            return 0
        try:
            while queue.step(job, args.owner, args.chunk_size) != "completed":
                if args.pause_seconds:
                    time.sleep(args.pause_seconds)
        except ImportFailure as exc:
            queue.db.execute("UPDATE jobs SET status='failed',error=?,owner=NULL,lease_until=NULL WHERE id=? AND owner=?", (str(exc), job, args.owner))
            print(json.dumps({"status": "failed", "job": job, "error": str(exc)}))
            return 1
        print(json.dumps({"status": "completed", "job": job}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
