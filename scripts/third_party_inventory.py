#!/usr/bin/env python3
"""Record public package metadata and preserve shipped license texts offline."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "third_party"
    output.mkdir(exist_ok=True)
    notices = output / "notices"
    notices.mkdir(exist_ok=True)
    entries = []

    def preserve(name, files):
        target = notices / name
        target.mkdir(exist_ok=True)
        refs = []
        for filename, data in files:
            dest = target / filename
            dest.write_bytes(data)
            refs.append({"path": str(dest.relative_to(ROOT)), "sha256": hashlib.sha256(data).hexdigest()})
        return refs

    wheels = json.loads((ROOT / "artifacts/S01/cached-wheels.json").read_text())
    for name, data in sorted(wheels.items()):
        path = ROOT / ".tools/wheelhouse" / data["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != data["sha256"]:
            raise ValueError("Wheel hash mismatch: " + name)
        with zipfile.ZipFile(path) as z:
            texts = [(n.replace("/", "__"), z.read(n)) for n in z.namelist()
                     if ".dist-info/" in n and any(s in n.lower().split("/")[-1] for s in ("license", "copying", "notice"))]
        # Older wheel metadata uses classifiers instead of License-Expression.
        license_id = data["license"] or {"fastapi": "MIT", "idna": "BSD-3-Clause", "setuptools": "MIT", "wheel": "MIT"}.get(name)
        entries.append({"ecosystem": "pypi", "name": name.replace("_", "-"), "version": data["version"],
            "source": f"https://pypi.org/project/{name.replace('_', '-')}/{data['version']}/",
            "upstream": data["home"], "commit": None, "artifact_sha256": data["sha256"],
            "license": license_id, "notices": preserve("pypi-" + name, texts),
            "changes": "Unmodified wheel from local pip HTTP cache; no third-party source vendored"})

    lock = json.loads((ROOT / "package-lock.json").read_text())
    catalog = {e["resolved"]: e["manifest"] for e in json.loads((ROOT / "artifacts/S01/npm-cache-catalog.json").read_text())}
    def npm_entry(name, path, pinned=None):
        m = json.loads((path / "package.json").read_text())
        texts = [(p.name, p.read_bytes()) for p in path.iterdir() if p.is_file() and p.name.lower().startswith(("license", "copying", "notice"))]
        return {"ecosystem": "npm", "usage": "application" if pinned else "development-tool", "name": m["name"], "version": m["version"],
            "source": (pinned or {}).get("resolved", f"https://registry.npmjs.org/{m['name']}/-/{m['name'].split('/')[-1]}-{m['version']}.tgz"),
            "upstream": m.get("repository"), "commit": m.get("gitHead"),
            "integrity": (pinned or {}).get("integrity"), "license": m.get("license") or m.get("licenses"),
            "notices": preserve("npm-" + name.replace("/", "__"), texts),
            "changes": "Unmodified public npm package; install scripts disabled for web dependencies"}
    for key, pinned in lock["packages"].items():
        if not key:
            continue
        entry = npm_entry(key.removeprefix("node_modules/"), ROOT / key, pinned)
        entry["commit"] = catalog[pinned["resolved"]].get("gitHead")
        entries.append(entry)
    desktop = ROOT / "apps/desktop"
    desktop_lock = json.loads((desktop / "package-lock.json").read_text())
    for key, pinned in desktop_lock["packages"].items():
        if not key:
            continue
        entry = npm_entry("desktop-" + key.removeprefix("node_modules/"), desktop / key, pinned)
        entry["usage"] = "desktop-application"
        entries.append(entry)
    runtime_pin = json.loads((desktop / "runtime-lock.json").read_text())
    runtime = desktop / "node_modules/electron/dist"
    archive = ROOT / ".tools/electron-cache" / runtime_pin["archive"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != runtime_pin["sha256"]:
        raise ValueError("Electron archive differs from reviewed pin")
    with zipfile.ZipFile(archive) as bundle:
        runtime_hashes = {m.filename: hashlib.sha256(bundle.read(m)).hexdigest()
                          for m in bundle.infolist() if not m.is_dir()}
    for name, expected in runtime_hashes.items():
        if hashlib.sha256((runtime / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Installed runtime differs from reviewed archive: " + name)
    entries.append({"ecosystem": "runtime", "name": "electron", "version": runtime_pin["version"],
        "source": runtime_pin["source"], "download_mirror": runtime_pin["download_mirror"],
        "metadata_source": runtime_pin["metadata_source"], "commit": None,
        "artifact_sha256": runtime_pin["sha256"], "license": "MIT AND Chromium third-party licenses",
        "notices": preserve("electron-runtime", [(name, (runtime / name).read_bytes())
                    for name in ("LICENSE", "LICENSES.chromium.html")]),
        "changes": "Unmodified archive files; executable permissions retained without setuid/setgid"})
    (output / "electron-runtime-files.json").write_text(json.dumps(runtime_hashes, indent=2, sort_keys=True) + "\n")
    # npm tool bundles its own dependency tree; record it separately from app dependencies.
    npm = ROOT / ".tools/npm"
    entries.append(npm_entry("npm-tool", npm))
    for p in sorted((npm / "node_modules").glob("**/package.json")):
        if "/node_modules/" not in str(p) or not p.is_file():
            continue
        try:
            m = json.loads(p.read_text())
            if m.get("name") and m.get("version"):
                entries.append(npm_entry("npm-tool-" + str(p.parent.relative_to(npm / "node_modules")), p.parent))
        except (ValueError, KeyError):
            continue
    pins = json.loads((ROOT / "toolchain.json").read_text())
    for name, source, license_id in [
        ("python", "https://github.com/python/cpython/tree/v3.12.14", "PSF-2.0"),
        ("node", "https://github.com/nodejs/node/tree/v24.19.0", "MIT AND third-party licenses")]:
        texts = []
        if name == "python":
            texts = [("LICENSE.txt", (ROOT / ".tools/python/lib/python3.12/LICENSE.txt").read_bytes())]
        elif name == "node":
            texts = [("LICENSE", (notices / "node/LICENSE").read_bytes())]
        entries.append({"ecosystem": "runtime", "name": name, "version": pins[name], "source": source,
            "commit": None, "license": license_id, "artifact_sha256": pins["binary_sha256"][name],
            "notices": preserve(name, texts), "changes": "Copied explicit local runtime seed; ambient site-packages, node_modules and absolute/dangling symlinks excluded",
            "verification": "Binary hash pinned; upstream binary release/build provenance not established"})
    manifest = {"schema_version": 1, "scope": "S01 development skeleton; not a redistribution clearance",
        "entries": entries,
        "pending": [],
        "limitations": ["npm tool bundled packages may inherit license from parent; missing notices require redistribution review", "Python/Node runtime binaries are development seeds, not reproducible upstream builds", "Python build tools contain vendored components requiring expanded redistribution review in Q01"]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Recorded {len(entries)} third-party components")


if __name__ == "__main__":
    main()
