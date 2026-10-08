PIPI INVEST v4.2 - Railway diagnostic build

Required Railway variable:
  PIPI_PASSWORD = your login password

Optional compatibility fallback:
  APP_PASSWORD = accepted only if PIPI_PASSWORD is empty

Recommended:
  PIPI_DATA_DIR = /data

After deployment, open:
  https://YOUR-DOMAIN/auth-status

Expected JSON:
  "password_status": "SET"
  "password_source": "PIPI_PASSWORD"
  "version": "4.2"

The password value is never returned or logged.
