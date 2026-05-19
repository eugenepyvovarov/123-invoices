#!/usr/bin/env python3
"""Generate a sanitized SQLite database for public screencasts."""

from __future__ import annotations

import argparse
import calendar
import shutil
import sqlite3
from pathlib import Path

TARGET_YEAR = 2025
SCALE_FACTOR = 0.83

ADJECTIVES = [
    "Apex",
    "Aurora",
    "Beacon",
    "Bright",
    "Cedar",
    "Cobalt",
    "Coral",
    "Crimson",
    "Echo",
    "Evergreen",
    "Golden",
    "Harbor",
    "Horizon",
    "Ivory",
    "Juniper",
    "Lunar",
    "Maple",
    "Nimbus",
    "Oak",
    "Pacific",
    "Quartz",
    "River",
    "Summit",
    "Timber",
    "Urban",
    "Violet",
    "Willow",
    "Zenith",
    "Cascade",
    "Driftwood",
    "Ember",
    "Frontier",
    "Grove",
    "Indigo",
    "Jetstream",
    "Keystone",
    "Lighthouse",
    "Monarch",
    "Northwind",
    "Opal",
    "Prairie",
    "Redwood",
    "Solstice",
    "Trident",
    "Unity",
    "Voyage",
    "Waypoint",
    "Yellowtail",
    "Zephyr",
]

NOUNS = [
    "Associates",
    "Consulting",
    "Dynamics",
    "Enterprises",
    "Fabricators",
    "Global",
    "Holdings",
    "Industries",
    "Labs",
    "Logistics",
    "Partners",
    "Resources",
    "Solutions",
    "Studios",
    "Systems",
    "Ventures",
    "Works",
    "Collective",
    "Analytics",
    "Networks",
    "Advisory",
    "Creative",
    "Developments",
    "Engineering",
    "Marketing",
    "Services",
    "Strategies",
    "Support",
    "Agency",
    "Capital",
]

SUFFIXES = ["LLC", "Ltd", "Inc.", "Co.", "Group", "PLC", "GmbH", "SARL"]

FIRST_NAMES = [
    "Alex",
    "Blake",
    "Casey",
    "Drew",
    "Elliot",
    "Finley",
    "Harper",
    "Jordan",
    "Kai",
    "Logan",
    "Morgan",
    "Parker",
    "Quinn",
    "Reese",
    "Sawyer",
    "Taylor",
    "Sydney",
    "Rowan",
    "Avery",
    "Riley",
]

LAST_NAMES = [
    "Anderson",
    "Bailey",
    "Carter",
    "Dawson",
    "Edwards",
    "Fletcher",
    "Grayson",
    "Hayes",
    "Irving",
    "Jensen",
    "Kensington",
    "Lawson",
    "Monroe",
    "Nolan",
    "Osborne",
    "Presley",
    "Ramsey",
    "Sinclair",
    "Tanner",
    "Vaughn",
    "Winslow",
    "Yeager",
    "Zimmer",
]

PROJECT_PREFIXES = [
    "Aurora",
    "Beacon",
    "Catalyst",
    "Delta",
    "Echo",
    "Fusion",
    "Genesis",
    "Harbor",
    "Ivory",
    "Juno",
    "Keystone",
    "Lumen",
    "Momentum",
    "Nova",
    "Orion",
    "Pioneer",
    "Quartz",
    "Radiant",
    "Summit",
    "Titan",
    "Umbra",
    "Velocity",
    "Waypoint",
    "Zenith",
    "Atlas",
    "Cosmos",
    "Drift",
    "Ember",
    "Forge",
    "Glacier",
    "Helios",
    "Impulse",
    "Jetstream",
    "Kodiak",
    "Lattice",
    "Mosaic",
    "Nimbus",
    "Odyssey",
    "Pulse",
    "Quasar",
    "Ranger",
    "Solstice",
    "Tribute",
    "Unity",
    "Voyager",
    "Wildflower",
    "Zephyr",
]

