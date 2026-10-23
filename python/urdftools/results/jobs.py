"""SQLite leased, resumable import of externally produced files."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import time
import uuid


class ImportFailure(ValueError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class ImportQueue:
    def __init__(self, location: str | Path):
        self.root = Path(location).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.partial = self.root / "partial"
        self.blobs = self.root / "blobs"
        self.partial.mkdir(exist_ok=True)
        self.blobs.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / "results.sqlite3", timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,bundle_id TEXT UNIQUE NOT NULL,
          source TEXT NOT NULL,manifest TEXT NOT NULL,manifest_sha TEXT NOT NULL,
          status TEXT NOT NULL,next_file INTEGER NOT NULL DEFAULT 0,offset INTEGER NOT NULL DEFAULT 0,
          owner TEXT,lease_until REAL,error TEXT);
        CREATE TABLE IF NOT EXISTS assets(sha TEXT PRIMARY KEY,size INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS job_assets(job_id TEXT NOT NULL,path TEXT NOT NULL,sha TEXT NOT NULL,
          PRIMARY KEY(job_id,path));
        CREATE TABLE IF NOT EXISTS runs(bundle_id TEXT PRIMARY KEY,job_id TEXT UNIQUE NOT NULL,
          robot_hash TEXT NOT NULL,manifest_sha TEXT NOT NULL,imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def enqueue(self, source: str | Path, manifest: dict) -> str:
        source = Path(source).resolve(strict=True)
        if not source.is_dir() or not isinstance(manifest, dict):
            raise ImportFailure("Local directory and manifest required")
        bundle_id, robot_hash, files = (manifest.get(k) for k in ("bundle_id", "robot_hash", "files"))
        if not isinstance(bundle_id, str) or not bundle_id or len(bundle_id) > 160:
            raise ImportFailure("Invalid bundle ID")
        if not isinstance(robot_hash, str) or len(robot_hash) != 64 or any(c not in "0123456789abcdef" for c in robot_hash):
            raise ImportFailure("Invalid robot SHA-256")
        if not isinstance(files, list) or not 0 < len(files) <= 10000:
            raise ImportFailure("Invalid file inventory")
        seen, total = set(), 0
        for item in files:
            if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
                raise ImportFailure("File requires path, size, sha256")
            name, size, sha = item["path"], item["size"], item["sha256"]
            if not isinstance(name, str) or not name or "\\" in name or "\0" in name or PurePosixPath(name).is_absolute() or any(p in {"", ".", ".."} for p in name.split("/")) or name in seen:
                raise ImportFailure("Unsafe or duplicate path")
            seen.add(name)
            if type(size) is not int or not 0 <= size <= 8 * 1024**3:
                raise ImportFailure("Invalid file size")
            total += size
            if total > 32 * 1024**3:
                raise ImportFailure("Bundle exceeds 32 GiB")
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                raise ImportFailure("Invalid SHA-256")
            path = source / name
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source):
                raise ImportFailure("Missing, linked or escaped input")
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)
        manifest_sha = hashlib.sha256(encoded.encode()).hexdigest()
        prior = self.db.execute("SELECT id,source,manifest_sha FROM jobs WHERE bundle_id=?", (bundle_id,)).fetchone()
        if prior:
            if prior["source"] != str(source) or prior["manifest_sha"] != manifest_sha:
                raise ImportFailure("Bundle ID already bound to different source or robot")
            return prior["id"]
        job_id = uuid.uuid4().hex
        self.db.execute("INSERT INTO jobs(id,bundle_id,source,manifest,manifest_sha,status) VALUES(?,?,?,?,?,'queued')",
                        (job_id, bundle_id, str(source), encoded, manifest_sha))
        return job_id

    def status(self, job_id: str) -> dict:
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def claim(self, owner: str, lease_seconds: float = 30) -> str | None:
        if not owner or lease_seconds <= 0:
            raise ValueError("Valid owner and lease required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT id FROM jobs WHERE status='queued' OR (status='running' AND lease_until<?) ORDER BY rowid LIMIT 1", (time.time(),)).fetchone()
            if row:
                self.db.execute("UPDATE jobs SET status='running',owner=?,lease_until=? WHERE id=?", (owner, time.time()+lease_seconds, row["id"]))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return row["id"] if row else None

    def cancel(self, job_id: str):
        self.db.execute("UPDATE jobs SET status='cancelled',owner=NULL,lease_until=NULL WHERE id=? AND status IN ('queued','running')", (job_id,))

    def step(self, job_id: str, owner: str, chunk_size: int = 1024 * 1024) -> str:
        if not 0 < chunk_size <= 16 * 1024 * 1024:
            raise ValueError("Invalid chunk size")
        job = self.status(job_id)
        if job["status"] != "running" or job["owner"] != owner or job["lease_until"] <= time.time():
            raise ImportFailure("Live lease required")
        manifest = json.loads(job["manifest"])
        index = job["next_file"]
        if index == len(manifest["files"]):
            self.db.execute("BEGIN IMMEDIATE")
            try:
                current = self.status(job_id)
                if current["owner"] != owner or current["status"] != "running":
                    raise ImportFailure("Lease changed")
                self.db.execute("INSERT INTO runs(bundle_id,job_id,robot_hash,manifest_sha) VALUES(?,?,?,?)",
                                (job["bundle_id"], job_id, manifest["robot_hash"], job["manifest_sha"]))
                self.db.execute("UPDATE jobs SET status='completed',owner=NULL,lease_until=NULL WHERE id=?", (job_id,))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            return "completed"
        item = manifest["files"][index]
        source = Path(job["source"]) / item["path"]
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(Path(job["source"])):
            raise ImportFailure("Source changed or escaped bundle")
        part = self.partial / f"{job_id}-{index}.part"
        offset = job["offset"]
        with part.open("ab+") as output:
            output.seek(0, os.SEEK_END)
            if output.tell() < offset:
                raise ImportFailure("Partial file shorter than checkpoint")
            output.truncate(offset)
            output.seek(offset)
            with source.open("rb") as data:
                data.seek(offset)
                block = data.read(min(chunk_size, item["size"]-offset))
                if len(block) != min(chunk_size, item["size"]-offset):
                    raise ImportFailure("Source truncated")
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        offset += len(block)
        if offset < item["size"]:
            changed = self.db.execute("UPDATE jobs SET offset=?,lease_until=? WHERE id=? AND owner=? AND status='running' AND lease_until>? AND offset=?",
                                      (offset, time.time()+30, job_id, owner, time.time(), job["offset"]))
            if changed.rowcount != 1:
                raise ImportFailure("Lease changed during chunk")
            return "running"
        if digest(part) != item["sha256"] or source.stat().st_size != item["size"] or digest(source) != item["sha256"]:
            raise ImportFailure("Source hash or size mismatch")
        target = self.blobs / item["sha256"][:2] / item["sha256"]
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            if target.stat().st_size != item["size"] or digest(target) != item["sha256"]:
                raise ImportFailure("Existing blob hash mismatch")
            part.unlink()
        else:
            os.replace(part, target)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current = self.status(job_id)
            if current["status"] != "running" or current["owner"] != owner or current["lease_until"] <= time.time() or current["next_file"] != index:
                raise ImportFailure("Lease changed during file")
            self.db.execute("INSERT OR IGNORE INTO assets(sha,size) VALUES(?,?)", (item["sha256"], item["size"]))
            self.db.execute("INSERT INTO job_assets(job_id,path,sha) VALUES(?,?,?)", (job_id, item["path"], item["sha256"]))
            self.db.execute("UPDATE jobs SET next_file=?,offset=0,lease_until=? WHERE id=?", (index+1, time.time()+30, job_id))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return "running"
