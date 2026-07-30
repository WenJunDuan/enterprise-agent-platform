#!/usr/bin/env python3
"""Build real document-format smoke fixtures from source documents and pinned assets."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "scripts" / "document_format_fixtures"
PYXLSB_COMMIT = "a59b6ddcadd89cf96e478152b7c4fb051588a747"
PYXLSB_URL = (
    "https://raw.githubusercontent.com/willtrnr/pyxlsb/"
    f"{PYXLSB_COMMIT}/test_files/test.xlsb"
)
PYXLSB_SHA256 = "94e006f195668677170b9e0efb7ba8d443fa6c9c2149ebd78b7a67d77a99c09e"


def _write_odf(path: Path, mimetype: str, content_xml: str, *, macro: bool = False) -> None:
    manifest_entries = ""
    if macro:
        manifest_entries = """
 <manifest:file-entry manifest:full-path="Basic/" manifest:media-type="application/vnd.sun.star.basic-libraries"/>
 <manifest:file-entry manifest:full-path="Basic/Standard/" manifest:media-type="application/vnd.sun.star.basic-library"/>
 <manifest:file-entry manifest:full-path="Basic/Standard/Module1.xml" manifest:media-type="text/xml"/>
 <manifest:file-entry manifest:full-path="Basic/Standard/script-lb.xml" manifest:media-type="text/xml"/>
 <manifest:file-entry manifest:full-path="Basic/script-lc.xml" manifest:media-type="text/xml"/>"""
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">
 <manifest:file-entry manifest:full-path="/" manifest:media-type="{mimetype}"/>
 <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>{manifest_entries}
</manifest:manifest>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", mimetype, compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/manifest.xml", manifest)
        archive.writestr("content.xml", content_xml)
        if macro:
            archive.writestr("Basic/script-lc.xml", _BASIC_LIBRARIES)
            archive.writestr("Basic/Standard/script-lb.xml", _BASIC_LIBRARY)
            archive.writestr("Basic/Standard/Module1.xml", _BASIC_MODULE)


_BASIC_LIBRARIES = """<?xml version="1.0" encoding="UTF-8"?>
<library:libraries xmlns:library="http://openoffice.org/2000/library">
 <library:library library:name="Standard" library:link="false"/>
</library:libraries>
"""
_BASIC_LIBRARY = """<?xml version="1.0" encoding="UTF-8"?>
<library:library xmlns:library="http://openoffice.org/2000/library" library:name="Standard" library:readonly="false" library:passwordprotected="false">
 <library:element library:name="Module1"/>
</library:library>
"""
_BASIC_MODULE = """<?xml version="1.0" encoding="UTF-8"?>
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic" script:moduleType="normal"><![CDATA[
Sub Main
  documentPath = ConvertFromURL(ThisComponent.URL)
  markerPath = Left(documentPath, InStrRev(documentPath, "/")) & "macro-side-effect.txt"
  fileNumber = FreeFile
  Open markerPath For Output As #fileNumber
  Print #fileNumber, "MACRO_EXECUTED"
  Close #fileNumber
End Sub
]]></script:module>
"""


def _writer_xml(*, macro: bool) -> str:
    listener = ""
    if macro:
        listener = """
   <office:event-listeners>
    <script:event-listener script:language="ooo:script" script:event-name="dom:load" xlink:type="simple" xlink:href="vnd.sun.star.script:Standard.Module1.Main?language=Basic&amp;location=document"/>
   </office:event-listeners>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:script="urn:oasis:names:tc:opendocument:xmlns:script:1.0" xmlns:xlink="http://www.w3.org/1999/xlink" office:version="1.3">
 <office:scripts/><office:automatic-styles/><office:body><office:text>{listener}
  <text:h text:outline-level="1">招投标文档格式验收</text:h>
  <text:p>真实 Writer 文档，包含中文正文与金额 880 元。</text:p>
 </office:text></office:body>
</office:document-content>
"""


_CALC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.3">
 <office:automatic-styles/><office:body><office:spreadsheet><table:table table:name="报价">
  <table:table-row><table:table-cell office:value-type="string"><text:p>项目</text:p></table:table-cell><table:table-cell office:value-type="string"><text:p>金额</text:p></table:table-cell></table:table-row>
  <table:table-row><table:table-cell office:value-type="string"><text:p>服务</text:p></table:table-cell><table:table-cell office:value-type="float" office:value="880"><text:p>880</text:p></table:table-cell></table:table-row>
 </table:table></office:spreadsheet></office:body>
</office:document-content>
"""
_IMPRESS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0" xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" office:version="1.3">
 <office:automatic-styles/><office:body><office:presentation>
  <draw:page draw:name="page1"><draw:frame presentation:class="title" svg:x="2cm" svg:y="2cm" svg:width="20cm" svg:height="3cm"><draw:text-box><text:p>投标方案真实演示文稿</text:p></draw:text-box></draw:frame></draw:page>
 </office:presentation></office:body>
