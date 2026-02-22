#!/usr/bin/env python3
"""
Import a CIS Controls xlsx file and generate a CAAMS-compatible JSON template.

Usage
-----
    python import_cis.py CIS_Controls_v8.1.xlsx
    python import_cis.py CIS_Controls_v8.1.xlsx --version v8.1
    python import_cis.py CIS_Controls_v8.1.xlsx --version v8.1 --ig 2
    python import_cis.py CIS_Controls_v8.1.xlsx --sheet "CIS Controls" --seed

Options
-------
  --version VERSION   Version string written into the JSON (default: v8)
  --sheet   SHEET     Worksheet name to parse (auto-detected if omitted)
  --ig      {1,2,3}   Minimum Implementation Group level to include (default: 1)
  --output  FILE      Output file path (default: app/data/cis_<version>.json)
  --seed              After generating the JSON, seed it into the running DB
  --force             Overwrite the output file if it already exists
"""

import argparse
import json
import sys
from pathlib import Path

from app.importers.cis_xlsx import parse_cis_xlsx


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a CAAMS framework JSON from a CIS Controls xlsx.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("xlsx", help="Path to the CIS Controls xlsx file")
    parser.add_argument(
        "--version", default="v8",
        help="Version label written into the JSON (default: v8)",
    )
    parser.add_argument(
        "--sheet", default=None,
        help="Worksheet name to parse (auto-detected if omitted)",
    )
    parser.add_argument(
        "--ig", type=int, choices=[1, 2, 3], default=1,
        help="Minimum Implementation Group to include (default: 1 = all)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output JSON path (default: app/data/cis_<version>.json)",
    )
    parser.add_argument(
        "--seed", action="store_true",
        help="Seed the generated framework into the database after writing",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite the output file if it already exists",
    )
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        sys.exit(f"ERROR: file not found: {xlsx_path}")

    # Resolve output path
    version_slug = args.version.replace(".", "_").replace(" ", "_")
    out_path = Path(args.output) if args.output else (
        Path(__file__).parent / "app" / "data" / f"cis_{version_slug}.json"
    )

    if out_path.exists() and not args.force:
        sys.exit(
            f"ERROR: {out_path} already exists.  Use --force to overwrite."
        )

    # Parse
    print(f"Parsing {xlsx_path} …")
    try:
        framework = parse_cis_xlsx(
            xlsx_path,
            version=args.version,
            sheet_name=args.sheet,
            min_ig=args.ig,
        )
    except Exception as e:
        sys.exit(f"ERROR: {e}")

    ctrl_count = len(framework["controls"])
    sub_count  = sum(len(c["sub_controls"]) for c in framework["controls"])
    print(f"  Parsed {ctrl_count} controls, {sub_count} safeguards")

    # Write JSON
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(framework, indent=2))
    print(f"  Written to {out_path}")

    # Optional DB seed
    if args.seed:
        print("Seeding into database …")
        try:
            from app.database import SessionLocal, engine
            from app import models

            models.Base.metadata.create_all(bind=engine)
            db = SessionLocal()
            try:
                existing = db.query(models.Framework).filter(
                    models.Framework.name    == framework["name"],
                    models.Framework.version == framework["version"],
                ).first()
                if existing:
                    print(f"  Framework already exists (id={existing.id}) — skipping DB insert.")
                    print("  Delete it first if you want to re-import.")
                else:
                    fw = models.Framework(
                        name=framework["name"],
                        version=framework["version"],
                    )
                    db.add(fw)
                    db.flush()
                    for c in framework["controls"]:
                        db.add(models.Control(
                            framework_id  = fw.id,
                            control_id    = c["control_id"],
                            title         = c["title"],
                            description   = c["description"],
                            required_tags = c["required_tags"],
                            optional_tags = c["optional_tags"],
                            evidence      = c["evidence"],
                            sub_controls  = c["sub_controls"],
                        ))
                    db.commit()
                    print(f"  Seeded: {framework['name']} {framework['version']} "
                          f"({ctrl_count} controls)")
            finally:
                db.close()
        except Exception as e:
            sys.exit(f"ERROR during seed: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
