import ipaddress
import socket
import urllib.request

PORT = 5002
PATH = "/dashboard"


def clean_ip(value):
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return None
    if ip.version != 4 or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
        return None
    if not ip.is_private:
        return None
    return str(ip)


def primary_ip():
    # Ask Windows which local interface it would use for an outbound route.
    # No data is sent; UDP connect only selects a route/interface.
    for target in [("8.8.8.8", 80), ("1.1.1.1", 80), ("192.0.2.1", 80)]:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(target)
            ip = clean_ip(s.getsockname()[0])
            if ip:
                return ip
        except OSError:
            pass
        finally:
            s.close()
    return None


def all_private_ips():
    found = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM)
        for info in infos:
            ip = clean_ip(info[4][0])
            if ip and ip not in found:
                found.append(ip)
    except OSError:
        pass
    p = primary_ip()
    if p and p not in found:
        found.insert(0, p)
    return found


def local_server_ok():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{PATH}", timeout=2) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


if __name__ == "__main__":
    ips = all_private_ips()
    p = primary_ip()
    if p and p in ips:
        ips.remove(p)
        ips.insert(0, p)

    print("========================================")
    print("PIPI VR7 TABLET URL")
    print("========================================")
    print()
    print("LOCAL SERVER:", "OK" if local_server_ok() else "NOT RUNNING")
    print()
    if ips:
        print("PRIMARY:")
        print(f"http://{ips[0]}:{PORT}{PATH}")
        if len(ips) > 1:
            print()
            print("OTHER PRIVATE IPv4 ADDRESSES:")
            for ip in ips[1:]:
                print(f"http://{ip}:{PORT}{PATH}")
    else:
        print("No private LAN IPv4 address found.")
    print()
    print("PC and tablet must be on the same Wi-Fi/LAN.")
    print("If LOCAL SERVER is OK but the tablet cannot open the URL,")
    print("run TABLET_SETUP.bat once as administrator.")
    print("========================================")