PROJECT_SUFFIXES = [
    "Analytics",
    "Dashboard",
    "Enablement",
    "Expansion",
    "Implementation",
    "Integration",
    "Launch",
    "Migration",
    "Modernization",
    "Onboarding",
    "Optimization",
    "Platform",
    "Portal",
    "Program",
    "Refresh",
    "Rollout",
    "Transformation",
    "Upgrade",
    "Workflow",
    "Experience",
    "Pilot",
    "Pipeline",
    "Revamp",
    "Initiative",
    "Operations",
    "Lifecycle",
    "Expedition",
    "Sprint",
    "Roadmap",
    "Blueprint",
]


def generate_company_name(index: int) -> str:
    a = ADJECTIVES[index % len(ADJECTIVES)]
    b = NOUNS[(index // len(ADJECTIVES)) % len(NOUNS)]
    c = SUFFIXES[(index // (len(ADJECTIVES) * len(NOUNS))) % len(SUFFIXES)]
    return f"{a} {b} {c}"


def generate_person_name(index: int) -> str:
    first = FIRST_NAMES[index % len(FIRST_NAMES)]
    last = LAST_NAMES[(index * 7) % len(LAST_NAMES)]
    return f"{first} {last}"


def slugify(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def generate_project_title(index: int) -> str:
    prefix = PROJECT_PREFIXES[index % len(PROJECT_PREFIXES)]
    suffix = PROJECT_SUFFIXES[index % len(PROJECT_SUFFIXES)]
    return f"{prefix} {suffix}"


def clamp_date(date_text: str, year: int) -> str:
    if not date_text:
        return date_text
    parts = date_text.split("-")
    if len(parts) != 3:
        return date_text
    original_year = int(parts[0])
    month = max(1, min(12, int(parts[1])))
    day = max(1, int(parts[2]))
    last_day = calendar.monthrange(year, month)[1]
    if day > last_day:
        day = last_day
    if original_year == year:
        return f"{year:04d}-{month:02d}-{day:02d}"
    if original_year < year:
        month, day = 1, 1
    else:
        month, day = 12, 31
    return f"{year:04d}-{month:02d}-{day:02d}"


def scale_amounts(cursor: sqlite3.Cursor, factor: float) -> None:
    targets = {
        "invoices_invoice": [
            "discount_value",
            "discount_amount",
            "tax_value",
            "tax_amount",
            "tax_base",
            "sub_total",
            "total_due",
            "base_currency_total",
            "amount_paid",
            "amount_due",
            "amount_overdue",
        ],
        "invoices_orderline": ["unit_price", "line_total"],
        "invoices_payment": ["amount", "base_currency_amount"],
        "invoices_paymentapplication": ["amount_applied"],
        "invoices_statement": [
            "total_balance",
            "current_due",
            "overdue_30",
            "overdue_60",
            "overdue_90",
            "overdue_over_90",
        ],
        "invoices_expense": ["amount"],
    }
    for table, columns in targets.items():
        set_clause = ", ".join(f"{column} = ROUND({column} * ?, 2)" for column in columns)
        params = [factor] * len(columns)
        cursor.execute(f"UPDATE {table} SET {set_clause}", params)


def restrict_to_year(conn: sqlite3.Connection, year: int) -> None:
    cursor = conn.cursor()
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    rows = cursor.execute(
        "SELECT id FROM invoices_invoice WHERE issued_date IS NULL OR issued_date < ? OR issued_date > ?",
        (start, end),
    ).fetchall()
    invoice_ids = [row[0] for row in rows]
    if invoice_ids:
        placeholders = ", ".join("?" for _ in invoice_ids)
        for table, column in [
            ("invoices_orderline", "invoice_id"),
            ("invoices_paymentapplication", "invoice_id"),
            ("invoices_expense", "invoice_id"),
        ]:
            cursor.execute(f"DELETE FROM {table} WHERE {column} IN ({placeholders})", invoice_ids)
        cursor.execute(f"DELETE FROM invoices_invoice WHERE id IN ({placeholders})", invoice_ids)
    cursor.execute("DELETE FROM invoices_paymentapplication WHERE invoice_id NOT IN (SELECT id FROM invoices_invoice)")
    cursor.execute(
        "DELETE FROM invoices_payment WHERE id NOT IN (SELECT DISTINCT payment_id FROM invoices_paymentapplication)"
    )
    cursor.execute(
        "DELETE FROM invoices_expense WHERE invoice_id IS NULL AND (date < ? OR date > ?)",
        (start, end),
    )
    cursor.execute(
        "DELETE FROM invoices_statement WHERE to_date < ? OR from_date > ?",
        (start, end),
    )
    conn.commit()


def update_dates(conn: sqlite3.Connection, year: int) -> None:
    cursor = conn.cursor()
    date_targets = [
        ("invoices_payment", "received_at"),
        ("invoices_statement", "from_date"),
        ("invoices_statement", "to_date"),
        ("invoices_statement", "sent_date"),
        ("invoices_expense", "date"),
    ]
    for table, column in date_targets:
        rows = cursor.execute(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
        for record_id, date_value in rows:
            normalized = clamp_date(date_value, year)
            if normalized != date_value:
                cursor.execute(
                    f"UPDATE {table} SET {column} = ? WHERE id = ?",
                    (normalized, record_id),
                )
    conn.commit()


def anonymize_companies(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    rows = cursor.execute("SELECT id, contact_name FROM invoices_company ORDER BY id").fetchall()
    for index, (company_id, contact_name) in enumerate(rows):
        new_name = generate_company_name(index)
        slug = slugify(new_name)
        assignments: list[str] = ["name = ?", "contact_phone_number = ?"]
        params: list[str | int] = [new_name, f"555-010-{index % 10000:04d}"]
        if contact_name:
            person_name = generate_person_name(index)
            assignments.extend(["contact_name = ?", "contact_email = ?"])
            params.extend([person_name, f"{slug}@example.com"])
        cursor.execute(
            f"UPDATE invoices_company SET {', '.join(assignments)} WHERE id = ?",
            (*params, company_id),
        )
    conn.commit()


def anonymize_active_customers(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT id FROM invoices_customer WHERE is_active = 1 ORDER BY id"
    ).fetchall()
    for index, (customer_id,) in enumerate(rows):
        person_name = generate_person_name(index)
        slug = slugify(person_name)
        cursor.execute(
            "UPDATE invoices_customer SET billing_contact_name = ?, billing_email = ? WHERE id = ?",
            (person_name, f"{slug}@example.com", customer_id),
        )
    conn.commit()


def anonymize_active_projects(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT id FROM invoices_project WHERE status = 'active' ORDER BY id"
    ).fetchall()
    for index, (project_id,) in enumerate(rows, start=1):
        title = generate_project_title(index - 1)
        code = f"SC-{index:03d}"
        cursor.execute(
            "UPDATE invoices_project SET title = ?, project_code = ? WHERE id = ?",
            (title, code, project_id),
        )
    conn.commit()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a sanitized screencast database copy from the live dataset.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("db.sqlite3"),
        help="Path to the source SQLite database",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("db_screencast.sqlite3"),
        help="Destination path where the sanitized database will be written",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the destination file if it exists already",
    )
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    source = args.source
    dest = args.dest

    if not source.exists():
        raise SystemExit(f"Source database not found: {source}")
    if dest.exists() and not args.overwrite:
        raise SystemExit(f"Destination already exists: {dest}. Use --overwrite to replace it.")

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)

    conn = sqlite3.connect(dest)
    conn.execute("PRAGMA foreign_keys = OFF;")
    conn.row_factory = sqlite3.Row

    restrict_to_year(conn, TARGET_YEAR)
    update_dates(conn, TARGET_YEAR)
    scale_amounts(conn.cursor(), SCALE_FACTOR)
    anonymize_companies(conn)
    anonymize_active_customers(conn)
    anonymize_active_projects(conn)

    conn.commit()
    conn.close()

    print(f"Sanitized database available at {dest}")


if __name__ == "__main__":
    main()
