# CAAMS — Compliance and Auditing Made Simple

A lightweight, self-hosted compliance coverage tool. Pick a security framework, select the tools in your environment, and get an auditor-ready gap analysis in seconds — with per-control notes, evidence links, compensating control overrides, and export to XLSX or PDF.

---

## Features

| Feature | Details |
|---|---|
| **Framework coverage mapping** | Map your tool stack against CIS Controls v8, NIST CSF v2, SOC 2 (2017), PCI DSS v4.0, and HIPAA Security Rule |
| **Tool configuration** | Toggle MFA enforcement, log retention days, backup testing, and hardening per tool to unlock additional coverage tags |
| **Per-control detail drawer** | Click any control row to open a side panel with description, notes, evidence link, and compensating control override |
| **Evidence / process links** | Paste a URL per control (SharePoint, Google Drive, Confluence, etc.) — opens directly from the drawer |
| **Compensating control overrides** | Manually set a control's status to Covered / Partial / Not Covered with a justification and optional expiry date |
| **Tool recommendations** | Auto-ranked list of tools not yet in the assessment that would close the most gaps |
| **Assessment clone** | Duplicate any assessment including tools, ownership, and notes |
| **Assessment history** | Load any previously saved assessment without leaving the page |
| **Ownership tracking** | Assign an owner, team, and evidence owner per control — inline editable |
| **XLSX export** | Four-sheet workbook: Summary, Coverage Report (with notes, evidence link, override columns), Evidence Checklist, Recommendations |
| **PDF export** | Branded cover page, executive summary, and per-control coverage table |
| **REST API** | Full FastAPI backend with interactive Swagger docs at `/docs` |

---

## Supported Frameworks

| Framework | Version | Controls |
|---|---|---|
| CIS Controls | v8 | 18 |
| NIST Cybersecurity Framework | v2.0 | 6 functions / 22 categories |
| SOC 2 Trust Services Criteria | 2017 | 9 |
| PCI DSS | v4.0 | 12 requirements |
| HIPAA Security Rule | 45 CFR Part 164 | 16 standards |

