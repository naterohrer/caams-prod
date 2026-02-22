#Seed the database with framework data from the json files
#Run once after first install:  python seed.py

import json
from pathlib import Path
from app.database import SessionLocal, engine
from app import models

DATA_DIR = Path(__file__).parent / "app" / "data"

#load the framework conf files
FRAMEWORK_FILES = [
    "cis_v8.json",
    "nist_csf_v2.json",
    "soc2_2017.json",
    "pci_dss_v4.json",
    "hipaa_security.json",
]

#check to see if famework name exists, else load the new conf
def seed_framework(db, data: dict) -> None:
    existing = db.query(models.Framework).filter(
        models.Framework.name == data["name"],
        models.Framework.version == data["version"],
    ).first()
    if existing:
        print(f"  Skipping (already exists): {data['name']} {data['version']}")
        return

    framework = models.Framework(name=data["name"], version=data["version"])
    db.add(framework)
    db.flush()

    for c in data["controls"]:
        db.add(
            models.Control(
                framework_id=framework.id,
                control_id=c["control_id"],
                title=c["title"],
                description=c["description"],
                required_tags=c["required_tags"],
                optional_tags=c["optional_tags"],
                evidence=c["evidence"],
                sub_controls=c.get("sub_controls", []),
            )
        )

    db.commit()
    print(f"  Seeded: {framework.name} {framework.version} ({len(data['controls'])} controls)")

#load tool list
def seed_tools(db, tools_data: list) -> None:
    added = 0
    for t in tools_data:
        existing = db.query(models.Tool).filter(models.Tool.name == t["name"]).first()
        if existing:
            continue
        tool = models.Tool(name=t["name"], category=t["category"])
        db.add(tool)
        db.flush()
        for tag in t["capabilities"]:
            db.add(models.ToolCapability(tool_id=tool.id, tag=tag))
        added += 1
    db.commit()
    print(f"  Seeded {added} new tools ({len(tools_data) - added} already existed)")


def seed():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("Seeding frameworks…")
        for filename in FRAMEWORK_FILES:
            with open(DATA_DIR / filename) as f:
                seed_framework(db, json.load(f))

        print("Seeding tool catalog…")
        with open(DATA_DIR / "tools_catalog.json") as f:
            seed_tools(db, json.load(f))

        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
