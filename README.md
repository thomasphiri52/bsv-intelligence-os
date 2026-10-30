# BSV Intelligence OS V1–V14 — Streamlit Edition

A multi-workspace business intelligence prototype for BSV Telecoms and client workspaces. This package is configured for Streamlit Community Cloud or a self-hosted Streamlit server.

## V14 — AI Business Intelligence foundation
- Executive dashboard with lead, pipeline, campaign and conversion indicators.
- Workspace-filtered CRM and campaign records.
- Transparent rule-based business advisor.
- Pipeline snapshot and stage-based forecasting view.
- CSV exports for leads and campaigns.
- Client portal summary and account password update.
- BSV platform-owner subscription overview and manual subscription record updates.
- Neon navy/cyan Streamlit theme.

**AI note:** The V14 advisor is rule-based decision support, not a connected generative AI model. Forecasting is a pipeline snapshot, not a predictive time-series model.

## Deploy on Streamlit Community Cloud
1. Extract the ZIP and push the complete project folder to a GitHub repository.
2. In Streamlit Community Cloud, select **Create app**.
3. Choose the repository and branch, then set **Main file path** to `app.py`.
4. Deploy. Streamlit installs packages from `requirements.txt`.
5. For a persistent production database, configure an external managed database before accepting live customer data.

The included SQLite database is created at first run. Streamlit Community Cloud local files may not provide durable storage across restarts/redeployments; use managed PostgreSQL for production. Do not commit secrets or a live database to GitHub.

## Run on Windows
1. Install Python 3.11 or newer.
2. Extract the ZIP.
3. Double-click `run_streamlit.bat`, or run:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL displayed by Streamlit (usually http://localhost:8501).

## Demo accounts
- BSV workspace: `admin@bsv.local`
- Demo client workspace: `client@demo.local`
- Initial password for both: `ChangeMe123!`

Change demo passwords immediately. These public demo credentials must never be used in a live deployment. For Streamlit Cloud, use a clean database or seed controlled demo data; do not deploy with real customer information in SQLite.

## Existing Flask edition
The previous Flask application is preserved as `legacy_flask_app.py` for reference. The deployment entry point for this package is now `app.py` (Streamlit).

## Important prototype and security limitations
- This is a development prototype, not production-ready SaaS software.
- The seeded platform administrator identity is a prototype shortcut; implement a secure platform-owner role and enforce authorization server-side before production.
- Authentication is basic session-state login. Streamlit session state is not a replacement for a full identity provider, MFA, account recovery, rate limiting or hardened session management.
- No payment gateway, automated invoicing, subscription collection or external ad integrations are connected.
- Workspace data is filtered by tenant in application queries, but this has not undergone an independent tenant-isolation security audit.
- Use managed PostgreSQL, HTTPS, secrets management, backups and restore testing, monitoring, privacy notices and POPIA review before storing real client or personal data.
- Validate all workflows and perform a security review before public deployment.

## Files
- `app.py` — Streamlit application entry point.
- `requirements.txt` — Streamlit and pandas dependencies.
- `legacy_flask_app.py` — previous Flask edition for reference.
- `run_streamlit.bat` — Windows launcher.
- `.streamlit/config.toml` — dark neon theme and server configuration.
- `Procfile` — generic hosted process declaration.