Additional frameworks can be added by dropping a JSON file into `app/data/` and re-running `seed.py` — see [Adding Frameworks](#adding-frameworks) below.

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, Pydantic v2
- **Database**: SQLite (zero-config, file-based — `caams.db`)
- **Exports**: openpyxl (XLSX), ReportLab (PDF)
- **Frontend**: Vanilla JS, Tailwind CSS (CDN), no build step

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Seed the database

Loads all framework definitions and the tool catalog. Safe to re-run — skips anything already present.

```bash
python seed.py
```

### 3. Set the secret key

CAAMS requires a secret key to sign JWT tokens. The app will **refuse to start** without it.

```bash
export CAAMS_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

For a persistent dev setup, add that line to your shell profile or a local `.env` file.

### 4. Start the server

The app always uses HTTPS. Self-signed development certificates are included in `certs/`:

```bash
uvicorn app.main:app --reload \
  --port 8443 \
  --ssl-certfile certs/cert.pem \
  --ssl-keyfile  certs/key.pem
```

Then open **https://localhost:8443** in your browser (accept the self-signed cert warning). On first visit you will be prompted to create the initial admin account.

For production with a CA-signed certificate see the [Production Deployment](#production-deployment) section below.

---

## Usage

### Creating an assessment

1. Enter an **assessment name** (e.g. `Q1 2026 CIS Review`)
2. Select a **framework**
3. Check the tools deployed in your environment — expand each to configure options (MFA enforced, log retention, etc.)
4. Click **Analyze Coverage →**

### Reading the results

- **Green / Covered** — all required capability tags are satisfied by your selected tools
- **Amber / Partial** — some required tags are missing, but at least one is present
- **Red / Not Covered** — no required tags are satisfied

The coverage score is `covered + 0.5 × partial` controls as a percentage.

### Control detail drawer

Click any row (or **Details →**) to open the side panel for that control:

- **Description** — what the control requires
- **Status override** — manually mark as Covered, Partial, or Not Covered (compensating controls). Add a justification and an optional expiry date; the override reverts to auto-computed when it expires.
- **Notes** — free-text audit notes or context, saved automatically on blur
- **Evidence / Process Link** — paste the URL to your policy document, runbook, or evidence folder. Click **Open ↗** to launch it directly.
- **Coverage detail** — which tools contribute, which tags are missing, and the full list of evidence items required by the framework

Indicators in the table:
- `✎` on the status badge = control has a manual override
- `●` on the title = control has notes or an evidence link

### Tool recommendations

Click **Tool Recommendations** below the results table to see tools (ranked by gap coverage) that you could add to improve your score.

### Ownership

Inline-edit the **Owner**, **Team**, and **Evidence Owner** columns directly in the table — saves on blur.

### Clone an assessment

Use **Clone** in the toolbar to create an exact copy (name, tools, ownership, notes). Useful for quarterly snapshots or framework comparisons.

### Load a previous assessment

Use **Load Assessment** in the header to switch between any previously saved assessment.

---

## Authentication

CAAMS uses JWT-based authentication. All API endpoints (except `/health` and `/auth/setup`) require a valid bearer token.

### Roles

| Role | Permissions |
|---|---|
| `admin` | Full access: create/delete assessments, manage users, all writes |
| `contributor` | Create/edit assessments, update notes, ownership, and overrides |
| `viewer` | Read-only access to all assessments and results |

### First-run setup

On first visit the UI shows a setup screen to create the initial admin account. Via API:

```bash
curl -X POST https://localhost:8443/auth/setup \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "YourPassword"}'
```

### Logging in

```bash
curl -X POST https://localhost:8443/auth/login \
  -d "username=admin&password=YourPassword"
# returns {"access_token": "...", "token_type": "bearer", "role": "admin"}
```

Pass the token in the `Authorization` header for all subsequent requests:

```bash
curl https://localhost:8443/assessments/ \
  -H "Authorization: Bearer <token>"
```

Tokens expire after **8 hours**. Brute-force is limited to **10 login attempts per minute** per IP.

### Managing users (admin only)

| Method | Path | Action |
|---|---|---|
| `GET` | `/auth/users` | List all users |
| `POST` | `/auth/users` | Create a user (`username`, `password`, `role`) |
| `PATCH` | `/auth/users/{id}` | Update role, password, or active status |
| `DELETE` | `/auth/users/{id}` | Delete a user |

Password requirements: 8–128 characters.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CAAMS_SECRET_KEY` | **Yes** | 64-char hex string used to sign JWTs. Generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`. App refuses to start without it. |
| `CAAMS_CORS_ORIGIN` | No | Set to your intranet hostname (e.g. `https://caams.corp.local`) to enable credentialed cross-origin requests. If unset, CORS is open with credentials disabled (same-origin browser requests always work). |

In production these are loaded from `/etc/caams.env` by the systemd unit. In development, `export` them in your shell or add them to a `.env` file.

---

## Logging

Two rotating log files are written to `logs/` in the project root (10 MB per file, 5 backups — 50 MB max each). All entries also appear in stdout / `journalctl -u caams`.

### `logs/access.log` — every HTTP request

```
2026-02-19 12:34:56 | 10.0.0.1 | POST /auth/login | 200 | 13ms
2026-02-19 12:34:57 | 10.0.0.1 | GET /assessments/5/results | 200 | 87ms
```

### `logs/app.log` — application events

```
2026-02-19 12:34:55 | INFO     | caams.app | STARTUP | CAAMS v0.2.0 | logging active
2026-02-19 12:34:56 | WARNING  | caams.app | LOGIN failed | username=badguy | ip=10.0.0.3
2026-02-19 12:34:57 | INFO     | caams.app | LOGIN success | user=admin | role=admin | ip=10.0.0.1
2026-02-19 12:35:10 | INFO     | caams.app | ASSESSMENT created | id=5 | name=Q1 Audit | framework=CIS Controls | user=admin
2026-02-19 12:35:30 | WARNING  | caams.app | OVERRIDE | assessment=5 | control=CIS-3 | status=covered | expires=2026-06-01 | by=admin
2026-02-19 12:36:00 | WARNING  | caams.app | ASSESSMENT deleted | id=3 | name=Old Test | by=admin
```

Events logged: startup, admin account creation, login success/failure (with IP), user created/updated/deleted, assessment created/deleted, status overrides set, unhandled exceptions (with full traceback at ERROR level).

---

## Exports

### XLSX (`/assessments/{id}/export`)

| Sheet | Contents |
|---|---|
| Summary | Assessment name, framework, and aggregate metrics |
| Coverage Report | All controls with status, owners, covered-by, missing tags, notes, evidence link, and override details. Overridden rows are highlighted. |
| Evidence Checklist | One row per evidence item, pre-populated with owners and notes — ready to hand to an auditor |
| Recommendations | Missing capability tags ranked by how many controls require them — shows exactly what gaps remain (omitted if fully covered) |

### PDF (`/assessments/{id}/export/pdf`)

Branded report with cover page, executive summary, and a color-coded per-control table.

---

## API Reference

Interactive Swagger UI is available at **/docs** (e.g. `https://localhost:8443/docs`).

**Auth** (no token required for setup and login)

| Method | Path | Description |
|---|---|---|
| `GET` | `/auth/setup-needed` | Returns `{"needed": true}` if no users exist yet |
| `POST` | `/auth/setup` | Create the first admin account (blocked once any user exists) |
| `POST` | `/auth/login` | Exchange credentials for a JWT (form-encoded, rate-limited 10/min) |
| `GET` | `/auth/me` | Return the current user's profile |
| `GET` | `/auth/users` | List all users (admin) |
| `POST` | `/auth/users` | Create a user (admin) |
| `PATCH` | `/auth/users/{id}` | Update role, password, or active status (admin) |
| `DELETE` | `/auth/users/{id}` | Delete a user (admin) |

**Frameworks & Tools**

| Method | Path | Description |
|---|---|---|
| `GET` | `/frameworks` | List all loaded frameworks |
| `GET` | `/frameworks/{id}/controls` | List controls for a framework |
| `GET` | `/tools` | List all tools in the catalog |
| `POST` | `/tools` | Add a tool manually (admin) |
| `DELETE` | `/tools/{id}` | Remove a tool (admin) |
| `GET` | `/tools/template/download` | Download a JSON template for bulk upload |
| `POST` | `/tools/upload` | Bulk-import tools from a JSON file (admin) |

**Assessments**

| Method | Path | Description |
|---|---|---|
| `POST` | `/assessments` | Create a new assessment (contributor) |
| `GET` | `/assessments` | List all assessments (newest first) |
| `GET` | `/assessments/history` | List assessments with pre-computed summary metrics |
| `GET` | `/assessments/{id}` | Get assessment metadata |
| `GET` | `/assessments/{id}/results` | Compute and return full coverage results |
| `DELETE` | `/assessments/{id}` | Delete assessment and all related data (admin) |
| `POST` | `/assessments/{id}/clone` | Clone with all tools, ownership, and notes (contributor) |
| `GET` | `/assessments/{id}/recommendations` | Capability gaps ranked by controls affected |
| `PATCH` | `/assessments/{id}/controls/{cid}/ownership` | Set owner / team / evidence owner (contributor) |
| `PATCH` | `/assessments/{id}/controls/{cid}/notes` | Upsert notes, evidence URL, and status override (contributor) |
| `GET` | `/assessments/{id}/controls/{cid}/notes` | Get notes for a single control |
| `GET` | `/assessments/{id}/export` | Download XLSX workbook |
| `GET` | `/assessments/{id}/export/pdf` | Download PDF report |

**Misc**

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check (no auth required) |

---

## Adding Frameworks

1. Create a JSON file in `app/data/` following this structure:

```json
{
  "name": "My Framework",
  "version": "v1.0",
  "controls": [
    {
      "control_id": "MF-1",
      "title": "Control Title",
      "description": "What this control requires.",
      "required_tags": ["tag-a", "tag-b"],
      "optional_tags": ["tag-c"],
      "evidence": [
        "Evidence item 1",
        "Evidence item 2"
      ]
    }
  ]
}
```

2. Add the filename to `FRAMEWORK_FILES` in `seed.py`
3. Re-run `python seed.py` — existing data is not affected

**Tags** must match capability tags in `app/data/tools_catalog.json` for controls to be satisfiable by existing tools. Run the following to see all available tags:

```bash
python3 -c "
import json
data = json.load(open('app/data/tools_catalog.json'))
tags = sorted({t for tool in data for t in tool['capabilities']})
print('\n'.join(tags))
"
```

---

## Adding Tools

Edit `app/data/tools_catalog.json` and add an entry:

```json
{
  "name": "My Tool",
  "category": "EDR",
  "capabilities": ["endpoint-protection", "malware-detection", "EDR"]
}
```

Re-run `python seed.py` to load it. The tool will immediately appear in the setup catalog.

---

## Production Deployment

`install_service.sh` automates a full production install on any systemd-based Linux host (tested on Ubuntu 22.04+). It manages its own virtualenv — no manual `pip install` required.

```bash
sudo bash install_service.sh
```

What it does:
1. Verifies prerequisites (`systemctl` present, `python3` on PATH)
2. Copies the app to `/opt/caams/` (skipped if already running from that path)
3. Creates a virtualenv at `/opt/caams/venv` and installs all dependencies into it (works on Ubuntu 22.04+ where system pip is locked by PEP 668)
4. **Requires** TLS certificates at `certs/cert.pem` + `certs/key.pem` — prints generation instructions and aborts if they are missing. To generate a self-signed cert:
   ```bash
   mkdir -p /opt/caams/certs
   openssl req -x509 -newkey rsa:4096 \
     -keyout /opt/caams/certs/key.pem \
     -out    /opt/caams/certs/cert.pem \
     -sha256 -days 3650 -nodes \
     -subj   "/CN=$(hostname)" \
     -addext "subjectAltName=DNS:$(hostname),IP:$(hostname -I | awk '{print $1}')"
   ```
5. Creates a dedicated `caams` system user and group (no login shell, no home dir)
6. Sets file ownership/permissions and creates `/opt/caams/logs/` (mode 750)
7. Generates a random `CAAMS_SECRET_KEY` and writes it to `/etc/caams.env` (readable only by root and the service account). The installer **refuses to proceed** if an existing `/etc/caams.env` still contains the development default key.
8. Seeds the database via `seed.py` if no `caams.db` exists yet
9. Writes the systemd unit file to `/etc/systemd/system/caams.service`
10. Enables the service (auto-start on boot) and starts it immediately

After install:
```bash
sudo systemctl status caams
sudo journalctl -u caams -f          # live log stream
sudo tail -f /opt/caams/logs/app.log # app events only
```

To use a CA-signed certificate instead of the self-signed one:
```bash
sudo cp your-cert.pem /opt/caams/certs/cert.pem
sudo cp your-key.pem  /opt/caams/certs/key.pem
sudo systemctl restart caams
```

---

## Data Storage

All data is stored in `caams.db` (SQLite) in the project root. To reset completely:

```bash
rm caams.db && python seed.py
```

The database is created automatically on first run. No migrations are required for a fresh install — `SQLAlchemy` creates all tables from the models on startup.

---

## Project Structure

```
caams/
├── app/
│   ├── data/                  # Framework JSON files and tool catalog
│   │   ├── cis_v8.json
│   │   ├── nist_csf_v2.json
│   │   ├── soc2_2017.json
│   │   ├── pci_dss_v4.json
│   │   ├── hipaa_security.json
│   │   └── tools_catalog.json
│   ├── engine/
│   │   └── mapper.py          # Coverage computation engine
│   ├── importers/
│   │   └── cis_xlsx.py        # CIS Controls XLSX importer
│   ├── routers/
│   │   ├── assessments.py     # Assessment CRUD, notes, clone, recommendations
│   │   ├── auth.py            # Login, setup, user management endpoints
│   │   ├── export.py          # XLSX export
│   │   ├── frameworks.py      # Framework and control endpoints
│   │   ├── pdf_export.py      # PDF export
│   │   └── tools.py           # Tool catalog endpoints
│   ├── auth.py                # JWT signing/verification, password hashing, role dependencies
│   ├── database.py            # SQLAlchemy setup (SQLite, absolute path)
│   ├── limiter.py             # Shared slowapi rate limiter instance
│   ├── logging_config.py      # Rotating file handler setup (access.log + app.log)
│   ├── main.py                # FastAPI app, middleware, CORS, lifespan
│   ├── models.py              # SQLAlchemy ORM models
│   └── schemas.py             # Pydantic request/response schemas (with field limits)
├── logs/                      # Runtime log files (created on first start, git-ignored)
│   ├── access.log             # Every HTTP request with timing
│   └── app.log                # Auth events, assessment lifecycle, errors
├── static/
│   └── index.html             # Single-page frontend (Tailwind + vanilla JS)
├── caams.service              # systemd unit file
├── install_service.sh         # Production installer (systemd, TLS, env file)
├── seed.py                    # Database seeder
├── requirements.txt
└── README.md
```
