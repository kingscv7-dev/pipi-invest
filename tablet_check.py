import ipaddress
import socket
import urllib.request

PORT = 5002
PATH = "/dashboard"


def get_ips():
    out = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)
        for info in infos:
            value = info[4][0]
            try:
                ip = ipaddress.ip_address(value)
            except ValueError:
                continue
            if ip.version == 4 and ip.is_private and not ip.is_loopback and not ip.is_link_local:
                if value not in out:
                    out.append(value)
    except OSError:
        pass
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        value = s.getsockname()[0]
        if value not in out and value != "127.0.0.1":
            out.insert(0, value)
    except OSError:
        pass
    finally:
        s.close()
    return out


def http_ok(host):
    try:
        with urllib.request.urlopen(f"http://{host}:{PORT}{PATH}", timeout=2) as r:
            return 200 <= r.status < 400, r.status
    except Exception as e:
        return False, type(e).__name__

print("========================================")
print("PIPI VR7 TABLET CHECK")
print("========================================")
local_ok, detail = http_ok("127.0.0.1")
print("LOCAL SERVER:", "OK" if local_ok else f"FAIL ({detail})")

ips = get_ips()
if not ips:
    print("LAN IPv4: NOT FOUND")
else:
    for ip in ips:
        ok, d = http_ok(ip)
        print(f"LAN {ip}:{PORT}:", "OK" if ok else f"FAIL ({d})")
        print(f"URL: http://{ip}:{PORT}{PATH}")

print()
if local_ok:
    print("If LOCAL SERVER is OK but LAN is FAIL: run TABLET_SETUP.bat.")
    print("If LAN is OK but tablet cannot connect: check same Wi-Fi/LAN or AP isolation.")
else:
    print("Start PIPI VR7 with RUN.bat first.")
print("========================================")
