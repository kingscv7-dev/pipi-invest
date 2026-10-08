PIPI VR7 v3.8

RUN.bat            Start PIPI VR7 (hidden CMD)
STOP.bat           Stop PIPI VR7
DIAG.bat           Diagnostic start with visible CMD
TABLET_ADDRESS.bat Show LAN address for Galaxy Tab / tablet access

Local PC: http://127.0.0.1:5002/dashboard
Tablet: use the address shown by TABLET_ADDRESS.bat

Data migration:
Copy your existing vr7.db into this folder before starting.

v3.8 cleanup:
- Removed corrupted / garbled launcher filenames.
- All BAT/VBS filenames are ASCII only.
- All command-window text is ASCII only.
- Browser UI remains Korean.

--- Tablet access (v3.8) ---
1. Run RUN.bat on the PC.
2. Run TABLET_SETUP.bat once and approve the Windows administrator prompt.
3. Run TABLET_ADDRESS.bat.
4. Open the PRIMARY URL on the Galaxy Tab Chrome browser.
5. PC and tablet must be connected to the same Wi-Fi/LAN.
6. If it still fails, run TABLET_CHECK.bat.


[v3.8 tablet fix]
TABLET_ADDRESS.bat now uses tablet_address.py instead of inline PowerShell.
Run order: RUN.bat -> TABLET_SETUP.bat (once) -> TABLET_ADDRESS.bat.


STOP behavior (v3.8)
- STOP.bat / STOP_HIDDEN.vbs stops the PIPI VR7 server.
- It first uses vr7.pid, then falls back to the process listening on TCP port 5002.
- The Chrome/Samsung Internet tab is NOT closed automatically. The old page may remain visible or animate from cached JavaScript; refresh or click a menu after stopping to confirm the server is offline.
