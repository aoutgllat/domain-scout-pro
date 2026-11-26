#!/usr/bin/env python3
"""
Domain Scout Pro v1.7.0 — Clickable domains
-----------------------------------
Domains in the results table are now clickable:
  * Double-click a domain (or a "Redirects to" value) to open it
    in Google Chrome — Chrome is tried first, the default browser
    is the fallback if Chrome is not installed.
  * Right-click a row for: Open in Chrome, Open redirect target,
    Copy domain, Copy URL, Copy redirect target, Copy email, Copy row.
  * Ctrl+C copies the selected domain(s), one per line.
  * Hovering a domain / redirect cell shows a hand cursor.
  * Enter on a selected row also opens it in Chrome.
  Copy = copy to the clipboard, then paste it anywhere (WhatsApp,
  Excel, a browser address bar, ...). No auto-posting, no auto-send.

Domain Scout Pro v1.6.0 — Pro Redesign
-----------------------------------
Developed by Outgllat — https://ko-fi.com/outgllat
(Change KO_FI_URL below if your Ko-fi handle is different.)
Check a list of domains and tell you, per domain, whether it is:

  FOR SALE    — listed / parked for sale (Sedo, Afternic, GoDaddy,
                Dan/Atom, HugeDomains, Bodis, ParkingCrew, etc.)
  DEVELOPED   — live website with real content
  PARKED      — DNS / parking page, no clear for-sale wording
  EXPIRED     — WHOIS expiry date has passed, or in
                redemption / pendingDelete
  AVAILABLE   — WHOIS says "no match" / not registered
  UNKNOWN     — could not decide (no DNS, blocked, timeout, etc.)

How it checks each domain (stdlib only, no dnspython):
  1. Normalise + syntax check.
  2. DNS — A via socket, NS / CNAME via pure-Python UDP DNS
     (8.8.8.8, then 1.1.1.1), fallback DNS-over-HTTPS, then nslookup.
     Parking nameservers are a strong for-sale signal.
  3. WHOIS — port 43. Asks whois.iana.org for the TLD server,
     follows the referral to the registrar WHOIS, parses
     registrar / creation / expiry / status / nameservers.
     For .com/.net falls back to whois.verisign-grs.com.
  4. HTTP — tries https://domain then https://www.domain then
     http://, follows redirects MANUALLY (up to 6 hops) and records
     the chain. A same-domain www redirect is normal; a cross-domain
     redirect_to (final domain differs) is the real owner site.
     Reads title + first ~120 KB. Title / body / final URL are
     scanned for sale + parking keywords and marketplace names.
  5. Emails (v1.3.0, outbound) — extracts emails actually found on
     the homepage, then WHOIS, then /contact-us, /contact,
     /about-us, /about. Junk / privacy / noreply addresses are
     dropped. If none is found and the domain has MX, it shows one
     clearly-marked guess "info@domain (?)" — (?) = unverified.
     If no email exists but a contact page does, its URL is kept
     (contact_url, in the CSV) so you can use the form instead.
  6. Classify — expiry first, then available, then for-sale,
     then parked, then developed, else unknown.

  v1.6.0 PRO REDESIGN — same checker, same live radar, new pro UI:
  slim header, top action bar, radar + latest-result card, coloured
  stat cards, pro table, input panel below the table, footer.
  Window stays 1280x920 so the bottom Check / Stop stay on screen.

  v1.5.0 LIVE RADAR (Flightradar style) — every domain is a live
  target on the scope: it flies in as a white pulsing blip while
  it is being checked, leaves a trail behind it, flashes bright
  every time the sweep passes over it, and pings (expanding ring)
  the moment its result lands, turning the colour of its status.
  Hover a blip for its domain + status, click it to jump to its
  row. Pause / sweep speed are on the radar panel.
  NOTE: it cannot tell you which OTHER domains redirect TO this
  one — that needs a backlink / redirect index, not DNS + HTTP.
  What it shows is the forward direction: where THIS domain sends
  its visitors.

What it does NOT do:
  * It cannot see private marketplace listings. A domain can be
    listed on Afternic / Sedo / Dan with a lander that this tool
    cannot distinguish from a normal parked page, and a domain
    listed only inside a marketplace account (no lander) will
    look Developed / Parked. Treat FOR SALE as "landed for sale",
    not "listed everywhere".
  * WHOIS servers rate-limit. Default 4 workers; if you run
    200+ domains at 8 workers you will get WHOIS timeouts.
    Lower workers / raise timeout if that happens.
  * Some sites block bots / Cloudflare. A 403 / timeout does not
    mean the domain is not developed — check the Note column.
  * Expiry dates in WHOIS are the registrar's dates. A domain
    can be past expiry but still in grace / redemption for
    30-45 days — the tool flags the status string too.

Run with:
    python3 domain_checker_pro.py
No extra dependencies — stdlib only. Tkinter GUI, dark pro theme,
same button system as SMTP Tester / Mailbox Checker Pro.

Bulk format: one domain per line. Paste, or Load CSV / TXT.
CSV: any cell that looks like a domain is picked up.
URLs are accepted too — http://, www., trailing /path are stripped.
"""

import csv
import json
import math
import os
import webbrowser
import queue
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, scrolledtext, ttk

# --- Branding — change KO_FI_URL here if your Ko-fi handle differs ---
APP_NAME = "Domain Scout Pro"
APP_VERSION = "1.7.0"
DEVELOPER = "Outgllat"
KO_FI_URL = "https://ko-fi.com/outgllat"  # <-- your Ko-fi page; update if different

BG = "#0e1013"
PANEL = "#181b21"
PANEL_ALT = "#22262e"
PANEL_HOVER = "#2c313b"
BORDER = "#2a2f38"
FG = "#f2f4f7"
MUTED = "#9aa3af"
ACCENT = "#ff5a3c"          # Outgllat / Predator thermal orange-red
ACCENT_HOVER = "#ff6f52"
ACCENT_PRESSED = "#e04a2f"
KOFI = "#ff5e5b"            # Ko-fi brand red
KOFI_HOVER = "#ff7572"
KOFI_PRESSED = "#e04a47"
OK = "#3ddc84"
WARN = "#ffc857"
ERR = "#ff5c66"
PURPLE = "#b389ff"
DISABLED_BG = "#22262e"
DISABLED_FG = "#6b7280"
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO = ("Consolas", 9)
FONT_HEADER = ("Segoe UI", 18, "bold")
FONT_SUBTITLE = ("Segoe UI", 9)
FONT_STAT_NUM = ("Segoe UI", 14, "bold")
FONT_STAT_LABEL = ("Segoe UI", 8, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_SECTION = ("Segoe UI", 9, "bold")

DOMAIN_RE = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
    r"(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,63}$"
)
DOMAIN_FIND_RE = re.compile(
    r"\b(?:https?://)?(?:www\.)?([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,63})\b"
)

# --- Open in Chrome (v1.7.0, clickable domains) -------------------------
# Chrome first, default browser as fallback. Works on Windows, macOS
# and Linux. Returns (True, "") on success, (False, reason) otherwise.
def find_chrome_path():
    """Return the Chrome executable path, or None if not found."""
    candidates = []
    if os.name == "nt":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        candidates = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
                      "/usr/bin/chromium", "/usr/bin/chromium-browser",
                      "/snap/bin/chromium"]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    # Also try PATH (chrome / google-chrome / chromium)
    import shutil
    for name in ("google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None

def open_in_chrome(url):
    """Open a URL in Google Chrome if it is installed, else in the
    default browser. `url` may be a bare domain — https:// is added."""
    if not url:
        return False, "Nothing to open"
    url = str(url).strip()
    if not url:
        return False, "Nothing to open"
    if "://" not in url:
        url = "https://" + url.lstrip("/")
    chrome = find_chrome_path()
    if chrome:
        try:
            subprocess.Popen([chrome, url])
            return True, ""
        except Exception:
            pass  # fall through to the default browser
    for browser_name in ("chrome", "google-chrome", "chromium"):
        try:
            webbrowser.get(browser_name).open(url)
            return True, ""
        except Exception:
            continue
    try:
        webbrowser.open(url)
        return True, ""
    except Exception as e:
        return False, str(e)

# --- Email finder (v1.3.0, for outbound) ---------------------------------
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Mailbox names that are never a real person to contact for outbound
JUNK_EMAIL_LOCAL = {
    "noreply", "no-reply", "donotreply", "do-not-reply", "postmaster",
    "abuse", "dmarc", "bounce", "bounces", "mailer-daemon", "webmaster",
    "hostmaster", "wordpress", "wix", "squarespace", "shopify",
}
PRIVACY_EMAIL_HINTS = (
    "redact", "privacy", "proxy", "whoisguard", "domainsbyproxy",
    "withheld", "protected", "registrar", "contactprivacy",
)

def extract_emails(text, domain=None):
    """Pull real-looking emails out of HTML / WHOIS text.
    De-obfuscates 'name [at] domain [dot] com' and 'name (at) domain'.
    Same-domain emails first, junk / privacy / image-file emails dropped.
    Never invents an address — only returns what was actually found."""
    if not text:
        return []
    s = text
    # De-obfuscate common anti-scrape spellings
    s = re.sub(r"\s*\[at\]\s*|\s*\(at\)\s*|\s+at\s+", "@", s, flags=re.I)
    s = re.sub(r"\s*\[dot\]\s*|\s*\(dot\)\s*|\s+dot\s+", ".", s, flags=re.I)
    found = []
    for m in EMAIL_RE.finditer(s):
        e = m.group(0).lower().strip(".,;:\"'<>")
        if not e or "@" not in e:
            continue
        local, host = e.rsplit("@", 1)
        if local in JUNK_EMAIL_LOCAL:
            continue
        if host.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
                          ".js", ".css", ".woff", ".woff2")):
            continue
        if any(h in e for h in PRIVACY_EMAIL_HINTS):
            continue
        if host in ("example.com", "example.org", "example.net",
                    "s.w.org", "w.org", "domain.com"):
            continue
        if e not in found:
            found.append(e)
    if domain:
        d = domain.lower().lstrip("www.")
        # Same-domain (or sub-domain of it) first — most likely the owner
        found.sort(key=lambda e: (0 if e.rsplit("@", 1)[-1] == d
                                  or e.rsplit("@", 1)[-1].endswith("." + d)
                                  else 1, e))
    return found[:5]

# --- Sale / parking signals -------------------------------------------------
PARKING_NS = [
    "sedoparking", "sedo.", "afternic", "parkingcrew", "bodis",
    "hugedomains", "dan.com", "atom.com", "namecheap", "godaddy",
    "parklogic", "above.com", "trafficz", "voodoo.com", "domainparking",
    "uniregistry", "epik", "squadhelp", "atom", "porkbun",
]
SALE_KEYWORDS = [
    "domain for sale", "domain name for sale", "this domain is for sale",
    "buy this domain", "buy this domain name", "domain is for sale",
    "this domain is available", "make an offer", "make offer",
    "for sale by owner", "premium domain for sale", "domain for sale!",
    "this domain may be for sale", "interested in this domain",
    "purchase this domain", "get this domain", "domain available for purchase",
    "is for sale", "for sale —", "for sale |",
]
PARKING_KEYWORDS = [
    # NOTE v1.2.0: bare "parked" / "parking" were removed — a real
    # developed site can be about parking lots / parking services
    # (columbuspowercleaning.com: "Parking Lot Sweeping") and was
    # wrongly flagged Parked. Only specific parking-page phrases count.
    "sedo", "afternic", "bodis", "parkingcrew",
    "hugedomains", "this domain has been registered", "domain parking",
    "this web page is parked", "parked domain", "domain is parked",
    "under construction", "coming soon",
]
MARKETPLACES = [
    "sedo.com", "afternic.com", "dan.com", "atom.com", "godaddy.com",
    "hugedomains.com", "namecheap.com", "squadhelp.com", "bodis.com",
    "parkingcrew", "uniregistry", "epik.com",
]

