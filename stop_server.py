from __future__ import annotations
import os, re, subprocess, time
from pathlib import Path

BASE = Path(__file__).resolve().parent
PID_FILE = BASE / 'vr7.pid'
PORT = 5002


def kill_pid(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        r = subprocess.run(
            ['taskkill', '/PID', str(pid), '/T', '/F'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def pid_alive(pid: int) -> bool:
    try:
        r = subprocess.run(
            ['tasklist', '/FI', f'PID eq {pid}', '/NH'],
            capture_output=True,
            text=True,
            errors='ignore',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            check=False,
        )
        return bool(re.search(rf'\b{pid}\b', r.stdout or ''))
    except Exception:
        return False


def listener_pids(port: int) -> set[int]:
    out: set[int] = set()
    try:
        r = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'],
            capture_output=True,
            text=True,
            errors='ignore',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            check=False,
        )
        # Windows output example:
        # TCP    0.0.0.0:5002    0.0.0.0:0    LISTENING    1234
        for line in (r.stdout or '').splitlines():
            if 'LISTEN' not in line.upper():
                continue
            cols=line.split()
            if len(cols) < 5:
                continue
            local=cols[1]
            if not local.endswith(f':{port}'):
                continue
            try:
                out.add(int(cols[-1]))
            except ValueError:
                pass
    except Exception:
        pass
    return out


def main():
    killed=False
    saved_pid=None
    try:
        if PID_FILE.exists():
            raw=PID_FILE.read_text(encoding='ascii',errors='ignore').strip()
            if raw.isdigit():
                saved_pid=int(raw)
                if pid_alive(saved_pid):
                    killed=kill_pid(saved_pid) or killed
                    time.sleep(0.2)
    except Exception:
        pass

    # Fallback for old/stale copies: if PIPI is still listening on its dedicated
    # port, stop the listener as well. This also catches a server started from an
    # older version folder, whose PID file lives elsewhere.
    for pid in listener_pids(PORT):
        if saved_pid is None or pid != saved_pid or pid_alive(pid):
            killed=kill_pid(pid) or killed

    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == '__main__':
    main()
