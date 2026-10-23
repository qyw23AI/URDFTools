"""R00 actual sqlite WAL and immutable content-cache transaction contract."""
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"python"))
from urdftools.reference.registry import ModelRegistry,RegistryError,AssetFetchError

FILES=ROOT/"tests/fixtures/E00"
ATTR=dict(name="quad",category="quadruped",origin="public_import",
          license_id="CC0-1.0")


class RegistryTests(unittest.TestCase):
    def test_versions_are_never_overwritten_restart_persists(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            a=FILES/"quadruped_valid.urdf"
            b=FILES/"quadruped_axis_context_mismatch.urdf"
            with ModelRegistry(path) as r:
                first=r.import_file(a,version="1",**ATTR)
                second=r.import_file(b,version="2",**ATTR)
                self.assertNotEqual(first["id"],second["id"])
                self.assertNotEqual(first["sha256"],second["sha256"])
                self.assertEqual(first["id"],r.import_file(a,version="1",**ATTR)["id"])
                self.assertEqual(len(r.list_models()),2)
                self.assertEqual(r.read_asset(first["id"]),a.read_bytes())
                with self.assertRaisesRegex(RegistryError,"different bytes"):
                    r.import_file(b,version="1",**ATTR)
            with ModelRegistry(path) as reopened:
                self.assertEqual(len(reopened.list_models()),2)
                self.assertEqual(reopened.get(first["id"])["sha256"],
                                 hashlib.sha256(a.read_bytes()).hexdigest())
                self.assertEqual(reopened.read_asset(second["id"]),b.read_bytes())

    def test_hash_and_invalid_input_dont_impact_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            with ModelRegistry(temporary) as registry:
                with self.assertRaisesRegex(RegistryError,"SHA-256"):
                    registry.import_file(FILES/"quadruped_valid.urdf",
                                         version="1",expected_sha256="0"*64,**ATTR)
                with self.assertRaisesRegex(RegistryError,"Invalid URDF"):
                    registry.import_bytes(b"<robot",version="2",**ATTR)
                self.assertEqual(registry.list_models(),[])
                self.assertEqual(list((Path(temporary)/"blobs").rglob("*.tmp")),[])

    def test_explicit_review_and_source_origin_gates_bundling(self):
        with tempfile.TemporaryDirectory() as temporary:
            with ModelRegistry(temporary) as r:
                src=FILES/"quadruped_valid.urdf"
                public=r.import_file(src,version="1",**ATTR)
                private=r.import_file(src,name="private",version="1",
                                      origin="user_upload",category="quadruped",
                                      license_id="CC0-1.0")
                fixture=r.import_file(src,name="fixture",version="1",
                                      origin="synthetic_fixture",category="quadruped",
                                      license_id="CC0-1.0")
                self.assertFalse(public["bundling_permitted"])
                self.assertFalse(private["bundling_permitted"])
                with self.assertRaisesRegex(RegistryError,"private/fixture"):
                    r.approve_public_license(private["id"],b"notice","operator")
                with self.assertRaisesRegex(RegistryError,"private/fixture"):
                    r.approve_public_license(fixture["id"],b"notice","operator")
                approved=r.approve_public_license(public["id"],b"CC0-1.0 notice\n","operator")
                self.assertTrue(approved["bundling_permitted"])
                self.assertFalse(r.get(private["id"])["bundling_permitted"])
                self.assertFalse(r.get(fixture["id"])["bundling_permitted"])
                self.assertFalse(approved["reference_performance"])

    def test_download_rejects_unsafe_scheme_and_remains_recoverable(self):
        with tempfile.TemporaryDirectory() as temporary:
            with ModelRegistry(temporary) as r:
                with self.assertRaisesRegex(AssetFetchError,"HTTPS"):
                    r.fetch_https("file:///etc/passwd",version="1",**ATTR)
                with self.assertRaises(AssetFetchError):
                    r.fetch_https("https://127.0.0.1:1/unavailable.urdf",version="1",**ATTR)
                self.assertEqual(r.list_models(),[])
                self.assertEqual(r.import_file(FILES/"quadruped_valid.urdf",
                                                version="1",**ATTR)["version"],"1")


if __name__=="__main__":
    unittest.main()