# ---------------------------------------------------------------------
# Tooltip
# ---------------------------------------------------------------------
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self._tip = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._hide()
        self._after_id = self.widget.after(600, self._show)

    def _show(self):
        if self._tip is not None:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tip, text=self.text, bg="#111218", fg="#eef0f4",
                         font=FONT_SMALL, padx=10, pady=6, relief="solid",
                         borderwidth=1, highlightbackground=BORDER)
        label.pack()
        self._tip = tip

    def _hide(self, _event=None):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


# ---------------------------------------------------------------------
# Domain normalisation
# ---------------------------------------------------------------------
def normalize_domain(raw):
    s = (raw or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0]
    s = s.split(":")[0]
    s = s.lstrip("www.").rstrip(".").strip()
    # Strip a leading www. again after cleaning, and any @ user part
    if "@" in s:
        s = s.split("@")[-1]
    return s

def extract_domains(text):
    """Pull domains out of pasted text / CSV content, deduped, in order."""
    seen = set()
    out = []
    for line in (text or "").splitlines():
        for m in DOMAIN_FIND_RE.finditer(line):
            d = normalize_domain(m.group(0))
            if DOMAIN_RE.match(d) and d not in seen:
                seen.add(d)
                out.append(d)
        # Also catch a bare domain on its own line (no www/http)
        bare = normalize_domain(line.strip().strip(",;\"'"))
        if DOMAIN_RE.match(bare) and bare not in seen:
            seen.add(bare)
            out.append(bare)
    return out


# ---------------------------------------------------------------------
# DNS — pure-stdlib UDP + DoH + nslookup
# ---------------------------------------------------------------------
def _encode_dns_name(name):
    out = b""
    for part in name.rstrip(".").split("."):
        if not part:
            continue
        b = part.encode("idna")
        out += struct.pack("B", len(b)) + b
    return out + b"\x00"

def _decode_dns_name(msg, offset):
    labels = []
    jumped = False
    next_offset = offset
    seen = set()
    while True:
        if offset >= len(msg):
            break
        length = msg[offset]
        if length == 0:
            offset += 1
            if not jumped:
                next_offset = offset
            break
        if (length & 0xC0) == 0xC0:
            if offset + 1 >= len(msg):
                break
            pointer = ((length & 0x3F) << 8) | msg[offset + 1]
            if not jumped:
                next_offset = offset + 2
            jumped = True
            if pointer in seen:
                break
            seen.add(pointer)
            offset = pointer
            continue
        offset += 1
        if offset + length > len(msg):
            break
        try:
            labels.append(msg[offset:offset + length].decode("idna"))
        except Exception:
            labels.append(msg[offset:offset + length].decode("utf-8", "ignore"))
        offset += length
        if not jumped:
            next_offset = offset
    return ".".join(labels), next_offset

def _query_dns_via_server(domain, qtype, dns_server, timeout=5):
    import random
    txid = random.randint(0, 0xFFFF)
    header = struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0)
    question = _encode_dns_name(domain) + struct.pack(">HH", qtype, 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(header + question, (dns_server, 53))
        data, _ = sock.recvfrom(8192)
    finally:
        sock.close()
    if len(data) < 12:
        return [], False
    (_rxid, _flags, qdcount, ancount, _ns, _ar) = struct.unpack(">HHHHHH", data[:12])
    if _rxid != txid:
        return [], False
    rcode = _flags & 0x000F
    nxdomain = (rcode == 3)
    offset = 12
    for _ in range(qdcount):
        _n, offset = _decode_dns_name(data, offset)
        offset += 4
    results = []
    for _ in range(ancount):
        _n, offset = _decode_dns_name(data, offset)
        if offset + 10 > len(data):
            break
        (rtype, _rc, _ttl, rdlen) = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        rdata_start = offset
        if rtype == qtype and offset + rdlen <= len(data):
            if qtype == 1 and rdlen == 4:  # A
                results.append(socket.inet_ntoa(data[offset:offset + 4]))
            elif qtype in (2, 5):  # NS / CNAME
                host, _ = _decode_dns_name(data, offset)
                if host:
                    results.append(host.rstrip("."))
            elif qtype == 15 and rdlen >= 3:  # MX
                host, _ = _decode_dns_name(data, offset + 2)
                if host:
                    results.append(host.rstrip("."))
        offset = rdata_start + rdlen
    return results, nxdomain

def _query_dns_via_doh(domain, qtype_name, timeout=5):
    # Try Google first, then Cloudflare — NS answers in particular
    # sometimes come back empty from one of them on the first try.
    templates = [
        "https://dns.google/resolve?name={}&type={}",
        "https://cloudflare-dns.com/dns-query?name={}&type={}",
    ]
    for template in templates:
        url = template.format(urllib.parse.quote(domain), qtype_name)
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "application/dns-json",
                "User-Agent": "Domain-Scout-Pro/1.4"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception:
            continue
        if data.get("Status") == 3:
            return [], True
        out = []
        for ans in data.get("Answer", []) or []:
            d = str(ans.get("data", "")).strip().rstrip(".")
            if d:
                # MX answers look like "10 mail.example.com."
                if qtype_name == "MX":
                    parts = d.split(None, 1)
                    if len(parts) == 2:
                        d = parts[1]
                out.append(d)
        if out:
            return out, False
    return [], False

def _dns_via_nslookup(domain, qtype_name, timeout=8):
    try:
        out = subprocess.run(
            ["nslookup", f"-type={qtype_name}", domain],
            capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return []
    res = []
    for line in out.splitlines():
        line = line.strip()
        m = re.search(r"(?:nameserver|name server)\s*=\s*(\S+)", line, re.I)
        if m:
            res.append(m.group(1).rstrip("."))
        m2 = re.search(r"canonical name\s*=\s*(\S+)", line, re.I)
        if m2:
            res.append(m2.group(1).rstrip("."))
        m3 = re.search(r"Address:\s*(\d+\.\d+\.\d+\.\d+)", line)
        if qtype_name == "A" and m3:
            res.append(m3.group(1))
    return res

def dns_lookup(domain, qtype, qtype_name, timeout=5):
    """Return (values, nxdomain_or_None). Tries UDP, then DoH, then nslookup."""
    for server in ("8.8.8.8", "1.1.1.1"):
        try:
            vals, nx = _query_dns_via_server(domain, qtype, server, timeout=timeout)
            if vals or nx:
                return vals, nx
        except Exception:
            continue
    vals, nx = _query_dns_via_doh(domain, qtype_name, timeout=timeout)
    if vals or nx:
        return vals, nx
    # DoH answered empty (not NXDOMAIN) — don't trust it yet. Try
    # nslookup, then one more DoH attempt before giving up.
    vals = _dns_via_nslookup(domain, qtype_name)
    if vals:
        return vals, None
    vals, nx = _query_dns_via_doh(domain, qtype_name, timeout=timeout)
    return vals, nx

def get_dns_info(domain, timeout=5):
    info = {"a": [], "ns": [], "cname": [], "mx": [], "nxdomain": False}
    # A via socket first (fast, local resolver)
    try:
        _hn, _aliases, ips = socket.gethostbyname_ex(domain)
        info["a"] = sorted(set(ips))
    except Exception:
        pass
    a_vals, a_nx = dns_lookup(domain, 1, "A", timeout=timeout)
    if a_vals:
        info["a"] = sorted(set(info["a"]) | set(a_vals))
    if a_nx:
        info["nxdomain"] = True
        # NXDOMAIN wins: some sandboxed / ISP resolvers answer EVERY
        # name with a fake IP via socket — discard it, or fake domains
        # would look live and Available would never trigger.
        info["a"] = []
    ns_vals, _ = dns_lookup(domain, 2, "NS", timeout=timeout)
    if ns_vals:
        info["ns"] = sorted(set(ns_vals))
    cname_vals, _ = dns_lookup(domain, 5, "CNAME", timeout=timeout)
    if cname_vals:
        info["cname"] = sorted(set(cname_vals))
    # MX is a useful "is this a real business domain?" hint, cheap to add
    try:
        mx_vals, _ = dns_lookup(domain, 15, "MX", timeout=timeout)
        # Drop junk answers like "0" / "." (empty MX, e.g. "0 .")
        mx_vals = [m.strip().rstrip(".") for m in mx_vals
                   if m.strip().rstrip(".") and "." in m.strip().rstrip(".")]
        if mx_vals:
            info["mx"] = sorted(set(mx_vals))
    except Exception:
        pass
    if not info["a"] and info["nxdomain"]:
        info["nxdomain"] = True
    return info


# ---------------------------------------------------------------------
# WHOIS — port 43
# ---------------------------------------------------------------------
def _whois_query(server, query, timeout=10):
    sock = socket.create_connection((server, 43), timeout=timeout)
    try:
        sock.sendall((query + "\r\n").encode("utf-8", "ignore"))
        chunks = []
        sock.settimeout(timeout)
        while True:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                break
            if not data:
                break
            chunks.append(data)
            if sum(len(c) for c in chunks) > 200_000:
                break
    finally:
        sock.close()
    return b"".join(chunks).decode("utf-8", "ignore")

_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%b-%Y", "%d-%b-%Y %H:%M:%S %Z",
    "%Y.%m.%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S",
    "%a %b %d %H:%M:%S %Z %Y", "%d %b %Y",
]

def _parse_whois_date(raw):
    if not raw:
        return None
    s = raw.strip().strip('"').split()[0] if "T" not in raw else raw.strip()
    s = raw.strip()
    # Most common: 2027-01-15T12:00:00Z or 15-Jan-2027
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except Exception:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            tzinfo=timezone.utc)
        except Exception:
            return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None

def _first_whois_value(text, keys):
    for key in keys:
        m = re.search(rf"^{re.escape(key)}\s*:\s*(.+)$", text, re.I | re.M)
        if m:
            v = m.group(1).strip()
            if v:
                return v
    return ""

