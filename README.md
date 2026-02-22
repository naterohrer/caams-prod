# CAAMS — Compliance and Auditing Made Simple

A self-hosted tool for mapping your security tool stack against compliance frameworks (CIS Controls, NIST CSF, SOC 2, PCI DSS, HIPAA) and generating auditor-ready gap analysis reports.

<img width="1294" height="819" alt="caams-prod-ss" src="https://github.com/user-attachments/assets/54bf001f-5191-42f4-947a-29cf68cc0866" />

---

## What it does

1. You select the security tools your organisation uses
2. CAAMS maps them against your chosen compliance framework
3. You get a coverage report showing which controls are met, partially met, or missing — with evidence links, notes, and owner assignments per control
4. Export to XLSX or PDF for auditors

---

## Requirements

- A Linux server with **systemd** (Ubuntu 22.04+ recommended)
- **Python 3.11+** installed
- A TLS certificate (self-signed or CA-signed)
- Root / sudo access for the install

---

## Production Install

### 1. Run the installer

From the root of the CAAMS folder:

```bash
sudo bash install_service.sh
```

The installer will:
- Create a dedicated `caams` system account
- Install all dependencies into an isolated Python virtualenv
- Generate a secure secret key and store it in `/etc/caams.env`
- Auto-generate a self-signed TLS certificate if none is present
- Seed the database with framework and tool data
- Register and start CAAMS as a systemd service (auto-starts on reboot)

Using a CA-signed certificate? Place your cert.pem and key.pem in /opt/caams/certs/ before running the installer and it will use them as-is.

### 2. Verify it's running

```bash
sudo systemctl status caams
```

You should see `active (running)`. If not:

```bash
sudo journalctl -u caams -f
```

### 4. Open the app

Navigate to `https://<your-server-hostname>:8443` in a browser.

On first visit you'll be prompted to create your admin account. Do this immediately — the setup screen is disabled once any account exists.

---

## Using CAAMS

### Create an assessment

1. Enter an assessment name (e.g. `Q1 2026 — CIS Review`)
2. Select a compliance framework
3. Check the tools deployed in your environment
4. Click **Analyze Coverage**

### Reading results

| Badge | Meaning |
|---|---|
| Green / Covered | All required controls are satisfied by your tools |
| Amber / Partial | Some controls are met but gaps remain |
| Red / Not Covered | No controls in this area are satisfied |

Click any row to open the detail panel — add notes, paste an evidence link (SharePoint, Confluence, Google Drive, etc.), assign an owner, or set a manual override with a justification.

### Exporting

Use the **Export** button to download:
- **XLSX** — four-sheet workbook (summary, full coverage report, evidence checklist, recommendations). Ready to hand to an auditor.
- **PDF** — branded report with cover page, executive summary, and colour-coded control table.

### Tool recommendations

Below the results table, **Tool Recommendations** shows which tools (not yet in your assessment) would close the most gaps — ranked by number of controls they would cover.

---

## Common Admin Tasks

**Restart the service after a config change:**
```bash
sudo systemctl restart caams
```

**View live logs:**
```bash
sudo journalctl -u caams -f
```

**View application events (logins, overrides, errors):**
```bash
sudo tail -f /opt/caams/logs/app.log
```

**Add or manage users** (admin only — also available via the UI):
```bash
# List users
curl -k https://localhost:8443/auth/users \
  -H "Authorization: Bearer <your-token>"

# Create a user
curl -k -X POST https://localhost:8443/auth/users \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "SecurePass1!", "role": "contributor"}'
```

User roles: `admin` (full access), `contributor` (create/edit assessments), `viewer` (read-only).

**Swap in a new TLS certificate:**
```bash
sudo cp your-cert.pem /opt/caams/certs/cert.pem
sudo cp your-key.pem  /opt/caams/certs/key.pem
sudo systemctl restart caams
```

---

## Supported Frameworks

| Framework | Version |
|---|---|
| CIS Controls | v8 |
| NIST Cybersecurity Framework | v2.0 |
| SOC 2 Trust Services Criteria | 2017 |
| PCI DSS | v4.0 |
| HIPAA Security Rule | 45 CFR Part 164 |

---

## For Developers

Full technical documentation — API reference, adding custom frameworks, project structure, database details, and development setup — is in [README-technical.md](README-technical.md).
