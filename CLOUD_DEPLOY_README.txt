PIPI INVEST v4.1 - Railway

Required Railway Variable:
PIPI_PASSWORD = your login password

Required Railway Volume mount path:
/data

PIPI_DATA_DIR and PIPI_CLOUD are already set by Dockerfile.
Do not upload vr7.db to GitHub. Restore it from PIPI DB Restore after deployment.

Cloud security behavior:
- No PIPI_PASSWORD: app data is blocked; setup-required page is shown.
- PIPI_PASSWORD set: every app page requires login.
- Changing PIPI_PASSWORD invalidates previous login sessions.