def get_whois(domain, timeout=10):
    """Return dict: registrar, created, expires, status[], nameservers[], raw_found, error."""
    out = {"registrar": "", "created": None, "expires": None,
           "created_raw": "", "expires_raw": "", "status": [],
           "nameservers": [], "raw_found": False, "error": "", "emails": []}
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    try:
        # Step 1: IANA for the TLD server
        text = ""
        try:
            text = _whois_query("whois.iana.org", tld, timeout=timeout)
        except Exception as e:
            out["error"] = f"IANA WHOIS failed: {e}"
        server = ""
        m = re.search(r"^whois:\s*(\S+)", text, re.I | re.M)
        if m:
            server = m.group(1).strip()
        if tld in ("com", "net") and not server:
            server = "whois.verisign-grs.com"
        if not server:
            out["error"] = out["error"] or "No WHOIS server for this TLD"
            return out
        # Step 2: TLD server
        try:
            text = _whois_query(server, domain, timeout=timeout)
            if tld in ("com", "net"):
                text = _whois_query(server, "=" + domain, timeout=timeout)
        except Exception as e:
            out["error"] = f"WHOIS {server} failed: {e}"
            return out
        # Step 3: follow referral if present
        m2 = re.search(r"Whois Server:\s*(\S+)", text, re.I)
        if m2 and m2.group(1).lower() != server.lower():
            try:
                text2 = _whois_query(m2.group(1).strip(), domain, timeout=timeout)
                if text2 and "No match" not in text2[:500]:
                    text = text2
            except Exception:
                pass
        low = text.lower()
        if ("no match" in low[:800] or "not found" in low[:800]
                or "no data found" in low[:800] or "domain not found" in low[:800]):
            out["raw_found"] = False
            return out
        out["raw_found"] = True
        out["registrar"] = _first_whois_value(
            text, ["Registrar", "Sponsoring Registrar", "registrar"])
        out["created_raw"] = _first_whois_value(
            text, ["Creation Date", "Created On", "Created", "Registration Date"])
        out["expires_raw"] = _first_whois_value(
            text, ["Registry Expiry Date", "Registrar Registration Expiration Date",
                   "Expiration Date", "Expiry Date", "Expire Date", "paid-till"])
        out["created"] = _parse_whois_date(out["created_raw"])
        out["expires"] = _parse_whois_date(out["expires_raw"])
        out["status"] = sorted(set(
            s.strip() for s in re.findall(r"^Domain Status:\s*(.+)$", text, re.I | re.M)))
        out["nameservers"] = sorted(set(
            s.strip().lower().rstrip(".")
            for s in re.findall(r"^Name Server:\s*(\S+)", text, re.I | re.M)))
        # v1.3.0: registrant / admin email from WHOIS, if not redacted.
        # Most .com WHOIS is redacted now, so this is usually empty —
        # the website scrape in find_contact_emails() is the main source.
        out["emails"] = extract_emails(text, domain)
        return out
    except Exception as e:
        out["error"] = str(e)
        return out


# ---------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------
# v1.2.0 fix — "Remote end closed connection without response":
# Some hosts (e.g. SiteGround / WordPress sites like
# columbuspowercleaning.com) drop the connection with NO HTTP status
# when the request carries an old Chrome user-agent — Chrome/120
# failed 6/6 times here, while a plain "Mozilla/5.0", Firefox and
# Chrome/141 all worked 6/6. The old code used Chrome/120 only, so
# a live, developed site was reported as Unknown.
# Fix: try a modern UA first, and on a closed/reset connection retry
# the SAME url with a different UA before moving to the next url.
USER_AGENTS = [
    # Modern Chrome — primary
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
    "Gecko/20100101 Firefox/133.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    # Plain fallback — the one that worked when Chrome/120 was blocked
    "Mozilla/5.0",
]

def _is_closed_connection_error(e):
    """True when the server closed the connection without a response
    (RemoteDisconnected / reset / empty reply) — worth a UA retry."""
    name = type(e).__name__
    if name in ("RemoteDisconnected", "ConnectionResetError",
                "BadStatusLine", "ConnectionAbortedError"):
        return True
    s = str(e).lower()
    return ("remote end closed" in s or "empty reply" in s
            or "connection reset" in s or "connection aborted" in s
            or "remote disconnected" in s)

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Stop urllib following redirects, so we can record the chain
    ourselves (301 google.com -> www.google.com, or a cross-domain
    forward to a totally different site). Returning None makes
    urlopen raise HTTPError with the Location header instead."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _is_captcha_page(status, html):
    """SiteGround / Cloudflare style bot check: HTTP 202 with a tiny
    page that only refreshes to /.well-known/sgcaptcha/ — not the
    real site. Treat it as blocked, not as a 200."""
    if status != 202:
        return False
    low = (html or "").lower()
    return ("sgcaptcha" in low or "well-known/sgcaptcha" in low
            or ("captcha" in low and len(html or "") < 1000))

def _fetch_one(url, ua, timeout=10):
    """One GET with no auto-redirect. Returns (status, headers, html).
    Raises HTTPError for 3xx/4xx/5xx (with headers), other exceptions
    for closed connections / timeouts / SSL."""
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }, method="GET")
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read(120_000)
        return resp.getcode(), resp.headers, raw.decode("utf-8", "ignore")

def fetch_http(domain, timeout=10):
    """Try https, https://www, http, following redirects manually.
    Returns status, final_url, title, text_len, body_lower,
    redirect_chain (['301 a -> b', ...]), redirect_to (final domain
    when it differs from the checked domain), emails found on the
    homepage, and error. A same-domain www redirect is normal;
    a cross-domain redirect_to is the real owner site to contact."""
    out = {"http_code": None, "final_url": "", "title": "",
           "text_len": 0, "body_lower": "", "error": "",
           "redirect_chain": [], "redirect_to": "", "emails": [],
           "ua_used": "", "contact_links": []}
    urls = [f"https://{domain}", f"https://www.{domain}", f"http://{domain}"]
    last_err = ""
    for start_url in urls:
        url = start_url
        chain = []
        for _hop in range(6):
            got_response = False
            for ua in USER_AGENTS:
                try:
                    status, headers, html = _fetch_one(url, ua, timeout=timeout)
                except urllib.error.HTTPError as e:
                    # Redirect (3xx) or an error status — no body to read
                    # here, but the Location header is what we need.
                    if e.code in (301, 302, 303, 307, 308):
                        loc = e.headers.get("Location") if e.headers else None
                        if loc:
                            nxt = urllib.parse.urljoin(url, loc)
                            chain.append(f"{e.code} {url} -> {nxt}")
                            url = nxt
                            got_response = True  # hop handled, follow it
                        else:
                            last_err = f"HTTP {e.code} (redirect, no Location)"
                        break
                    out["http_code"] = e.code
                    out["final_url"] = url
                    out["redirect_chain"] = chain
                    last_err = f"HTTP {e.code}"
                    if e.code in (401, 403):
                        return out  # live site, content blocked — keep it
                    got_response = True  # handled, stop this start URL
                    break
                except Exception as e:
                    last_err = str(e) or type(e).__name__
                    if _is_closed_connection_error(e):
                        continue  # same URL, next user-agent
                    break  # timeout / DNS / SSL — try the next start URL
                else:
                    got_response = True
                    if _is_captcha_page(status, html):
                        last_err = "Bot check / captcha (202)"
                        continue  # next UA, maybe it gets through
                    if status in (301, 302, 303, 307, 308):
                        # _NoRedirect normally raises for these, but
                        # keep the branch for safety.
                        loc = headers.get("Location") if headers else None
                        if loc:
                            nxt = urllib.parse.urljoin(url, loc)
                            chain.append(f"{status} {url} -> {nxt}")
                            url = nxt
                            break
                    # Success (or other non-redirect status)
                    out["http_code"] = status
                    out["final_url"] = url
                    out["redirect_chain"] = chain
                    out["ua_used"] = ua  # reuse this UA for contact pages
                    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                    if m:
                        out["title"] = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
                    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html,
                                  flags=re.I | re.S)
                    text = re.sub(r"<[^>]+>", " ", text)
                    text = re.sub(r"\s+", " ", text)
                    out["text_len"] = len(text)
                    out["body_lower"] = text[:8000].lower()
                    out["emails"] = extract_emails(html, domain)
                    # v1.3.0: links to contact / about pages on the
                    # homepage itself — follow the site's own link
                    # (e.g. /foundation/contact.html) before guessing
                    # /contact-us, /contact, etc.
                    try:
                        _host = urllib.parse.urlparse(url).hostname or ""
                        _links = []
                        for _l in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
                            if "contact" in _l.lower() or "about" in _l.lower():
                                _abs = urllib.parse.urljoin(url, _l)
                                if (urllib.parse.urlparse(_abs).hostname or "") == _host:
                                    if _abs not in _links:
                                        _links.append(_abs)
                        out["contact_links"] = _links[:3]
                    except Exception:
                        out["contact_links"] = []
                    # redirect_to: final host, when it is a DIFFERENT
                    # domain (ignoring www.) from the one checked.
                    try:
                        final_host = urllib.parse.urlparse(url).hostname or ""
                    except Exception:
                        final_host = ""
                    if (final_host and final_host.lstrip("www.").lower()
                            != domain.lstrip("www.").lower()):
                        out["redirect_to"] = final_host
                    return out
            # If we followed a redirect, loop to the next hop; if the
            # hop was handled as an error / captcha, stop this start URL.
            if chain and url != start_url and out.get("http_code") is None:
                # We are mid-chain (last hop was a redirect) — continue
                # only if the last attempt actually set a new url.
                # Detect by checking whether the last chain entry ends
                # with the current url.
                if chain and chain[-1].endswith(url):
                    continue
            break
    out["error"] = last_err
    return out

def _fetch_simple_page(url, timeout=10, uas=None):
    """Fetch one extra page (contact / about) for the email finder.
    Returns html or None. Captcha / closed-connection pages are skipped.
    Tries the UA that worked for the homepage first — hammering a
    bot-protected site with 4 different UAs in a row just triggers
    its captcha (SiteGround did exactly that on columbus)."""
    for ua in (uas or USER_AGENTS):
        try:
            status, _headers, html = _fetch_one(url, ua, timeout=timeout)
            if status == 200 and not _is_captcha_page(status, html):
                return html
            if status in (301, 302, 303, 307, 308):
                return None
        except urllib.error.HTTPError:
            return None
        except Exception:
            continue
    return None

CONTACT_PATHS = ("/contact-us", "/contact", "/about-us", "/about")

def find_contact_emails(domain, http, whois_emails=None, dns_mx=None,
                        timeout=10, ua_used=None):
    """Outbound email finder. Returns (emails, contact_url).
    1) emails already found on the homepage, 2) WHOIS email if any,
    3) /contact-us, /contact, /about-us, /about pages — first page
    with an email wins. Returns only addresses actually found;
    guessing is left to check_domain(), clearly marked (?)."""
    found = list(http.get("emails") or [])
    for e in (whois_emails or []):
        if e not in found:
            found.append(e)
    contact_url = ""
    if found:
        return found[:5], contact_url
    base = (http.get("final_url") or f"https://www.{domain}").rstrip("/")
    # Only try contact pages on a live site (http 200), not on a
    # for-sale lander — those have no owner email to find.
    if http.get("http_code") == 200:
        # Try the homepage's working UA first, then one fallback.
        uas = ([ua_used] + [u for u in USER_AGENTS if u != ua_used]
               if ua_used else USER_AGENTS)[:2]
        # Candidate pages: the site's own contact/about links first,
        # then the usual guessed paths.
        candidates = list(http.get("contact_links") or [])
        for path in CONTACT_PATHS:
            _u = base + path
            if _u not in candidates:
                candidates.append(_u)
        for page_url in candidates[:6]:
            html = _fetch_simple_page(page_url, timeout=timeout, uas=uas)
            if html is None:
                continue
            if not contact_url:
                contact_url = page_url
            emails = extract_emails(html, domain)
            if emails:
                return emails[:5], page_url
            # Page exists but has no email (form only) — keep trying
            # the next candidate; the first contact URL is still kept
            # so ab can use the form if nothing else turns up.
    return found[:5], contact_url