</office:document-content>
"""


def _run(argv: list[str]) -> None:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=120)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {argv}\n{completed.stderr}")


def _convert(soffice: str, source: Path, output_dir: Path, extension: str, filter_name: str) -> Path:
    profile = source.parent / f"profile-{uuid.uuid4().hex}"
    _run(
        [
            soffice,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--convert-to",
            f"{extension}:{filter_name}",
            "--outdir",
            str(output_dir),
            str(source),
        ]
    )
    converted = output_dir / f"{source.stem}.{extension}"
    if not converted.is_file():
        raise RuntimeError(f"LibreOffice did not create {converted}")
    return converted


def _download_xlsb(destination: Path) -> None:
    _run(
        [
            "curl",
            "--fail",
            "--location",
            "--silent",
            "--show-error",
            "--proto",
            "=https",
            "--tlsv1.2",
            "--output",
            str(destination),
            PYXLSB_URL,
        ]
    )
    content = destination.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != PYXLSB_SHA256:
        raise RuntimeError(f"pyxlsb fixture checksum mismatch: {digest}")


def build() -> None:
    """Rebuild the canonical real-file fixture matrix from pinned inputs."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    magick = shutil.which("magick")
    if soffice is None or magick is None:
        raise RuntimeError("fixture build requires LibreOffice and ImageMagick")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old_fixture in OUTPUT_DIR.iterdir():
        if old_fixture.is_file():
            old_fixture.unlink()
    with tempfile.TemporaryDirectory(prefix="document-fixtures-") as temp_name:
        staging = Path(temp_name)
        writer = staging / "writer.odt"
        calc = staging / "calc.ods"
        impress = staging / "impress.odp"
        macro_odt = OUTPUT_DIR / "macro-on-open.odt"
        _write_odf(writer, "application/vnd.oasis.opendocument.text", _writer_xml(macro=False))
        _write_odf(calc, "application/vnd.oasis.opendocument.spreadsheet", _CALC_XML)
        _write_odf(impress, "application/vnd.oasis.opendocument.presentation", _IMPRESS_XML)
        _write_odf(
            macro_odt,
            "application/vnd.oasis.opendocument.text",
            _writer_xml(macro=True),
            macro=True,
        )
        shutil.copyfile(calc, OUTPUT_DIR / "sample.ods")
        shutil.copyfile(impress, OUTPUT_DIR / "sample.odp")
        conversions = [
            (writer, "doc", "MS Word 97", "sample.doc"),
            (writer, "docx", "Office Open XML Text", "sample.docx"),
            (writer, "pdf", "writer_pdf_Export", "sample.pdf"),
            (calc, "xls", "MS Excel 97", "sample.xls"),
            (calc, "xlsx", "Calc MS Excel 2007 XML", "sample.xlsx"),
            (calc, "xlsm", "Calc MS Excel 2007 VBA XML", "sample.xlsm"),
            (impress, "ppt", "MS PowerPoint 97", "sample.ppt"),
            (impress, "pptx", "Impress MS PowerPoint 2007 XML", "sample.pptx"),
        ]
        converted_dir = staging / "converted"
        converted_dir.mkdir()
        for source, extension, filter_name, target_name in conversions:
            converted = _convert(soffice, source, converted_dir, extension, filter_name)
            shutil.copyfile(converted, OUTPUT_DIR / target_name)
            converted.unlink()
        image_source = staging / "source.png"
        _run(
            [
                magick,
                "-size",
                "360x140",
                "xc:white",
                "-fill",
                "black",
                "-pointsize",
                "24",
                "-draw",
                "text 20,75 'Tender OCR 2026'",
                str(image_source),
            ]
        )
        for extension in ("png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"):
            destination = OUTPUT_DIR / f"sample.{extension}"
            if extension == "bmp":
                _run([magick, str(image_source), "-compress", "none", f"BMP3:{destination}"])
            else:
                _run([magick, str(image_source), str(destination)])
    text_payloads = {
        "sample.txt": "招投标纯文本底稿，金额 880 元。\n",
        "sample.csv": "项目,金额\n服务,880\n",
        "sample.md": "# 招投标底稿\n\n- 金额：880 元\n",
        "sample.json": json.dumps({"项目": "服务", "金额": 880}, ensure_ascii=False),
        "sample.tsv": "项目\t金额\n服务\t880\n",
    }
    for name, content in text_payloads.items():
        (OUTPUT_DIR / name).write_text(content, encoding="utf-8")
    _download_xlsb(OUTPUT_DIR / "sample.xlsb")
    sources = {
        "generated_by": "scripts/build_document_format_fixtures.py",
        "generated_with": subprocess.run(
            [soffice, "--version"], capture_output=True, text=True, check=True
        ).stdout.strip(),
        "fixtures": {
            "sample.xlsb": {
                "url": PYXLSB_URL,
                "repository": "https://github.com/willtrnr/pyxlsb",
                "commit": PYXLSB_COMMIT,
                "license": "LGPL-3.0",
                "license_url": "https://github.com/willtrnr/pyxlsb/blob/master/COPYING.LESSER",
                "sha256": PYXLSB_SHA256,
            }
        },
    }
    (OUTPUT_DIR / "SOURCES.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    build()
