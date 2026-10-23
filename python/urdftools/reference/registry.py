"""Local immutable content-addressed URDF reference catalog, no training results."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid
import xml.etree.ElementTree as ET


MAX_URDF_BYTES = 4 * 1024 * 1024
CATEGORIES = {"quadruped", "humanoid", "manipulator", "wheeled", "other"}
ORIGINS = {"public_import", "user_upload", "synthetic_fixture"}


class RegistryError(ValueError):
    pass


class AssetFetchError(RegistryError):
    pass


class ModelRegistry:
    def __init__(self, store: str | Path):
        self.store = Path(store).resolve()
        self.store.mkdir(parents=True, exist_ok=True)
        self.blobs = self.store / "blobs"
        self.blobs.mkdir(exist_ok=True)
        self.db = self.store / "models.sqlite3"
        self.connection = sqlite3.connect(str(self.db), timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=10000")
        self.connection.executescript("""
          CREATE TABLE IF NOT EXISTS models(
             id TEXT PRIMARY KEY,
             name TEXT NOT NULL,
             version TEXT NOT NULL,
             category TEXT NOT NULL,
             origin TEXT NOT NULL,
             source_uri TEXT,
             license TEXT,
             sha256 TEXT NOT NULL,
             license_notice_sha256 TEXT,
             license_reviewed_by TEXT,
             registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
             UNIQUE(name, version)
          );
          CREATE TABLE IF NOT EXISTS events(
             id INTEGER PRIMARY KEY,
             model_id TEXT NOT NULL REFERENCES models(id),
             type TEXT NOT NULL,
             details_json TEXT NOT NULL,
             created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
          );
        """)
        self.connection.commit()

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @staticmethod
    def _assert_urdf(blob: bytes):
        if not blob or len(blob) > MAX_URDF_BYTES:
            raise RegistryError("URDF asset empty or above 4 MiB limit")
        try:
            root = ET.fromstring(blob)
        except ET.ParseError as exc:
            raise RegistryError(f"Invalid URDF XML: {exc}") from exc
        if root.tag != "robot" or not root.get("name") or not root.findall("link"):
            raise RegistryError("URDF requires robot name and at least one link")

    def _blob_path(self, sha: str):
        return self.blobs / sha[:2] / sha

    def _store_blob(self, blob: bytes) -> str:
        sha = hashlib.sha256(blob).hexdigest()
        dest = self._blob_path(sha)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if hashlib.sha256(dest.read_bytes()).hexdigest() != sha:
                raise RegistryError("Existing asset hash mismatch; cannot overwrite")
            return sha
        tmp = dest.with_name(f".{sha}.{uuid.uuid4().hex}.tmp")
        try:
            with tmp.open("xb") as output:
                output.write(blob)
                output.flush()
                os.fsync(output.fileno())
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        return sha

    def import_bytes(self, blob: bytes, *, name: str, version: str, category: str,
                     origin: str, source_uri: str | None = None, license_id: str | None = None,
                     expected_sha256: str | None = None) -> dict:
        if not name.strip() or not version.strip() or any(len(x) > 160 for x in (name, version)):
            raise RegistryError("Name/version required and limited to 160 characters")
        if category not in CATEGORIES or origin not in ORIGINS:
            raise RegistryError("Unknown model category or provenance origin")
        if license_id is not None and not license_id.strip():
            raise RegistryError("Empty license identifier")
        self._assert_urdf(blob)
        sha = hashlib.sha256(blob).hexdigest()
        if expected_sha256 is not None and sha != expected_sha256.lower():
            raise RegistryError("Asset SHA-256 mismatch; no model registered")
        existing = self.connection.execute(
            "SELECT id,sha256 FROM models WHERE name=? AND version=?", (name, version)
        ).fetchone()
        if existing is not None and existing["sha256"] != sha:
            raise RegistryError("Existing name/version points to different bytes; use new version")
        self._store_blob(blob)
        model_id = hashlib.sha256(f"{name}\0{version}\0{sha}".encode()).hexdigest()[:32]
        with self.connection:
            self.connection.execute("""
                INSERT OR IGNORE INTO models
                  (id,name,version,category,origin,source_uri,license,sha256)
                VALUES(?,?,?,?,?,?,?,?)
            """, (model_id, name, version, category, origin, source_uri, license_id, sha))
            if existing is None:
                self.connection.execute(
                    "INSERT INTO events(model_id,type,details_json) VALUES(?,?,?)",
                    (model_id, "registered", json.dumps({"sha256": sha, "origin": origin}))
                )
        return self.get(model_id)

    def import_file(self, file: str | Path, **attributes) -> dict:
        file = Path(file).resolve(strict=True)
        if not file.is_file() or file.stat().st_size > MAX_URDF_BYTES:
            raise RegistryError("Input is not a bounded regular URDF file")
        return self.import_bytes(file.read_bytes(), **attributes)

    def fetch_https(self, url: str, **attributes) -> dict:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise AssetFetchError("Only credential-free HTTPS model URLs accepted")
        try:
            with urlopen(Request(url, headers={"User-Agent": "URDFTools-registry/1.0"}),
                         timeout=8) as response:
                blob = response.read(MAX_URDF_BYTES + 1)
        except (OSError, ValueError) as exc:
            raise AssetFetchError(f"HTTPS download failed; no registry entry added: {type(exc).__name__}") from exc
        return self.import_bytes(blob, source_uri=url, **attributes)

    def get(self, model_id: str) -> dict:
        row = self.connection.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()
        if row is None:
            raise RegistryError("Unknown model id")
        info = dict(row)
        info["reference_performance"] = False
        info["bundling_permitted"] = self.can_bundle(info)
        return info

    @staticmethod
    def can_bundle(record: dict) -> bool:
        return bool(record["origin"] == "public_import"
                    and record["license"]
                    and record["license_notice_sha256"]
                    and record["license_reviewed_by"])

    def list_models(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT id FROM models ORDER BY name,version,registered_at,id").fetchall()
        return [self.get(row["id"]) for row in rows]

    def read_asset(self, model_id: str) -> bytes:
        model = self.get(model_id)
        data = self._blob_path(model["sha256"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != model["sha256"]:
            raise RegistryError("Cached model was tampered with")
        return data

    def approve_public_license(self, model_id: str, notice: bytes, reviewer: str) -> dict:
        model = self.get(model_id)
        if model["origin"] != "public_import" or not model["license"]:
            raise RegistryError("Cannot approve bundling of private/fixture/unlicensed asset")
        if not notice.strip() or not reviewer.strip():
            raise RegistryError("License notice and explicit reviewer required")
        notice_sha = self._store_blob(notice)
        with self.connection:
            self.connection.execute(
                "UPDATE models SET license_notice_sha256=?,license_reviewed_by=? WHERE id=?",
                (notice_sha, reviewer, model_id))
            self.connection.execute(
                "INSERT INTO events(model_id,type,details_json) VALUES(?,?,?)",
                (model_id, "license_reviewed",
                 json.dumps({"notice_sha256": notice_sha, "reviewer": reviewer})))
        return self.get(model_id)
