#!/usr/bin/env python3
"""Fetch-ingest SSRF URL guard.

Enforces the deny-list codified in SKILL.md for the fetch-ingest bridge.
Usage:  check_url.py <url>
Exit 0 = SAFE to pass to the fetch tool; exit 1 = BLOCKED (reason printed).
stdlib only, run with any python3.
"""
import ipaddress
import socket
import sys
from urllib.parse import urlparse

DENY_NETS = [
    ipaddress.ip_network(n) for n in [
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "0.0.0.0/8",
        "::1/128",
        "::/128",
        "fe80::/10",
        "fc00::/7",
    ]
]

DENY_HOST_SUFFIXES = (".local", ".internal", ".lan", ".home", ".localhost")
DENY_HOST_EXACT = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
    "instance-data",
    "instance-data.ec2.internal",
}


def _blocked(ip: ipaddress._BaseAddress) -> bool:
    return any(ip in net for net in DENY_NETS)


def check(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "unparseable URL"
    if parsed.scheme not in ("http", "https"):
        return False, f"scheme '{parsed.scheme}' is not http(s)"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "no host in URL"
    if host in DENY_HOST_EXACT or host.endswith(DENY_HOST_SUFFIXES):
        return False, f"hostname '{host}' is on the deny-list"
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}"
    addrs = sorted({info[4][0] for info in infos})
    if not addrs:
        return False, "host resolved to no addresses"
    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])
        except ValueError:
            continue
        if _blocked(ip):
            return False, f"resolved IP {addr} is in a denied range"
    return True, f"SAFE -> {addrs}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: check_url.py <url>")
        sys.exit(2)
    ok, reason = check(sys.argv[1])
    print(reason)
    sys.exit(0 if ok else 1)
