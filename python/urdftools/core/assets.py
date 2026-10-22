"""Local asset hashing; no network, code execution or basename guessing."""
import hashlib
from pathlib import Path
from uuid import uuid4

from .models import AssetRef


def asset_path(root, relative_path):
    # Reuse the contract's path validation before touching the filesystem.
    AssetRef.relative(relative_path)
    root = Path(root).resolve(strict=True)
    path = (root / relative_path).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('asset escapes project or is not a regular file')
    return path


def digest(path):
    sha = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            sha.update(block)
            size += len(block)
    return sha.hexdigest(), size


def register_asset(root, relative_path, *, mime, source_url=None, source_commit=None, license_id=None):
    sha, size = digest(asset_path(root, relative_path))
    return AssetRef(id=uuid4(), sha256=sha, size=size, relative_path=relative_path,
                    mime=mime, source_url=source_url, source_commit=source_commit, license_id=license_id)


def verify_asset(root, asset):
    asset = AssetRef.model_validate(asset)
    sha, size = digest(asset_path(root, asset.relative_path))
    if (sha, size) != (asset.sha256, asset.size):
        raise ValueError('asset hash/size mismatch')
    return asset
