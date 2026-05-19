#!/usr/bin/env python3
"""Render an invoice using a Django template and export to HTML/PDF.

Example:
    python scripts/render_invoice.py --invoice-id 1 --template invoices/billings_tf_eur.html \
        --pdf tmp/invoice-1.pdf --html tmp/invoice-1.html
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import django


def setup_django(settings_module: str = "app.settings") -> None:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
    django.setup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--invoice-id", type=int, required=True, help="Invoice primary key")
    parser.add_argument(
        "--template",
        default="invoices/billings_tf_eur.html",
        help="Django template path (defaults to the Billings-styled template)",
    )
    parser.add_argument("--pdf", type=Path, help="Destination PDF path", required=True)
    parser.add_argument("--html", type=Path, help="Optional HTML output path", default=None)
    parser.add_argument(
        "--settings",
        default="app.settings",
        help="DJANGO_SETTINGS_MODULE to use (default app.settings)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_django(args.settings)

    from django.conf import settings
    from django.template.loader import render_to_string
    from invoices.models import Invoice, OrderLine

    invoice = (
        Invoice.objects.select_related(
            "issuer__company",
            "customer__company",
            "currency",
            "project",
        ).get(pk=args.invoice_id)
    )
    order_lines = OrderLine.objects.filter(invoice=invoice).order_by("id")

    context = {
        "invoice": invoice,
        "order_lines": order_lines,
    }

    html_content = render_to_string(args.template, context)

    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(html_content, encoding="utf-8")

    args.pdf.parent.mkdir(parents=True, exist_ok=True)
    try:
        from weasyprint import HTML

        HTML(string=html_content, base_url=str(settings.BASE_DIR)).write_pdf(str(args.pdf))
    except Exception as exc:  # pragma: no cover
        print("Warning: could not render PDF via WeasyPrint", exc, file=sys.stderr)
        if not args.html:
            raise

    print(f"Rendered invoice {invoice.pk} using template {args.template}")
    print(f"PDF saved to {args.pdf}")
    if args.html:
        print(f"HTML saved to {args.html}")


if __name__ == "__main__":
    main()
