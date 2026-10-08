PIPI INVEST v4.0 - Cloud/PWA build

GOAL
- PC does NOT need to stay on.
- iPhone, Galaxy Tab, and PC all use one cloud DB.
- Install from Safari/Chrome as an app icon (PWA).

CLOUD REQUIREMENTS
1) A host that can run this Dockerfile.
2) A persistent disk/volume mounted at /data.
3) Environment variables:
   PIPI_PASSWORD = your login password
   PIPI_SECRET_KEY = long random secret
   PIPI_HTTPS = 1
   PIPI_CLOUD = 1
   PIPI_DATA_DIR = /data
4) Start command is already in Dockerfile. Use one web instance / one Gunicorn worker with SQLite.

IMPORTANT
- Persistent /data is mandatory. Without it, vr7.db can disappear on redeploy/restart.
- Do not publicly deploy without PIPI_PASSWORD.
- Download DB Backup periodically from the app.

MOVE EXISTING DATA
- Your current vr7.db can be copied to /data/vr7.db on the cloud volume before first production use.
- If your host does not allow uploading a file into the volume, start with a blank DB or use a host/admin method to copy the DB.

INSTALL ON iPHONE
1) Open your HTTPS PIPI URL in Safari.
2) Share button -> Add to Home Screen.
3) Launch PIPI INVEST from the new icon.

INSTALL ON GALAXY TAB
1) Open your HTTPS PIPI URL in Chrome.
2) Chrome menu -> Add to Home screen / Install app.
3) Launch PIPI INVEST from the icon.

LOCAL WINDOWS
- RUN.bat / STOP.bat still work for local use.
- Local mode uses the DB inside this folder unless PIPI_DATA_DIR is set.
