#!/usr/bin/env python3
"""Convert actual D02 report to a readable Unicode PDF using installed local LibreOffice."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
dest=ROOT/"artifacts/D02"
html=dest/"mechanical-report.html"
assert html.is_file(), "D02 HTML report required"
with tempfile.TemporaryDirectory(prefix="d02-lo-") as profile:
    result=subprocess.run(["libreoffice",f"-env:UserInstallation=file://{profile}",
      "--headless","--convert-to","pdf","--outdir",str(dest),str(html)],
      cwd=ROOT,text=True,capture_output=True,timeout=100)
    assert result.returncode==0,(result.stdout,result.stderr)
pdf=dest/"mechanical-report.pdf"
raw=pdf.read_bytes()
assert len(raw)>2000 and raw.startswith(b"%PDF-"),"Expected real PDF output"
metadata=subprocess.run(["pdfinfo",str(pdf)],capture_output=True,text=True,check=True)
assert "Pages:" in metadata.stdout and "Title:" in metadata.stdout,metadata.stdout
text=subprocess.run(["pdftotext",str(pdf),"-"],capture_output=True,text=True,check=True).stdout
assert "URDFTools" in metadata.stdout and "ArmLink" in text and "机械" in text,text[:300]
print(json.dumps({"status":"passed","pdf_bytes":len(raw),
                  "pdf_sha256":hashlib.sha256(raw).hexdigest(),
                  "unicode_text_verified":True,"report":"artifacts/D02/mechanical-report.pdf"}))