# ---------------------------------------------------------------------
# Core check — separated from the GUI so it can be tested
# ---------------------------------------------------------------------
def check_domain(domain, opts=None):
    """opts: {timeout, do_whois, do_http, do_dns, do_email, do_redirect}.
    Returns a result dict."""
    opts = opts or {}
    timeout = int(opts.get("timeout", 10))
    do_whois = opts.get("do_whois", True)
    do_http = opts.get("do_http", True)
    do_dns = opts.get("do_dns", True)
    do_email = opts.get("do_email", True)
    do_redirect = opts.get("do_redirect", True)

    domain = normalize_domain(domain)
    now = datetime.now(timezone.utc)
    res = {
        "domain": domain, "status": "Unknown", "http_code": "",
        "title": "", "registrar": "", "created": "", "expires": "",
        "days_left": "", "parking": "", "note": "",
        "ns": "", "a": "", "redirect_to": "", "redirect_chain": "",
        "emails": "", "contact_url": "",
    }
    if not DOMAIN_RE.match(domain):
        res["status"] = "Invalid"
        res["note"] = "Bad domain format"
        return res

    dns = {"a": [], "ns": [], "cname": [], "mx": [], "nxdomain": False}
    if do_dns:
        try:
            dns = get_dns_info(domain, timeout=timeout)
        except Exception as e:
            res["note"] = f"DNS error: {e}"
    res["ns"] = ", ".join(dns.get("ns", [])[:3])
    res["a"] = ", ".join(dns.get("a", [])[:2])

    whois = {"registrar": "", "created": None, "expires": None,
             "created_raw": "", "expires_raw": "", "status": [],
             "nameservers": [], "raw_found": False, "error": "", "emails": []}
    if do_whois:
        try:
            whois = get_whois(domain, timeout=timeout)
        except Exception as e:
            whois["error"] = str(e)
    res["registrar"] = whois.get("registrar", "")[:60]
    if whois.get("created"):
        res["created"] = whois["created"].strftime("%Y-%m-%d")
    elif whois.get("created_raw"):
        res["created"] = whois["created_raw"][:10]
    if whois.get("expires"):
        res["expires"] = whois["expires"].strftime("%Y-%m-%d")
        days = (whois["expires"] - now).days
        res["days_left"] = str(days)
    elif whois.get("expires_raw"):
        res["expires"] = whois["expires_raw"][:10]

    http = {"http_code": None, "final_url": "", "title": "",
            "text_len": 0, "body_lower": "", "error": "",
            "redirect_chain": [], "redirect_to": "", "emails": []}
    if do_http:
        try:
            http = fetch_http(domain, timeout=timeout)
        except Exception as e:
            http["error"] = str(e)
    if http.get("http_code") is not None:
        res["http_code"] = str(http["http_code"])
    res["title"] = http.get("title", "")[:120]
    # v1.3.0 — redirects: final domain when it differs from the
    # checked domain (www. ignored). A cross-domain redirect_to is
    # the real owner site — contact them, not the forwarding domain.
    if do_redirect and http.get("redirect_to"):
        res["redirect_to"] = http["redirect_to"]
    if do_redirect and http.get("redirect_chain"):
        res["redirect_chain"] = " | ".join(http["redirect_chain"])

    # --- signals ---------------------------------------------------------
    ns_joined = " ".join(dns.get("ns", []) + whois.get("nameservers", [])).lower()
    parking_ns = next((p for p in PARKING_NS if p in ns_joined), "")
    final_url = (http.get("final_url") or "").lower()
    marketplace = next((m for m in MARKETPLACES if m in final_url), "")
    hay = f"{http.get('title','')} {http.get('body_lower','')} {final_url}".lower()
    sale_hit = next((k for k in SALE_KEYWORDS if k in hay), "")
    parking_hit = next((k for k in PARKING_KEYWORDS if k in hay), "")
    if parking_ns:
        res["parking"] = parking_ns
    elif marketplace:
        res["parking"] = marketplace
    elif parking_hit:
        res["parking"] = parking_hit

    # v1.3.0 — outbound emails. Only addresses actually found on the
    # site / in WHOIS go in the Emails column. If none is found and
    # this is NOT a for-sale / parking domain and the domain can
    # receive mail (MX present), show one clearly-marked guess:
    # "info@domain (?)" — (?) = unverified, try it, don't trust it.
    # If no email was found but a contact page exists, its URL is kept
    # in contact_url so ab can use the form instead.
    if do_email and do_http:
        try:
            if sale_hit or marketplace or parking_ns:
                # For-sale / parking lander — no owner email to hunt
                # for; just use what the homepage / WHOIS already had.
                found_emails = list(http.get("emails") or []) + list(whois.get("emails") or [])
                found_emails = list(dict.fromkeys(found_emails))[:5]
                contact_url = ""
            else:
                found_emails, contact_url = find_contact_emails(
                    domain, http, whois_emails=whois.get("emails"),
                    dns_mx=dns.get("mx"), timeout=timeout,
                    ua_used=http.get("ua_used"))
        except Exception:
            found_emails, contact_url = [], ""
        res["contact_url"] = contact_url
        if found_emails:
            res["emails"] = ", ".join(found_emails[:3])
        elif (not sale_hit and not marketplace
                and not next((p for p in ("afternic", "sedo", "dan.com", "atom", "hugedomains")
                              if p in ns_joined), "")
                and not res.get("redirect_to")
                and dns.get("mx")):
            # No guess when the domain redirects elsewhere — the
            # owner is at redirect_to, not at info@this-domain.
            res["emails"] = f"info@{domain} (?)"
    elif do_email and whois.get("emails"):
        res["emails"] = ", ".join(whois["emails"][:3])

    status_list = " ".join(whois.get("status", [])).lower()
    expired_status = any(s in status_list for s in
                         ("redemptionperiod", "pendingdelete", "pendingrestore"))

    # --- classify: expiry first, then available, sale, parked, developed --
    if do_whois and whois.get("expires") and whois["expires"] < now:
        res["status"] = "Expired"
        res["note"] = f"Expired {res['expires']} ({res['days_left']} days ago)"
        if expired_status:
            res["note"] += " — in redemption / pendingDelete"
        return res
    if expired_status:
        res["status"] = "Expired"
        res["note"] = f"WHOIS status: {whois.get('status', [''])[0]}"
        return res
    if do_whois and not whois.get("raw_found") and not whois.get("error"):
        # WHOIS says not registered — but only trust it if DNS agrees
        if not dns.get("a") and not dns.get("ns"):
            res["status"] = "Available"
            res["note"] = "WHOIS: no match — not registered"
            return res
    # Afternic / Sedo / Dan / Atom / HugeDomains nameservers mean the
    # domain is on a marketplace lander — that lander IS a for-sale
    # page, even when its static HTML has no "for sale" text (JS lander).
    SALE_NS = ("afternic", "sedo", "dan.com", "atom", "hugedomains")
    sale_ns = next((p for p in SALE_NS if p in ns_joined), "")
    if sale_hit or (parking_ns and sale_hit) or marketplace or sale_ns:
        res["status"] = "For Sale"
        res["note"] = f"Sale signal: '{sale_hit or marketplace or sale_ns or parking_ns}'"
        if parking_ns:
            res["note"] += f" · NS: {parking_ns}"
        return res
    if parking_ns or parking_hit:
        # Parking page without explicit sale wording
        if http.get("http_code") in (200, 301, 302) or parking_ns:
            res["status"] = "Parked"
            res["note"] = f"Parking signal: '{parking_ns or parking_hit}'"
            return res
    if http.get("http_code") == 200:
        # No text-length threshold: JS-heavy homepages (Google: 79 chars
        # of static text) are still developed sites. Parking / sale
        # were already checked above, so a 200 here is a live site.
        res["status"] = "Developed"
        mx = " · has MX" if dns.get("mx") else ""
        res["note"] = f"Live site, {http.get('text_len', 0):,} chars of text{mx}"
        return res
    if http.get("http_code") in (200, 301, 302, 401, 403):
        res["status"] = "Developed"
        res["note"] = f"HTTP {http['http_code']} — live, content unclear"
        return res
    # v1.2.0: server closed the connection without a response, but the
    # domain has a real A record AND real email (MX), and no parking /
    # sale signal was found above — that is a live business site whose
    # server / WAF blocked our request, not an empty domain.
    # Don't call it Unknown.
    http_err = (http.get("error") or "").lower()
    if (dns.get("a") and dns.get("mx")
            and ("remote end closed" in http_err or "empty reply" in http_err
                 or "connection reset" in http_err
                 or "remote disconnected" in http_err)):
        res["status"] = "Developed"
        res["note"] = ("Server closed connection without response "
                       "(likely bot filter) — DNS + MX present, "
                       "likely live site; verify in browser")
        return res
    if dns.get("nxdomain") and not dns.get("a"):
        res["status"] = "Unknown"
        res["note"] = "NXDOMAIN — no DNS, WHOIS inconclusive"
        return res
    if not dns.get("a") and not http.get("http_code"):
        res["status"] = "Unknown"
        res["note"] = (http.get("error") or whois.get("error") or
                       "No DNS / no HTTP response")
        return res
    res["status"] = "Unknown"
    res["note"] = http.get("error") or whois.get("error") or "Could not decide"
    return res


