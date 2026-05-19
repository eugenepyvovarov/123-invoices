#!/usr/bin/env python3
"""Utility to convert a Billings Pro .bptemplate bundle to XML/HTML and PDF.

Usage:
    python scripts/export_bptemplate.py path/to/template.bptemplate [--output tmp/billings_templates/export]

Requirements:
    * macOS `plutil`
    * Python package `WeasyPrint`
"""
from __future__ import annotations

import argparse
import html
import shutil
import subprocess
from pathlib import Path

try:
    from weasyprint import HTML  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "WeasyPrint is required. Install with `pip install weasyprint` inside your environment."
    ) from exc


def run_plutil_to_xml(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "plutil",
            "-convert",
            "xml1",
            str(source),
            "-o",
            str(destination),
        ],
        check=True,
    )


def copy_template_bundle(source: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / source.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target


def build_html(template_xml: Path, printinfo_xml: Path) -> str:
    template_content = template_xml.read_text(encoding="utf-8")
    printinfo_content = printinfo_xml.read_text(encoding="utf-8")
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>{html.escape(template_xml.stem)} – Billings Template</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; }}
    h1 {{ font-size: 1.6rem; }}
    h2 {{ margin-top: 2rem; }}
    pre {{ background: #f7f7f8; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
    .metadata {{ margin-bottom: 2rem; }}
  </style>
</head>
<body>
  <h1>Billings Pro Template Preview</h1>
  <p class=\"metadata\">Template source: <code>{html.escape(str(template_xml))}</code></p>
  <h2>Template.archive (XML)</h2>
  <pre>{html.escape(template_content)}</pre>
  <h2>Printinfo.archive (XML)</h2>
  <pre>{html.escape(printinfo_content)}</pre>
</body>
</html>"""


def generate(html_content: str, html_path: Path, pdf_path: Path) -> None:
    html_path.write_text(html_content, encoding="utf-8")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        HTML(string=html_content, base_url=str(html_path.parent)).write_pdf(str(pdf_path))
        print(f"Preview PDF: {pdf_path}")
    except Exception as exc:  # pragma: no cover
        print("Warning: Could not render PDF with WeasyPrint:", exc)
        print("The HTML preview is still available for manual inspection.")



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to the .bptemplate directory")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tmp/exported_templates"),
        help="Directory where outputs will be written",
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Template path not found: {source}")

    output_root = args.output.expanduser().resolve()
    bundle_copy = copy_template_bundle(source, output_root)

    template_xml = bundle_copy / "Template.xml"
    printinfo_xml = bundle_copy / "Printinfo.xml"

    run_plutil_to_xml(bundle_copy / "Template.archive", template_xml)
    run_plutil_to_xml(bundle_copy / "Printinfo.archive", printinfo_xml)

    html_content = build_html(template_xml, printinfo_xml)
    html_path = bundle_copy / "template_preview.html"
    pdf_path = bundle_copy / "template_preview.pdf"
    generate(html_content, html_path, pdf_path)

    print("Export completed")
    print(f"Copied bundle: {bundle_copy}")
    print(f"Template XML: {template_xml}")
    print(f"Print info XML: {printinfo_xml}")
    print(f"Preview HTML: {html_path}")


if __name__ == "__main__":
    main()