# ---------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------
STATUS_COLORS = {
    "For Sale": WARN, "Developed": OK, "Parked": "#e0a93d",
    "Expired": ERR, "Available": PURPLE, "Unknown": MUTED, "Invalid": ERR,
}

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        # Font fallback: Segoe UI is a Windows font. On Linux (or any
        # machine without it) fall back to TkDefaultFont so nothing
        # renders in a broken/missing font.
        try:
            import tkinter.font as _tkfont
            if "Segoe UI" not in _tkfont.families():
                g = globals()
                for _k, _sz, *_w in (("FONT", 10, ""), ("FONT_BOLD", 10, "bold"),
                                     ("FONT_SMALL", 9, ""), ("FONT_MONO", 9, ""),
                                     ("FONT_HEADER", 18, "bold"),
                                     ("FONT_SUBTITLE", 9, ""),
                                     ("FONT_STAT_NUM", 14, "bold"),
                                     ("FONT_STAT_LABEL", 8, "bold"),
                                     ("FONT_TITLE", 16, "bold"),
                                     ("FONT_SECTION", 9, "bold")):
                    g[_k] = ("TkDefaultFont", _sz) + (("bold",) if _w and _w[0] == "bold" else ())
        except Exception:
            pass
        self.title(f"{APP_NAME} — For Sale / Developed / Expired  •  by {DEVELOPER}")
        self.geometry("1280x920")
        self.configure(bg=BG)
        self.results = {}  # domain -> result dict
        self.order = []
        self._result_arrival = []  # domains in the order results arrived (newest first on screen)
        self.stop_event = threading.Event()
        self.running = False
        self.executor = None
        self.result_queue = queue.Queue()
        self._build_ui()
        self.after(100, self._poll_queue)

    # --- widgets -------------------------------------------------------
    def _open_kofi(self, _event=None):
        """Open the developer's Ko-fi page in the default browser."""
        try:
            webbrowser.open(KO_FI_URL)
        except Exception as e:
            messagebox.showinfo("Ko-fi", f"Open this link to support {DEVELOPER}:\n{KO_FI_URL}\n\n({e})")

    # --- Clickable domains (v1.7.0) -------------------------------------
    # Double-click = open in Chrome. Right-click = menu with Open /
    # Copy. Ctrl+C = copy selected domain(s). Enter = open selected.
    # The "Redirects to" column opens the redirect target, every
    # other column opens the domain itself.
    _TREE_COLS = ("domain", "status", "http", "title", "registrar",
                  "created", "expires", "days", "parking", "redirect_to",
                  "emails", "note")

    def _tree_cell_at(self, event):
        """(iid, column name, column index) under the mouse, or Nones."""
        try:
            iid = self.tree.identify_row(event.y)
            col_id = self.tree.identify_column(event.x)  # "#1" .. "#12"
            if not iid or not col_id:
                return None, None, None
            idx = int(col_id.lstrip("#")) - 1
            if 0 <= idx < len(self._TREE_COLS):
                return iid, self._TREE_COLS[idx], idx
        except Exception:
            pass
        return None, None, None

    def _domain_for_cell(self, iid, col):
        """Domain to open for a cell: the redirect target when the
        click was on 'Redirects to', else the row's own domain."""
        try:
            vals = self.tree.item(iid, "values")
        except Exception:
            return ""
        if not vals:
            return ""
        if col == "redirect_to" and len(vals) > 9 and vals[9]:
            return str(vals[9]).strip()
        return str(vals[0]).strip() if vals else ""

    def _copy_to_clipboard(self, text, label="Copied"):
        text = (text or "").strip()
        if not text:
            return False
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()  # keep it on the clipboard after the click
            self.status_label.configure(text=f"{label}: {text[:80]}")
            self._log(f"{label}: {text[:120]}")
            return True
        except Exception as e:
            messagebox.showwarning("Copy failed", f"Could not copy to clipboard:\n{e}")
            return False

    def _selected_domains(self):
        out = []
        for iid in self.tree.selection():
            try:
                vals = self.tree.item(iid, "values")
            except Exception:
                continue
            if vals and vals[0] and str(vals[0]) not in out:
                out.append(str(vals[0]))
        return out

    def _copy_selected_domains(self, _event=None):
        domains = self._selected_domains()
        if not domains:
            return "break"
        self._copy_to_clipboard("\n".join(domains),
                                "Copied domain" if len(domains) == 1 else f"Copied {len(domains)} domains")
        return "break"  # stop Tk doing its own Ctrl+C handling

    def _open_domain_in_chrome(self, domain):
        domain = (domain or "").strip()
        if not domain:
            return
        ok, err = open_in_chrome(domain)
        url = domain if "://" in domain else "https://" + domain
        if ok:
            self.status_label.configure(text=f"Opened in Chrome: {url}")
            self._log(f"Opened in Chrome: {url}")
        else:
            messagebox.showerror("Could not open Chrome",
                                 f"Could not open {url}\n\n{err}\n\n"
                                 "Copy the domain instead (right-click > Copy domain).")

    def _on_tree_double_click(self, event):
        iid, col, _idx = self._tree_cell_at(event)
        if not iid:
            return
        self._open_domain_in_chrome(self._domain_for_cell(iid, col))

    def _on_tree_return(self, _event=None):
        domains = self._selected_domains()
        if domains:
            self._open_domain_in_chrome(domains[0])
        return "break"

    def _on_tree_motion(self, event):
        # Hand cursor over a clickable cell (Domain / Redirects to),
        # normal cursor everywhere else in the table.
        _iid, col, _idx = self._tree_cell_at(event)
        try:
            self.tree.configure(cursor="hand2" if col in ("domain", "redirect_to") else "")
        except Exception:
            pass

    def _on_tree_right_click(self, event):
        iid, col, _idx = self._tree_cell_at(event)
        if not iid:
            return
        # Select the row that was right-clicked (if it wasn't already).
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        self._show_tree_menu(event, iid, col)

    def _show_tree_menu(self, event, iid, col):
        try:
            vals = self.tree.item(iid, "values")
        except Exception:
            return
        if not vals:
            return
        domain = str(vals[0]).strip()
        redirect_to = str(vals[9]).strip() if len(vals) > 9 else ""
        emails = str(vals[10]).strip() if len(vals) > 10 else ""
        target = self._domain_for_cell(iid, col)
        url = target if "://" in target else "https://" + target
        menu = tk.Menu(self, tearoff=0, bg=PANEL, fg=FG,
                       activebackground=ACCENT, activeforeground="#ffffff",
                       font=FONT_SMALL)
        menu.add_command(label=f"🌐  Open in Chrome — {target}",
                         command=lambda: self._open_domain_in_chrome(target))
        if redirect_to and redirect_to.lower() != domain.lower():
            menu.add_command(label=f"🌐  Open redirect target in Chrome — {redirect_to}",
                             command=lambda: self._open_domain_in_chrome(redirect_to))
        menu.add_separator()
        menu.add_command(label=f"📋  Copy domain — {domain}",
                         command=lambda: self._copy_to_clipboard(domain, "Copied domain"))
        menu.add_command(label="📋  Copy URL — " + ("https://" + domain),
                         command=lambda: self._copy_to_clipboard("https://" + domain, "Copied URL"))
        if redirect_to:
            menu.add_command(label=f"📋  Copy redirect target — {redirect_to}",
                             command=lambda: self._copy_to_clipboard(redirect_to, "Copied redirect target"))
        if emails:
            menu.add_command(label=f"📋  Copy email(s) — {emails[:60]}",
                             command=lambda: self._copy_to_clipboard(emails, "Copied email(s)"))
        menu.add_separator()
        row_text = "\t".join(str(v) for v in vals)
        menu.add_command(label="📋  Copy whole row",
                         command=lambda: self._copy_to_clipboard(row_text, "Copied row"))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def _set_run_buttons(self, running):
        """Keep the top AND bottom Check/Stop buttons in sync."""
        for b in (getattr(self, "check_btn", None), getattr(self, "check_btn_top", None)):
            if b is not None:
                b.configure(state="disabled" if running else "normal")
        for b in (getattr(self, "stop_btn", None), getattr(self, "stop_btn_top", None)):
            if b is not None:
                b.configure(state="normal" if running else "disabled")

    def _btn(self, parent, text, kind="secondary", command=None, tip=None):
        if kind == "primary":
            bg, fg, hover, pressed = ACCENT, "#ffffff", ACCENT_HOVER, ACCENT_PRESSED
        elif kind == "kofi":
            bg, fg, hover, pressed = KOFI, "#ffffff", KOFI_HOVER, KOFI_PRESSED
        elif kind == "danger":
            bg, fg, hover, pressed = "#3a1e22", "#ff8a90", "#4a2428", "#2c1518"
        else:
            bg, fg, hover, pressed = PANEL_ALT, FG, PANEL_HOVER, PANEL
        b = tk.Button(parent, text=text, font=FONT_BOLD, bg=bg, fg=fg,
                      activebackground=hover, activeforeground=fg,
                      relief="flat", padx=16, pady=7, cursor="hand2",
                      command=command, borderwidth=0, highlightthickness=0)
        def _enter(_e, b=b, hover=hover):
            if str(b["state"]) != "disabled":
                b.configure(bg=hover)
        def _leave(_e, b=b, bg=bg):
            if str(b["state"]) != "disabled":
                b.configure(bg=bg)
        def _press(_e, b=b, pressed=pressed):
            if str(b["state"]) != "disabled":
                b.configure(bg=pressed)
        def _release(_e, b=b, bg=bg, hover=hover):
            if str(b["state"]) != "disabled":
                b.configure(bg=hover)
        b.bind("<Enter>", _enter); b.bind("<Leave>", _leave)
        b.bind("<ButtonPress-1>", _press); b.bind("<ButtonRelease-1>", _release)
        if tip:
            Tooltip(b, tip)
        return b

    def _build_ui(self):
        # --- ttk theme (dark, clam base) --------------------------------
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=FG, rowheight=24, font=FONT_SMALL,
                        borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL_ALT,
                        foreground=FG, font=FONT_BOLD, relief="flat",
                        borderwidth=0)
        style.map("Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])
        style.configure("Accent.Horizontal.TProgressbar", background=ACCENT,
                        troughcolor=PANEL_ALT, borderwidth=0, thickness=6)
        style.configure("TCombobox", fieldbackground=PANEL_ALT,
                        background=PANEL_ALT, foreground=FG,
                        arrowcolor=FG, borderwidth=0)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_ALT)],
                  foreground=[("readonly", FG)])
        style.configure("Vertical.TScrollbar", background=PANEL_ALT,
                        troughcolor=PANEL, borderwidth=0, arrowcolor=MUTED)
        style.configure("Horizontal.TScrollbar", background=PANEL_ALT,
                        troughcolor=PANEL, borderwidth=0, arrowcolor=MUTED)

        # --- Thermal accent strip (Outgllat signature) ------------------
        tk.Frame(self, bg=ACCENT, height=4).pack(fill="x")

        # --- Header: slim pro bar ---------------------------------------
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=16, pady=(6, 4))
        badge = tk.Label(head, text=f"  {DEVELOPER.upper()}  ",
                         font=FONT_BOLD, bg=ACCENT, fg="#ffffff",
                         padx=8, pady=5)
        badge.pack(side="left", padx=(0, 12))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text=APP_NAME.upper(), font=FONT_TITLE, bg=BG,
                 fg=FG, anchor="w").pack(anchor="w")
        tk.Label(titles,
                 text="For Sale  •  Developed  •  Parked  •  Expired  •  Available  •  Redirects  •  Contact emails",
                 font=FONT_SUBTITLE, bg=BG, fg=MUTED, anchor="w").pack(anchor="w")
        right = tk.Frame(head, bg=BG)
        right.pack(side="right")
        tk.Label(right, text="Free — just your duaa 🤲", font=FONT_SMALL,
                 bg=BG, fg=MUTED).pack(side="left", padx=(0, 12))
        tk.Label(right, text=f"v{APP_VERSION}", font=FONT_BOLD,
                 bg=PANEL_ALT, fg=ACCENT, padx=10, pady=5).pack(
                     side="left", padx=(0, 10))
        self._btn(right, "☕  Support on Ko-fi", kind="kofi",
                  command=self._open_kofi,
                  tip=f"Support {DEVELOPER} on Ko-fi — opens {KO_FI_URL}").pack(side="left")

        # --- Top action bar: Check / Stop / Clear + search + filter -----
        bar = tk.Frame(self, bg=PANEL, highlightbackground=BORDER,
                       highlightthickness=1)
        bar.pack(fill="x", padx=16, pady=(0, 6))
        self.check_btn_top = self._btn(bar, "▶  Check All", kind="primary",
                                       command=self.check_all,
                                       tip="Check every domain in the list")
        self.check_btn_top.pack(side="left", padx=(10, 0), pady=6)
        self.stop_btn_top = self._btn(bar, "■  Stop", kind="danger",
                                      command=self.stop_check,
                                      tip="Stop after the current checks finish")
        self.stop_btn_top.pack(side="left", padx=(6, 0), pady=6)
        self.stop_btn_top.configure(state="disabled")
        self._btn(bar, "Clear", command=self.clear_all,
                  tip="Clear the input list and results").pack(
                      side="left", padx=(6, 0), pady=6)
        tk.Frame(bar, bg=BORDER, width=1, height=28).pack(
            side="left", padx=12, pady=6)
        tk.Label(bar, text="Search:", font=FONT_SMALL, bg=PANEL,
                 fg=MUTED).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_table())
        tk.Entry(bar, textvariable=self.search_var, font=FONT_SMALL,
                 bg=PANEL_ALT, fg=FG, insertbackground=FG, relief="flat",
                 width=26).pack(side="left", padx=(4, 12), ipady=4)
        tk.Label(bar, text="Show:", font=FONT_SMALL, bg=PANEL,
                 fg=MUTED).pack(side="left")
        self.filter_var = tk.StringVar(value="All")
        ttk.Combobox(bar, textvariable=self.filter_var, values=[
            "All", "For Sale", "Developed", "Parked", "Expired", "Available", "Unknown"],
            width=11, state="readonly", font=FONT_SMALL).pack(side="left", padx=(4, 0))
        self.filter_var.trace_add("write", lambda *_: self._refresh_table())
        self._btn(bar, "Export CSV", command=lambda: self.export_csv(False),
                  tip="Export all results to CSV").pack(side="right", padx=(0, 10), pady=6)
        self._btn(bar, "Export For Sale", command=lambda: self.export_csv(True),
                  tip="Export only For Sale domains to CSV").pack(side="right", padx=(0, 6), pady=6)
        self._btn(bar, "Save", command=self.save_session).pack(side="right", padx=(0, 6), pady=6)
        self._btn(bar, "Load", command=self.load_session).pack(side="right", padx=(0, 6), pady=6)

        # --- Radar deck: live scope + latest-result card ----------------
        radar_deck = tk.Frame(self, bg=BG)
        radar_deck.pack(fill="x", padx=16, pady=(0, 8))
        radar_card = tk.Frame(radar_deck, bg=PANEL, highlightbackground=BORDER,
                              highlightthickness=1)
        radar_card.pack(side="left", padx=(0, 10))
        self._radar_canvas = tk.Canvas(radar_card, width=240, height=200,
                                       bg="#0b0e12", highlightthickness=0)
        self._radar_canvas.pack(padx=6, pady=6)
        self._radar_canvas.bind("<Button-1>", self._on_radar_click)
        self._radar_canvas.bind("<Motion>", self._on_radar_motion)
        self._radar_canvas.bind("<Leave>", self._on_radar_leave)

        side = tk.Frame(radar_deck, bg=PANEL, highlightbackground=BORDER,
                        highlightthickness=1)
        side.pack(side="left", fill="both", expand=True)
        self._radar_live_label = tk.Label(side, text="●  LIVE  —  LATEST RESULT",
                 font=FONT_BOLD, bg=PANEL, fg=OK, anchor="w")
        self._radar_live_label.pack(anchor="w", padx=12, pady=(8, 2))
        self._radar_status = tk.Label(side,
                 text="No domains checked yet — paste domains below, then Check All.",
                 font=FONT, bg=PANEL, fg=FG, anchor="w",
                 wraplength=520, justify="left")
        self._radar_status.pack(anchor="w", fill="x", padx=12)
        self._radar_traffic = tk.Label(side,
                 text="0 tracked  •  0 in flight",
                 font=FONT_SMALL, bg=PANEL, fg=MUTED, anchor="w")
        self._radar_traffic.pack(anchor="w", padx=12, pady=(6, 0))
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=12, pady=(6, 6))
        ctl_row = tk.Frame(side, bg=PANEL)
        ctl_row.pack(anchor="w", padx=12)
        self._radar_pause_btn = self._btn(ctl_row, "⏸  Pause radar",
                  command=self._toggle_radar_pause,
                  tip="Freeze the sweep and the moving blips")
        self._radar_pause_btn.pack(side="left")
        tk.Label(ctl_row, text="Sweep:", font=FONT_SMALL, bg=PANEL,
                 fg=MUTED).pack(side="left", padx=(12, 4))
        self._radar_speed_var = tk.StringVar(value="Normal")
        ttk.Combobox(ctl_row, textvariable=self._radar_speed_var,
                     values=["Slow", "Normal", "Fast"], width=8,
                     state="readonly", font=FONT_SMALL).pack(side="left")
        tk.Label(side, text="White = checking  •  Flash = sweep passed  •  Hover for details, click a blip to jump to its row.",
                 font=FONT_SMALL, bg=PANEL, fg=MUTED, anchor="w",
                 wraplength=560, justify="left").pack(anchor="w", padx=12, pady=(8, 0))
        self._radar_angle = 0.0
        self._radar_blips = {}   # domain -> live blip dict (see _radar_init_blip)
        self._radar_hover = None
        self._radar_paused = False
        self._radar_frame = 0
        self._radar_speed_map = {"Slow": 0.6, "Normal": 1.0, "Fast": 1.8}
        self.after(50, self._animate_radar)

        # --- Stat cards: one real card per status -----------------------
        cards = tk.Frame(self, bg=BG)
        cards.pack(fill="x", padx=16, pady=(0, 8))
        self._stat_values = {}
        for label, color in (("Total", FG), ("For Sale", WARN), ("Developed", OK),
                             ("Parked", "#e0a93d"), ("Expired", ERR),
                             ("Available", PURPLE), ("Unknown", MUTED)):
            card = tk.Frame(cards, bg=PANEL, highlightbackground=BORDER,
                            highlightthickness=1)
            card.pack(side="left", fill="x", expand=True, padx=(0, 6))
            tk.Frame(card, bg=color, height=3).pack(fill="x")
            num = tk.Label(card, text="0", font=FONT_STAT_NUM, bg=PANEL, fg=color)
            num.pack(pady=(0, 0))
            tk.Label(card, text=label.upper(), font=FONT_STAT_LABEL,
                     bg=PANEL, fg=MUTED).pack(pady=(0, 2))
            self._stat_values[label] = num
        # remove the trailing gap on the last card
        cards.pack_slaves()[-1].pack_configure(padx=(0, 0))

        # --- Results table (newest first, height 6) ---------------------
        cols = ("domain", "status", "http", "title", "registrar",
                "created", "expires", "days", "parking", "redirect_to",
                "emails", "note")
        headings = ("Domain", "Status", "HTTP", "Title", "Registrar",
                    "Created", "Expires", "Days left", "Parking / Marketplace",
                    "Redirects to", "Emails", "Note")
        widths = (190, 85, 50, 150, 110, 80, 80, 60, 130, 160, 190, 240)
        frame = tk.Frame(self, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1)
        frame.pack(fill="x", padx=16, pady=(0, 8))
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended", height=6)
        for c, h, w in zip(cols, headings, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w", stretch=False)
        for s, col in STATUS_COLORS.items():
            self.tree.tag_configure(s, foreground=col)
        self.tree.tag_configure("even", background=PANEL)
        self.tree.tag_configure("odd", background="#1e222a")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        # v1.7.0 — clickable domains: double-click opens in Chrome,
        # right-click (Button-3, or Button-2 / Ctrl-click on macOS)
        # shows Copy / Open, Ctrl+C copies, Enter opens, hover shows
        # a hand cursor over the Domain / Redirects-to cells.
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-3>", self._on_tree_right_click)
        self.tree.bind("<Button-2>", self._on_tree_right_click)
        self.tree.bind("<Control-Button-1>", self._on_tree_right_click)
        self.tree.bind("<Motion>", self._on_tree_motion, add="+")
        self.tree.bind("<Control-c>", self._copy_selected_domains)
        self.tree.bind("<Control-C>", self._copy_selected_domains)
        self.tree.bind("<Return>", self._on_tree_return)
        Tooltip(self.tree, "Double-click a domain to open it in Chrome  •  "
                           "Right-click for Copy / Open  •  Ctrl+C copies the domain")

        # --- Input panel -------------------------------------------------
        inp = tk.Frame(self, bg=PANEL, highlightbackground=BORDER,
                       highlightthickness=1)
        inp.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(inp, text="DOMAINS — one per line  (URLs OK, www. stripped)",
                 font=FONT_SECTION, bg=PANEL, fg=ACCENT, anchor="w").pack(
                     anchor="w", padx=12, pady=(4, 2))
        top = tk.Frame(inp, bg=PANEL)
        top.pack(fill="x", padx=12, pady=(0, 4))
        self.single_entry = tk.Entry(top, font=FONT, bg=PANEL_ALT, fg=FG,
                                     insertbackground=FG, relief="flat")
        self.single_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8))
        self.single_entry.bind("<Return>", lambda _e: self.add_single())
        self.single_entry.insert(0, "premierpowercleaning.com")
        self._btn(top, "Add", command=self.add_single,
                  tip="Add the single domain above to the list").pack(side="left")
        self._btn(top, "Load CSV / TXT", command=self.load_file,
                  tip="Load domains from a .csv or .txt file").pack(side="left", padx=(6, 0))
        self._btn(top, "Load sample", command=self._load_sample,
                  tip="Load the 3 sample domains").pack(side="left", padx=(6, 0))
        self._btn(top, "Clear", command=self.clear_all,
                  tip="Clear the input list and results").pack(side="left", padx=(6, 0))

        self.bulk = scrolledtext.ScrolledText(
            inp, height=2, font=FONT_MONO, bg=PANEL_ALT, fg=FG,
            insertbackground=FG, relief="flat", wrap="none")
        self.bulk.pack(fill="x", padx=12, pady=(0, 4))
        self.bulk.insert("1.0", "google.com\npremierpowercleaning.com\nthis-domain-definitely-not-exist-12345xyz.com")

        # Settings + bottom Check / Stop (same buttons as the top bar)
        ctl = tk.Frame(inp, bg=PANEL)
        ctl.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(ctl, text="Timeout:", font=FONT_SMALL, bg=PANEL, fg=MUTED).pack(side="left")
        self.timeout_var = tk.StringVar(value="10")
        tk.Spinbox(ctl, from_=5, to=30, textvariable=self.timeout_var, width=4,
                   font=FONT_SMALL, bg=PANEL_ALT, fg=FG, relief="flat",
                   buttonbackground=PANEL_ALT).pack(side="left", padx=(4, 12))
        tk.Label(ctl, text="Workers:", font=FONT_SMALL, bg=PANEL, fg=MUTED).pack(side="left")
        self.workers_var = tk.StringVar(value="4")
        tk.Spinbox(ctl, from_=1, to=8, textvariable=self.workers_var, width=4,
                   font=FONT_SMALL, bg=PANEL_ALT, fg=FG, relief="flat",
                   buttonbackground=PANEL_ALT).pack(side="left", padx=(4, 12))
        self.whois_var = tk.BooleanVar(value=True)
        self.http_var = tk.BooleanVar(value=True)
        self.dns_var = tk.BooleanVar(value=True)
        self.email_var = tk.BooleanVar(value=True)
        self.redirect_var = tk.BooleanVar(value=True)
        for txt, var in (("WHOIS", self.whois_var), ("HTTP", self.http_var),
                         ("DNS", self.dns_var), ("Emails", self.email_var),
                         ("Redirects", self.redirect_var)):
            tk.Checkbutton(ctl, text=txt, variable=var, font=FONT_SMALL,
                           bg=PANEL, fg=FG, selectcolor=ACCENT,
                           activebackground=PANEL, activeforeground=FG,
                           relief="flat").pack(side="left", padx=(0, 4))
        self.check_btn = self._btn(ctl, "▶  Check All", kind="primary",
                                   command=self.check_all,
                                   tip="Check every domain in the list")
        self.check_btn.pack(side="right")
        self.stop_btn = self._btn(ctl, "■  Stop", kind="danger",
                                  command=self.stop_check,
                                  tip="Stop after the current checks finish")
        self.stop_btn.pack(side="right", padx=(0, 6))
        self.stop_btn.configure(state="disabled")

        # --- Progress + log + status --------------------------------------
        self.progress = ttk.Progressbar(self, mode="determinate",
                                        style="Accent.Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=16, pady=(0, 4))
        self.log = scrolledtext.ScrolledText(self, height=2, font=FONT_MONO,
                                             bg=PANEL, fg=MUTED, relief="flat")
        self.log.pack(fill="x", padx=16, pady=(0, 2))
        self.status_label = tk.Label(self, text="Ready. Paste domains above, then Check All.  •  Double-click a domain to open it in Chrome — right-click to copy.",
                                     font=FONT_SMALL, bg=BG, fg=MUTED, anchor="w")
        self.status_label.pack(fill="x", padx=16, pady=(0, 2))

        # --- Footer --------------------------------------------------------
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 6))
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(foot, text=f"Developed by {DEVELOPER}  •  {APP_NAME} v{APP_VERSION}  •  Free — just your duaa 🤲",
                 font=FONT_SMALL, bg=BG, fg=MUTED).pack(side="left")
        kofi_link = tk.Label(foot, text="☕  Support on Ko-fi",
                             font=FONT_BOLD, bg=BG, fg=KOFI, cursor="hand2")
        kofi_link.pack(side="right")
        kofi_link.bind("<Button-1>", self._open_kofi)
        Tooltip(kofi_link, f"Support {DEVELOPER} on Ko-fi — {KO_FI_URL}")

    # --- LIVE radar (v1.5.0, Flightradar style) ------------------------
    # Every domain is a live target: it flies in white + pulsing
    # while being checked, drifts slowly around the scope leaving
    # a trail, flashes when the sweep passes over it, and pings
    # (expanding ring) when its result lands.
    def _radar_speed(self):
        return self._radar_speed_map.get(
            getattr(self, "_radar_speed_var", None)
            and self._radar_speed_var.get() or "Normal", 1.0)

    def _radar_init_blip(self, domain, status="Checking", checking=False):
        """Create a live blip for a domain, or update an existing one.
        Position is deterministic from the domain hash, so the same
        domain always starts in the same sector of the scope."""
        b = self._radar_blips.get(domain)
        if b is not None:
            b["status"] = status
            b["checking"] = checking
            return b
        h = abs(hash(domain))
        angle = float(h % 360)
        radius = float(28 + (h // 360 % 58))
        angular = 0.18 + ((h // 1000) % 10) / 40.0
        if h % 2:
            angular = -angular
        b = {"angle": angle, "radius": radius, "base_radius": radius,
             "angular": angular, "trail": [], "flash": 0.0, "ping": 0.0,
             "status": status, "checking": checking,
             "phase": (h % 100) / 100.0 * 6.28}
        self._radar_blips[domain] = b
        return b

    def _radar_set_result(self, domain, status):
        """A result just landed: stop pulsing, colour it, ping it."""
        b = self._radar_blips.get(domain)
        if b is None:
            b = self._radar_init_blip(domain, status=status, checking=False)
        b["status"] = status
        b["checking"] = False
        b["flash"] = 1.0
        b["ping"] = 1.0

    def _radar_xy(self, b):
        a = math.radians(b["angle"])
        return 120 + b["radius"] * math.cos(a), 100 + b["radius"] * math.sin(a)

    def _radar_pos(self, domain):
        """Current blip position (kept for compatibility)."""
        b = self._radar_blips.get(domain)
        if b is not None:
            return self._radar_xy(b)
        h = abs(hash(domain))
        a = math.radians(h % 360)
        r = 28 + (h // 360 % 58)
        return 120 + r * math.cos(a), 100 + r * math.sin(a)

    def _update_radar_blips(self):
        speed = self._radar_speed()
        for b in list(self._radar_blips.values()):
            b["angle"] = (b["angle"] + b["angular"] * speed) % 360
            b["phase"] += 0.03 * speed
            b["radius"] = max(18.0, min(88.0,
                b["base_radius"] + math.sin(b["phase"]) * 3.0))
            x, y = self._radar_xy(b)
            b["trail"].append((x, y))
            if len(b["trail"]) > 16:
                b["trail"].pop(0)
            b["flash"] = max(0.0, b["flash"] - 0.06)
            b["ping"] = max(0.0, b["ping"] - 0.03)
            # Sweep flash — like a real radar return: the blip lights
            # up bright for a moment as the beam passes over it.
            diff = abs((self._radar_angle - b["angle"] + 180) % 360 - 180)
            if diff < 5:
                b["flash"] = 1.0

    def _draw_radar(self):
        c = getattr(self, "_radar_canvas", None)
        if c is None or not c.winfo_exists():
            return
        c.delete("all")
        cx, cy, R = 120, 100, 92
        # Faint grid — Flightradar map feel
        for gx in range(cx - 80, cx + 81, 20):
            c.create_line(gx, cy - R, gx, cy + R, fill="#101a20")
        for gy in range(cy - 80, cy + 81, 20):
            c.create_line(cx - R, gy, cx + R, gy, fill="#101a20")
        # Range rings + crosshairs
        for r, col in ((92, "#223642"), (69, "#1a2a33"), (46, "#16222b"), (23, "#16222b")):
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=1)
        c.create_line(cx - R, cy, cx + R, cy, fill="#16222b")
        c.create_line(cx, cy - R, cx, cy + R, fill="#16222b")
        c.create_text(cx, cy - R - 8, text="N", fill="#3a4a55", font=FONT_SMALL)
        c.create_text(cx + R + 8, cy, text="E", fill="#3a4a55", font=FONT_SMALL)
        c.create_text(cx, cy + R + 8, text="S", fill="#3a4a55", font=FONT_SMALL)
        c.create_text(cx - R - 8, cy, text="W", fill="#3a4a55", font=FONT_SMALL)
        for r, lab in ((46, "50"), (92, "100")):
            c.create_text(cx + 4, cy - r, text=lab, fill="#2c3e4a",
                          font=("Segoe UI", 7), anchor="w")
        c.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="#3a4a55", outline="")
        # Sweep — fading trail behind the beam, then the bright beam
        for off, col in ((36, "#0f2a1e"), (27, "#143d2a"),
                         (18, "#1d5c3a"), (9, "#2a7a4a")):
            a = math.radians(self._radar_angle - off)
            c.create_line(cx, cy, cx + R * math.cos(a), cy + R * math.sin(a),
                          fill=col, width=2)
        a = math.radians(self._radar_angle)
        c.create_line(cx, cy, cx + R * math.cos(a), cy + R * math.sin(a),
                      fill=ACCENT, width=2)
        # Blips — trails first, then ping ripples, then the targets
        newest = self._result_arrival[-1] if self._result_arrival else None
        for d, b in self._radar_blips.items():
            x, y = self._radar_xy(b)
            col = "#f2f4f7" if b["checking"] else STATUS_COLORS.get(b["status"], MUTED)
            if len(b["trail"]) > 1:
                c.create_line(*[v for pt in b["trail"] for v in pt],
                              fill=col, width=1)
            if b["ping"] > 0:
                pr = 5 + (1 - b["ping"]) * 20
                c.create_oval(x - pr, y - pr, x + pr, y + pr,
                              outline=col, width=1)
        for d, b in self._radar_blips.items():
            x, y = self._radar_xy(b)
            col = "#f2f4f7" if b["checking"] else STATUS_COLORS.get(b["status"], MUTED)
            # Heading triangle — points along the direction of travel
            heading = math.radians(b["angle"] + (90 if b["angular"] >= 0 else -90))
            hx, hy = math.cos(heading), math.sin(heading)
            px, py = -hy, hx
            tip = (x + hx * 8, y + hy * 8)
            left = (x - hx * 5 + px * 4, y - hy * 5 + py * 4)
            right = (x - hx * 5 - px * 4, y - hy * 5 - py * 4)
            c.create_polygon(tip, left, right, fill=col, outline="")
            # Flash halo when the sweep passes, pulsing while checking
            if b["flash"] > 0.15:
                hr = 10 + (1 - b["flash"]) * 5
                c.create_oval(x - hr, y - hr, x + hr, y + hr,
                              outline=col, width=2)
            elif b["checking"]:
                pr = 6 + 2 * math.sin(self._radar_frame * 0.35)
                c.create_oval(x - pr, y - pr, x + pr, y + pr,
                              outline="#f2f4f7", width=1)
            if d == newest and not b["checking"]:
                c.create_oval(x - 12, y - 12, x + 12, y + 12,
                              outline=col, width=1)
            if d == getattr(self, "_radar_hover", None) or d == newest or b["checking"]:
                label = d.split(".")[0][:12] + (" …" if b["checking"] else "")
                c.create_text(x + 10, y - 9, text=label,
                              fill="#c8d0d8", font=("Segoe UI", 7), anchor="w")
            # Hover card — Flightradar-style callout on the scope
            if getattr(self, "_radar_hover", None) == d:
                info = f"{d} — {b['status']}" if not b["checking"] else f"{d} — checking…"
                if not b["checking"]:
                    r = self.results.get(d) or {}
                    if r.get("emails"):
                        info += f"  •  {r['emails']}"
                tx, ty = min(x + 14, 240 - 190), max(y - 34, 4)
                c.create_rectangle(tx - 4, ty - 4, tx + 184, ty + 14,
                                   fill="#111218", outline=col, width=1)
                c.create_text(tx, ty + 5, text=info[:42],
                              fill="#eef0f4", font=FONT_SMALL, anchor="w")

    def _animate_radar(self):
        try:
            self._radar_frame += 1
            if not getattr(self, "_radar_paused", False):
                self._radar_angle = (
                    self._radar_angle + 3.0 * self._radar_speed()) % 360
                self._update_radar_blips()
            self._draw_radar()
            if self._radar_frame % 10 == 0:
                checking = sum(1 for b in self._radar_blips.values()
                               if b["checking"])
                tracked = len(self._radar_blips)
                if hasattr(self, "_radar_traffic"):
                    self._radar_traffic.configure(
                        text=f"{tracked} tracked  •  {checking} in flight"
                             f"  •  sweep {int(self._radar_angle)}°"
                             + ("  •  PAUSED" if self._radar_paused else ""))
                if hasattr(self, "_radar_live_label"):
                    self._radar_live_label.configure(
                        fg="#5c6b76" if self._radar_paused
                        else (OK if self._radar_frame % 20 < 10 else "#1d7a4a"))
        except Exception:
            pass
        try:
            self.after(50, self._animate_radar)
        except Exception:
            pass

    def _toggle_radar_pause(self):
        self._radar_paused = not getattr(self, "_radar_paused", False)
        self._radar_pause_btn.configure(
            text="▶  Resume radar" if self._radar_paused else "⏸  Pause radar")
        if hasattr(self, "_radar_live_label"):
            self._radar_live_label.configure(
                text="❚❚  PAUSED  —  LATEST RESULT" if self._radar_paused
                else "●  LIVE  —  LATEST RESULT")

    def _nearest_blip(self, event):
        best, best_d = 1e9, None
        for d, b in getattr(self, "_radar_blips", {}).items():
            x, y = self._radar_xy(b)
            dist = (event.x - x) ** 2 + (event.y - y) ** 2
            if dist < best:
                best, best_d = dist, d
        return (best_d, best) if best_d is not None and best < 500 else (None, best)

    def _on_radar_motion(self, event):
        d, _dist = self._nearest_blip(event)
        self._radar_hover = d
        self._radar_canvas.configure(
            cursor="hand2" if d else "")

    def _on_radar_leave(self, _event=None):
        self._radar_hover = None

    def _on_radar_click(self, event):
        """Click a blip to jump to that domain's row in the table."""
        best_d, best = self._nearest_blip(event)
        if best_d is None:
            return
        r = self.results.get(best_d)
        if r:
            self.status_label.configure(
                text=f"{best_d}: {r['status']} — {r.get('note', '')}"
                     f"{' — ' + r['emails'] if r.get('emails') else ''}")
            for iid in self.tree.get_children():
                if self.tree.item(iid, "values")[0] == best_d:
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                    break
        else:
            self.status_label.configure(
                text=f"{best_d}: checking… — still scanning, result not in yet.")

    # --- helpers ---------------------------------------------------------
    def _log(self, msg):
        self.log.insert("end", f"{datetime.now().strftime('%H:%M:%S')}  {msg}\n")
        self.log.see("end")

    def _collect_domains(self):
        text = self.bulk.get("1.0", "end")
        return extract_domains(text)

    def add_single(self):
        d = normalize_domain(self.single_entry.get())
        if not DOMAIN_RE.match(d):
            messagebox.showwarning("Invalid domain", f"'{d}' does not look like a domain.")
            return
        cur = self.bulk.get("1.0", "end").strip()
        self.bulk.insert("end", ("" if not cur else "\n") + d if cur else d)
        self.single_entry.delete(0, "end")

    def load_file(self):
        path = filedialog.askopenfilename(
            title="Load domains", filetypes=[("CSV / TXT", "*.csv *.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
            return
        domains = extract_domains(content)
        if not domains:
            messagebox.showwarning("No domains", "No domains found in that file.")
            return
        self.bulk.insert("end", "\n" + "\n".join(domains))
        self._log(f"Loaded {len(domains)} domains from {os.path.basename(path)}")

    def _load_sample(self):
        """Load the 3 sample domains into the bulk list."""
        self.bulk.delete("1.0", "end")
        self.bulk.insert("1.0", "google.com\npremierpowercleaning.com\nthis-domain-definitely-not-exist-12345xyz.com")
        self._log("Loaded 3 sample domains.")

    def clear_all(self):
        self.bulk.delete("1.0", "end")
        self.results.clear()
        self.order.clear()
        self._result_arrival.clear()
        self._radar_blips.clear()
        self._radar_hover = None
        self._radar_status.configure(
            text="No domains checked yet — paste domains below, then Check All.")
        self._refresh_table()
        self._update_stats()
        self._log("Cleared.")

    # --- checking --------------------------------------------------------
    def check_all(self):
        if self.running:
            return
        domains = self._collect_domains()
        if not domains:
            messagebox.showwarning("No domains", "Paste at least one domain first.")
            return
        try:
            timeout = int(self.timeout_var.get())
            workers = int(self.workers_var.get())
        except ValueError:
            timeout, workers = 10, 4
        opts = {"timeout": timeout, "do_whois": self.whois_var.get(),
                "do_http": self.http_var.get(), "do_dns": self.dns_var.get(),
                "do_email": self.email_var.get(),
                "do_redirect": self.redirect_var.get()}
        self.stop_event.clear()
        self.running = True
        self._set_run_buttons(True)
        self.progress.configure(maximum=len(domains), value=0)
        self.status_label.configure(text=f"Checking {len(domains)} domains…")
        self._log(f"Checking {len(domains)} domains (timeout {timeout}s, {workers} workers)…")
        self.executor = ThreadPoolExecutor(max_workers=max(1, min(8, workers)))
        for d in domains:
            if d not in self.order:
                self.order.append(d)
            self._radar_init_blip(d, checking=True)
            self.executor.submit(self._check_one, d, opts)
        threading.Thread(target=self._wait_done, daemon=True).start()

    def _check_one(self, domain, opts):
        if self.stop_event.is_set():
            return
        try:
            res = check_domain(domain, opts)
        except Exception as e:
            res = {"domain": domain, "status": "Unknown", "http_code": "",
                   "title": "", "registrar": "", "created": "", "expires": "",
                   "days_left": "", "parking": "", "redirect_to": "",
                   "redirect_chain": "", "emails": "", "contact_url": "",
                   "note": f"Error: {e}"}
        self.result_queue.put(res)

    def _wait_done(self):
        if self.executor:
            self.executor.shutdown(wait=True)
        self.result_queue.put(None)  # sentinel: done

    def _poll_queue(self):
        done = False
        try:
            while True:
                item = self.result_queue.get_nowait()
                if item is None:
                    done = True
                    break
                self.results[item["domain"]] = item
                self._radar_set_result(item["domain"], item["status"])
                if item["domain"] not in self._result_arrival:
                    self._result_arrival.append(item["domain"])
                self._refresh_table()
                self._update_stats()
                self.progress["value"] = len(self.results)
                self._radar_status.configure(
                    text=f"Latest: {item['domain']} — {item['status']}"
                         f"{' — ' + item['emails'] if item.get('emails') else ''}"
                         f"{' — redirects to ' + item['redirect_to'] if item.get('redirect_to') else ''}")
                self._log(f"{item['domain']}: {item['status']} — {item.get('note','')}")
        except queue.Empty:
            pass
        if done:
            self.running = False
            self._set_run_buttons(False)
            self.status_label.configure(
                text=f"Done — {len(self.results)} checked. "
                     f"For Sale: {sum(1 for r in self.results.values() if r['status']=='For Sale')}.")
            self._log("Done.")
        self.after(100, self._poll_queue)

    def stop_check(self):
        self.stop_event.set()
        self._log("Stop requested — finishing current checks…")
        self.status_label.configure(text="Stopping… (current checks will finish)")

    # --- table / stats ---------------------------------------------------
    def _refresh_table(self):
        q = (self.search_var.get() or "").strip().lower()
        f = self.filter_var.get()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        # v1.4.0: results appear at the top — newest result first,
        # then the rest in input order (queued domains last).
        if self._result_arrival:
            _latest = self.results.get(self._result_arrival[-1])
            if _latest:
                self._radar_status.configure(
                    text=f"Latest: {_latest['domain']} — {_latest['status']}"
                         f"{' — ' + _latest['emails'] if _latest.get('emails') else ''}"
                         f"{' — redirects to ' + _latest['redirect_to'] if _latest.get('redirect_to') else ''}")
        display_order = list(reversed(self._result_arrival))
        display_order += [d for d in self.order if d not in display_order]
        for d in display_order:
            r = self.results.get(d)
            if r is None:
                row = (d, "…", "", "", "", "", "", "", "", "", "", "Queued…")
                self.tree.insert("", "end", values=row)
                continue
            if f != "All" and r["status"] != f:
                continue
            if q and q not in d.lower() and q not in r.get("title", "").lower() \
                    and q not in r.get("emails", "").lower() \
                    and q not in r.get("redirect_to", "").lower():
                continue
            row = (r["domain"], r["status"], r["http_code"], r["title"],
                   r["registrar"], r["created"], r["expires"], r["days_left"],
                   r["parking"], r.get("redirect_to", ""),
                   r.get("emails", ""), r["note"])
            _row_no = len(self.tree.get_children())
            self.tree.insert("", "end", values=row,
                             tags=(r["status"], "even" if _row_no % 2 == 0 else "odd"))

    def _update_stats(self):
        vals = list(self.results.values())
        def c(s):
            return sum(1 for r in vals if r["status"] == s)
        counts = {"Total": len(vals), "For Sale": c("For Sale"),
                  "Developed": c("Developed"), "Parked": c("Parked"),
                  "Expired": c("Expired"), "Available": c("Available"),
                  "Unknown": c("Unknown")}
        for label, num in self._stat_values.items():
            num.configure(text=str(counts.get(label, 0)))

    # --- export / session --------------------------------------------------
    def export_csv(self, for_sale_only):
        rows = [r for r in self.results.values()
                if (not for_sale_only or r["status"] == "For Sale")]
        if not rows:
            messagebox.showwarning("Nothing to export", "No results yet (or no For Sale domains).")
            return
        path = filedialog.asksaveasfilename(
            title="Export CSV", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="domains-for-sale.csv" if for_sale_only else "domains-checked.csv")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "domain", "status", "http_code", "title", "registrar",
                    "created", "expires", "days_left", "parking",
                    "redirect_to", "redirect_chain", "emails",
                    "contact_url", "note"])
                w.writeheader()
                for r in rows:
                    w.writerow({k: r.get(k, "") for k in w.fieldnames})
            self._log(f"Exported {len(rows)} rows to {os.path.basename(path)}")
            messagebox.showinfo("Exported", f"Exported {len(rows)} rows to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def save_session(self):
        path = filedialog.asksaveasfilename(
            title="Save session", defaultextension=".json",
            filetypes=[("JSON", "*.json")], initialfile="domain-check-session.json")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"domains": self._collect_domains(),
                           "results": list(self.results.values())}, f, indent=2)
            os.chmod(path, 0o600)
            self._log(f"Session saved to {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def load_session(self):
        path = filedialog.askopenfilename(
            title="Load session", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
            return
        self.bulk.delete("1.0", "end")
        self.bulk.insert("1.0", "\n".join(data.get("domains", [])))
        self.results = {r["domain"]: r for r in data.get("results", [])}
        self.order = list(self.results.keys()) or data.get("domains", [])
        self._result_arrival = list(self.results.keys())
        for _d, _r in self.results.items():
            self._radar_init_blip(_d, status=_r.get("status", "Unknown"))
        self._refresh_table()
        self._update_stats()
        self._log(f"Session loaded: {len(self.results)} results.")


if __name__ == "__main__":
    App().mainloop()
