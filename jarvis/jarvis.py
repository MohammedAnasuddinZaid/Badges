#!/usr/bin/env python3
"""Jarvis - Anas's terminal AI assistant for Termux. No root required."""

import argparse
import ast
import base64
import datetime
import difflib
import glob
import html
import imaplib
import email
import email.header
import email.message
import email.utils
import json
import os
import random
import re
import shlex
import shutil
import signal
import smtplib
import socket
import subprocess
import sys
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
import xml.etree.ElementTree as ET

APP = "Jarvis"
VERSION = "1.0"
BASE = os.path.join(os.path.expanduser("~"), ".jarvis")
CONFIG_PATH = os.path.join(BASE, "config.json")
HISTORY_PATH = os.path.join(BASE, "history.json")
MEMORY_PATH = os.path.join(BASE, "memory.json")
NOTES_PATH = os.path.join(BASE, "notes.json")
TODOS_PATH = os.path.join(BASE, "todos.json")
SHOPPING_PATH = os.path.join(BASE, "shopping.json")
EXPENSES_PATH = os.path.join(BASE, "expenses.json")
SMOKE_REPORT_PATH = os.path.join(BASE, "smoke_report.json")
MACROS_PATH = os.path.join(BASE, "macros.json")
SCHEDULED_PATH = os.path.join(BASE, "scheduled.json")
APP_CATALOG_PATH = os.path.join(BASE, "app_catalog.json")
APP_ALIASES_PATH = os.path.join(BASE, "app_aliases.json")
KNOWLEDGE_PATH = os.path.join(BASE, "knowledge.jsonl")
CONVERSATIONS_PATH = os.path.join(BASE, "conversations.jsonl")
PERSONA_PATH = os.path.join(BASE, "persona.txt")

UA = ("Mozilla/5.0 (Linux; Android 14; SM-A156E) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Mobile Safari/537.36")

ANSI = sys.stdout.isatty()

def col(text, code):
    return f"\033[{code}m{text}\033[0m" if ANSI else text

def dim(t):    return col(t, "2")
def cyan(t):   return col(t, "36")
def green(t):  return col(t, "32")
def yellow(t): return col(t, "33")
def red(t):    return col(t, "31")
def bold(t):   return col(t, "1")


# ---------------------------------------------------------------- storage

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def load_list(path):
    d = load_json(path, [])
    return d if isinstance(d, list) else []

def save_json(path, data, private=False):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    if private:
        os.chmod(path, 0o600)

def load_config():
    cfg = load_json(CONFIG_PATH, None)
    if not cfg:
        print(red("Jarvis is not configured."))
        print(f"Run the installer, or create {CONFIG_PATH} with your API key.")
        sys.exit(1)
    cfg.setdefault("name", "Anas")
    cfg.setdefault("model", "openai/gpt-oss-120b")
    cfg.setdefault("fallback_model", "openai/gpt-oss-20b")
    cfg.setdefault("voice", False)
    cfg.setdefault("persona", "")
    return cfg

def now_str():
    return datetime.datetime.now().strftime("%A, %d %B %Y, %I:%M %p")

def run(cmd, timeout=25, stdin_text=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, input=stdin_text)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} is not installed"
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except Exception as e:
        return 1, "", repr(e)

def auto_update():
    src_dir = "/sdcard/jarvis_pkg"
    dst_dir = BASE
    if not os.path.isdir(src_dir):
        return
    try:
        src_jarvis = os.path.join(src_dir, "jarvis.py")
        dst_jarvis = os.path.join(dst_dir, "jarvis.py")
        if os.path.exists(src_jarvis):
            src_mtime = os.path.getmtime(src_jarvis)
            dst_mtime = os.path.getmtime(dst_jarvis) if os.path.exists(dst_jarvis) else 0
            if src_mtime > dst_mtime:
                import shutil as _sh
                _sh.copy2(src_jarvis, dst_jarvis)
                # also update jarvisd.py and anas if present
                for fn in ("jarvisd.py",):
                    s = os.path.join(src_dir, fn)
                    d = os.path.join(dst_dir, fn)
                    if os.path.exists(s):
                        _sh.copy2(s, d)
                # update anas launcher
                src_anas = os.path.join(src_dir, "anas")
                dst_anas = os.path.join(os.path.expanduser("~"), "..", "usr", "bin", "anas")
                # resolve prefix properly
                prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
                dst_anas = os.path.join(prefix, "bin", "anas")
                if os.path.exists(src_anas):
                    _sh.copy2(src_anas, dst_anas)
                    os.chmod(dst_anas, 0o755)
                # update boot script
                src_boot = os.path.join(src_dir, "boot.sh")
                if os.path.exists(src_boot):
                    boot_dir = os.path.join(os.path.expanduser("~"), ".termux", "boot")
                    os.makedirs(boot_dir, exist_ok=True)
                    _sh.copy2(src_boot, os.path.join(boot_dir, "00-jarvis.sh"))
                    os.chmod(os.path.join(boot_dir, "00-jarvis.sh"), 0o700)
    except Exception:
        pass

def save_list(path, data):
    save_json(path, data)

def free_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    return json.loads(raw.decode("utf-8", "ignore"))


# ---------------------------------------------------------------- tools

APPS = {
    "whatsapp":    ["com.whatsapp", "wa", "whats app"],
    "youtube":     ["com.google.android.youtube", "yt"],
    "gmail":       ["com.google.android.gm", "mail", "email"],
    "maps":        ["com.google.android.apps.maps", "google maps"],
    "chrome":      ["com.android.chrome", "browser"],
    "messages":    ["com.google.android.apps.messaging", "sms", "texts"],
    "dialer":      ["com.samsung.android.dialer", "phone"],
    "camera":      ["com.sec.android.app.camera"],
    "clock":       ["com.sec.android.app.clockpackage", "alarm"],
    "settings":    ["com.android.settings"],
    "spotify":     ["com.spotify.music", "music"],
    "telegram":    ["org.telegram.messenger", "tg"],
    "instagram":   ["com.instagram.android", "insta", "ig"],
    "facebook":    ["com.facebook.katana", "fb"],
    "netflix":     ["com.netflix.mediaclient"],
    "paytm":       ["net.one97.paytm"],
    "phonepe":     ["com.phonepe.app"],
    "swiggy":      ["in.swiggy.android"],
    "zomato":      ["com.application.zomato"],
    "uber":        ["com.ubercab"],
    "amazon":      ["in.amazon.mShop.android.shopping"],
    "flipkart":    ["com.flipkart.android"],
}

SETTINGS = {
    "wifi": "android.settings.WIFI_SETTINGS",
    "bluetooth": "android.settings.BLUETOOTH_SETTINGS",
    "battery": "android.settings.BATTERY_SAVER_SETTINGS",
    "display": "android.settings.DISPLAY_SETTINGS",
    "sound": "android.settings.SOUND_SETTINGS",
    "location": "android.settings.LOCATION_SOURCE_SETTINGS",
    "apps": "android.settings.APPLICATION_SETTINGS",
    "airplane": "android.settings.AIRPLANE_MODE_SETTINGS",
    "data": "android.settings.DATA_ROAMING_SETTINGS",
}

CONFIRM_TOOLS = {"dial", "send_sms", "whatsapp", "compose_email", "mail_send"}


def clean_text(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()

def decode_ddg(href):
    href = html.unescape(href or "")
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href:
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = qs.get("uddg", [href])[0]
        except Exception:
            pass
    return href

def _fetch_text(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _search_bing_rss(query, limit):
    url = ("https://www.bing.com/search?q=" + urllib.parse.quote_plus(query)
           + "&format=rss")
    root = ET.fromstring(_fetch_text(url, 20))
    out = []
    for it in root.findall(".//item")[:limit]:
        title = clean_text(it.findtext("title") or "")
        href = (it.findtext("link") or "").strip()
        snip = clean_text(it.findtext("description") or "")
        if title:
            out.append("%d. %s\n   %s\n   %s" % (len(out) + 1, title, href, snip))
    return out


def _search_ddg_html(query, limit):
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    raw = _fetch_text(url)
    out = []
    for b in re.split(r'<div class="result results_links', raw)[1:]:
        m = re.search(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not m:
            continue
        sm = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', b, re.S)
        out.append("%d. %s\n   %s\n   %s" % (
            len(out) + 1, clean_text(m.group(2)), decode_ddg(m.group(1)),
            clean_text(sm.group(1)) if sm else ""))
        if len(out) >= limit:
            break
    if not out:
        for href, title in re.findall(
                r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', raw, re.S)[:limit]:
            out.append("%d. %s\n   %s" % (len(out) + 1, clean_text(title), decode_ddg(href)))
    return out


def _search_ddg_lite(query, limit):
    url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote_plus(query)
    raw = _fetch_text(url, 20)
    out = []
    for href, title in re.findall(
            r'<a[^>]*class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', raw, re.S)[:limit]:
        out.append("%d. %s\n   %s" % (len(out) + 1, clean_text(title), decode_ddg(href)))
    return out


def web_search(query, limit=5):
    """Live web search with several backends so one blocked site doesn't kill it."""
    query = str(query or "").strip()
    if not query:
        return "ERROR: empty search query."
    errors = []
    for label, backend in (("Bing", _search_bing_rss),
                           ("DuckDuckGo", _search_ddg_html),
                           ("DuckDuckGo Lite", _search_ddg_lite)):
        try:
            results = backend(query, limit)
        except Exception as e:
            errors.append("%s: %s" % (label, str(e)[:100]))
            continue
        if results:
            return "Web results for %r (%s):\n\n%s" % (
                query, label, "\n\n".join(results))
    return ("Search failed on all backends. %s\nCheck internet/data connection."
            % "; ".join(errors))

def github_search(query, limit=5, sort="stars"):
    """Search public GitHub repositories - free, no token, rate-limited."""
    q = str(query or "").strip()
    if not q:
        return "ERROR: empty GitHub query."
    url = ("https://api.github.com/search/repositories?q=" + urllib.parse.quote_plus(q)
           + "&sort=" + str(sort or "stars") + "&per_page=" + str(max(1, min(10, int(limit or 5)))))
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/vnd.github+json",
    })
    data = json.loads(urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore"))
    items = data.get("items") or []
    if not items:
        return "No GitHub repos found for %r." % q
    out = []
    for r in items:
        out.append("- %s (%d stars)\n  %s\n  %s" % (
            r.get("full_name") or "?", r.get("stargazers_count") or 0,
            r.get("html_url") or "", clean_text(r.get("description") or "")[:220]))
    return "GitHub repos for %r:\n\n%s" % (q, "\n\n".join(out))


def wiki_search(query, limit=5):
    """Wikipedia search API - free, structured, reliable."""
    q = str(query or "").strip()
    if not q:
        return "ERROR: empty Wikipedia query."
    url = ("https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
           + urllib.parse.quote_plus(q) + "&format=json&srlimit="
           + str(max(1, min(10, int(limit or 5)))))
    data = json.loads(_fetch_text(url, 20))
    items = ((data.get("query") or {}).get("search") or [])
    if not items:
        return "No Wikipedia articles found for %r." % q
    out = []
    for r in items:
        out.append("- %s\n  %s" % (clean_text(r.get("title") or ""),
                                   clean_text(r.get("snippet") or "")[:240]))
    return "Wikipedia results for %r:\n\n%s" % (q, "\n\n".join(out))


def deep_search(query, limit=5):
    """Aggregate web + GitHub + Wikipedia into one research result."""
    q = str(query or "").strip()
    if not q:
        return "ERROR: empty search query."
    blocks = []
    for label, fn in (("Web", web_search), ("GitHub", github_search), ("Wikipedia", wiki_search)):
        try:
            blocks.append("=== %s ===\n%s" % (label, fn(q, limit)))
        except Exception as e:
            blocks.append("=== %s ===\nERROR: %s" % (label, str(e)[:160]))
    return "Deep search for %r:\n\n%s" % (q, "\n\n".join(blocks))


def news(topic="", limit=6):
    if topic:
        url = ("https://news.google.com/rss/search?q=" +
               urllib.parse.quote(str(topic) + " when:2d") +
               "&hl=en-IN&gl=IN&ceid=IN:en")
    else:
        url = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=25).read()
    root = ET.fromstring(raw)
    items = root.findall(".//item")[:limit]
    if not items:
        return "No news found for that topic."
    out = []
    for it in items:
        title = clean_text(it.findtext("title") or "")
        source = clean_text(it.findtext("source") or "")
        pub = (it.findtext("pubDate") or "")[:22]
        out.append("- %s\n  %s | %s" % (title, source, pub))
    label = topic if topic else "top stories"
    return "Latest news (%s):\n\n%s" % (label, "\n".join(out))

def read_page(url):
    if not url.lower().startswith(("http://", "https://")):
        return "ERROR: only http(s) URLs are supported."
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=25).read()
    try:
        text = raw.decode("utf-8")
    except Exception:
        text = raw.decode("latin-1", "ignore")
    title = ""
    tm = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
    if tm:
        title = clean_text(tm.group(1))
    text = re.sub(r"(?is)<(script|style|noscript|svg|head|nav|footer).*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|section|article)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    head = f"Page: {title}\nURL: {url}\n\n" if title else f"URL: {url}\n\n"
    return head + text[:6500]

def weather(city):
    fmt = "?format=%l:+%C+%t+(feels+%f),+humidity+%h,+wind+%w"
    queries = [urllib.parse.quote(city or "")]
    if city:
        queries.append("")          # IP-based fallback
    last = ""
    for q in queries:
        try:
            req = urllib.request.Request("https://wttr.in/" + q + fmt,
                                         headers={"User-Agent": "curl/8"})
            text = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore").strip()
            text = re.sub(r"<[^>]+>", "", text).strip()
            if text and "Unknown location" not in text and "Sorry" not in text:
                return "Weather: " + text
            last = text
        except Exception as e:
            last = repr(e)[:80]
    return "Weather: unavailable right now (%s)" % (last or "no data")

PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
PKG_NOISE = {"com", "org", "net", "io", "co", "in", "app", "apps", "android",
             "google", "www", "mobile", "androidapps", "inc", "ltd"}


def _app_norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _label_from_package(pkg):
    parts = [p for p in str(pkg or "").split(".")
             if p and p.lower() not in PKG_NOISE]
    if not parts:
        parts = [p for p in str(pkg or "").split(".") if p]
    if not parts:
        return str(pkg or "")
    words = parts[-2:] if len(parts) > 1 else parts[:1]
    return " ".join(words).replace("_", " ").title()


def installed_apps(refresh=False):
    """Read real installed packages, with a short-lived local cache."""
    cached = load_json(APP_CATALOG_PATH, {}) or {}
    if not refresh and cached.get("apps") and time.time() - float(cached.get("ts") or 0) < 86400:
        return list(cached.get("apps") or [])
    commands = (
        ["pm", "list", "packages", "-3"],
        ["cmd", "package", "list", "packages", "-3"],
        ["pm", "list", "packages"],
        ["cmd", "package", "list", "packages"],
    )
    found = []
    for cmd in commands:
        try:
            rc, out, _err = run(cmd, timeout=25)
        except Exception:
            continue
        if rc != 0:
            continue
        for line in (out or "").splitlines():
            m = re.search(r"package:([^\s]+)", line)
            pkg = (m.group(1) if m else line.strip().split()[-1] if line.strip() else "")
            if PKG_RE.match(pkg) and pkg not in found:
                found.append(pkg)
        if found:
            break
    if found:
        save_json(APP_CATALOG_PATH, {"ts": time.time(), "apps": found}, private=True)
    return found


def app_catalog(refresh=False):
    """Return [(label, package)] for real installed apps plus known favourites."""
    aliases = load_json(APP_ALIASES_PATH, {}) or {}
    rows = {}
    for pkg in installed_apps(refresh):
        rows[pkg] = str(aliases.get(pkg) or _label_from_package(pkg))
    for canonical, values in APPS.items():
        pkg = values[0]
        rows.setdefault(pkg, str(aliases.get(pkg) or canonical))
    return sorted(((label, pkg) for pkg, label in rows.items()),
                  key=lambda x: (x[0].lower(), x[1]))


def _app_score(query, label, pkg):
    q = _app_norm(query)
    if not q:
        return 0
    texts = [_app_norm(label), _app_norm(pkg)]
    for canonical, values in APPS.items():
        if values[0] == pkg:
            texts.append(_app_norm(canonical))
            texts.extend(_app_norm(a) for a in values[1:])
    aliases = load_json(APP_ALIASES_PATH, {}) or {}
    if aliases.get(pkg):
        texts.append(_app_norm(aliases[pkg]))
    best = 0
    for text in texts:
        if not text:
            continue
        if q == text:
            best = max(best, 100)
        elif q in text:
            best = max(best, 88 - min(20, len(text) - len(q)))
        elif text in q:
            best = max(best, 80)
        else:
            ratio = difflib.SequenceMatcher(None, q, text).ratio()
            hits = sum(1 for token in q.split() if token in text.split())
            best = max(best, int(ratio * 68) + hits * 12)
    return min(99, best)


def app_find(name, limit=5):
    """Fuzzy-match any installed app by spoken name, alias or package."""
    raw = str(name or "").strip()
    q = _app_norm(raw)
    if not q:
        return []
    rows = app_catalog()
    candidates = []
    for label, pkg in rows:
        score = _app_score(q, label, pkg)
        if score >= 45:
            candidates.append({"label": label, "pkg": pkg, "score": score})
    if PKG_RE.match(raw):
        for label, pkg in rows:
            if pkg.lower() == raw.lower():
                candidates.append({"label": label, "pkg": pkg, "score": 100})
    unique = {}
    for item in candidates:
        key = item["pkg"]
        if key not in unique or item["score"] > unique[key]["score"]:
            unique[key] = item
    return sorted(unique.values(), key=lambda x: -x["score"])[:max(1, min(10, int(limit or 5)))]


def find_app(name):
    matches = app_find(name, 1)
    if not matches:
        return None
    return matches[0]["label"], matches[0]["pkg"]


def app_search(name, limit=5):
    matches = app_find(name, limit)
    if not matches:
        return "No installed app matched '%s'." % str(name)[:60]
    lines = ["App matches for %s:" % str(name)[:60]]
    for item in matches:
        lines.append("- %s (%s) - %d%%" % (
            item["label"], item["pkg"], item["score"]))
    return "\n".join(lines)


def app_list(limit=50, refresh=False):
    rows = app_catalog(refresh)
    if not rows:
        return "No installed apps found."
    try:
        lim = max(5, min(200, int(limit or 50)))
    except Exception:
        lim = 50
    lines = ["Installed apps: %d known, showing %d." % (len(rows), min(lim, len(rows)))]
    for label, pkg in rows[:lim]:
        lines.append("- %s (%s)" % (label, pkg))
    return "\n".join(lines)


def app_open(name):
    matches = app_find(name, 1)
    if not matches:
        return "I could not find an installed app called '%s'. Say 'list apps' to see them." % str(name)[:60]
    best = matches[0]
    return launch_app(best["pkg"], best["label"])


def app_close(name, j=None):
    matches = app_find(name, 1)
    if not matches:
        return "I could not find an installed app called '%s'." % str(name)[:60]
    best = matches[0]
    runner = j or Jarvis(interactive=False)
    if not runner.confirm("Close %s?" % best["label"]):
        return "Cancelled. %s was not closed." % best["label"]
    rc, out, err = run(["am", "force-stop", best["pkg"]], timeout=20)
    return ("Closed %s." % best["label"]) if rc == 0 else (
        "ERROR: could not close %s (%s)" % (best["label"], (err or out or "no response")[:120]))


def app_info(name):
    matches = app_find(name, 1)
    if not matches:
        return "I could not find an installed app called '%s'." % str(name)[:60]
    best = matches[0]
    rc, out, err = run(["dumpsys", "package", best["pkg"]], timeout=25)
    if rc != 0:
        return "ERROR: could not read app info (%s)" % (err or out or "no response")[:120]
    keep = []
    for line in (out or "").splitlines():
        s = line.strip()
        if any(k in s for k in ("versionName", "versionCode", "targetSdk",
                                "firstInstallTime", "lastUpdateTime")):
            keep.append(s[:120])
    head = "App info for %s (%s):" % (best["label"], best["pkg"])
    return head + ("\n- " + "\n- ".join(keep[:8]) if keep else "\n- No extra details returned.")


def app_alias(name, alias):
    matches = app_find(name, 1)
    if not matches:
        return "I could not find an installed app called '%s'." % str(name)[:60]
    label = _app_norm(alias)
    if not label:
        return "ERROR: give a spoken alias, for example 'banking'."
    aliases = load_json(APP_ALIASES_PATH, {}) or {}
    pkg = matches[0]["pkg"]
    aliases[pkg] = label
    save_json(APP_ALIASES_PATH, aliases, private=True)
    return "App alias saved: '%s' now opens %s (%s)." % (label, matches[0]["label"], pkg)


def refresh_app_catalog():
    rows = app_catalog(True)
    return "App catalog refreshed: %d apps visible." % len(rows)


def set_startup_macro(name):
    key = _macro_key(name)
    data = load_macros() or {}
    if key not in data:
        return "ERROR: no macro named '%s'. Save it first." % key
    cfg = load_config() or {}
    cfg["startup_macro"] = key
    save_json(CONFIG_PATH, cfg, private=True)
    return "Startup macro set to '%s'. It runs every time Jarvis OS starts." % key


def _canonical_activity(pkg):
    """Ask Android for the real launcher activity of a package."""
    rc, out, err = run(["cmd", "package", "resolve-activity", "--brief", pkg],
                       timeout=15)
    if rc == 0 and out:
        for line in reversed((out or "").strip().splitlines()):
            line = line.strip()
            if "/" in line and " " not in line:
                return line
    # dumpsys fallback
    rc, out, err = run(["dumpsys", "package", pkg], timeout=15)
    for line in (out or "").splitlines():
        line = line.strip()
        if line.startswith(pkg + "/"):
            return line.rstrip("}")
    return None

def launch_app(pkg, canonical):
    # 1) most reliable: explicit component from Android's own resolver
    comp = _canonical_activity(pkg)
    if comp:
        rc, out, err = run(["am", "start", "-n", comp], timeout=20)
        blob = (out + " " + err).lower()
        if "error" not in blob and "not found" not in blob and "does not exist" not in blob:
            return "Opened %s." % canonical
    # 2) monkey launcher intent
    rc, out, err = run(["monkey", "-p", pkg, "-c",
                        "android.intent.category.LAUNCHER", "1"], timeout=25)
    blob = (out + " " + err).lower()
    if "no activities found" not in blob and "monkey aborted" not in blob and rc == 0:
        return "Opened %s." % canonical
    # 3) common activity names
    for act in [".MainActivity", ".Main", ".SplashActivity", ".ui.MainActivity"]:
        rc3, out3, err3 = run(["am", "start", "-n", "%s/%s" % (pkg, act)], timeout=15)
        blob3 = (out3 + " " + err3).lower()
        if rc3 == 0 and "error" not in blob3 and "not found" not in blob3:
            return "Opened %s." % canonical
    return ("ERROR: could not launch %s (%s). Try installing or updating it from "
            "the Play Store.") % (canonical, pkg)

def battery_info():
    """Battery status via Termux:API, with a /sys fallback."""
    cli = ["termux-battery-status"] if _api_available("termux-battery-status") else None
    rc, out, err = termux_api("BatteryStatus", cli=cli, timeout=12)
    if rc == 0 and out:
        try:
            d = json.loads(out)
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    d = {}
    try:
        base = "/sys/class/power_supply/battery"
        with open(base + "/capacity") as f:
            d["percentage"] = int(f.read().strip())
        with open(base + "/status") as f:
            d["status"] = f.read().strip().upper()
        try:
            with open(base + "/temp") as f:
                d["temperature"] = int(f.read().strip()) / 10.0
        except Exception:
            pass
        try:
            with open(base + "/health") as f:
                d["health"] = f.read().strip().upper()
        except Exception:
            pass
    except Exception:
        pass
    return d

def fmt_battery(d):
    if not d:
        return "Battery info is unavailable right now."
    pct = d.get("percentage")
    status = (d.get("status") or "").lower()
    plugged = d.get("plugged", "")
    temp = d.get("temperature")
    health = d.get("health", "")
    charge = "charging" if "charg" in status else "not charging"
    if plugged and plugged != "UNPLUGGED":
        charge += f" ({plugged.lower().replace('plugged_', '')})"
    parts = [f"Battery {pct}%", charge]
    if temp:
        parts.append(f"{temp}C")
    if health:
        parts.append(f"health {health.lower()}")
    return ", ".join(parts)

def system_info():
    lines = []
    d = battery_info()
    lines.append(fmt_battery(d))
    try:
        du = shutil.disk_usage("/data")
        lines.append("Storage: %.1f GB free of %.1f GB" %
                     (du.free / 2**30, du.total / 2**30))
    except Exception:
        pass
    try:
        with open("/proc/uptime") as f:
            up = float(f.read().split()[0])
        h, m = int(up // 3600), int((up % 3600) // 60)
        lines.append(f"Uptime: {h}h {m}m")
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        lines.append(f"Local IP: {ip}")
    except Exception:
        pass
    lines.append("Time: " + datetime.datetime.now().strftime("%I:%M %p, %d %b %Y"))
    return "\n".join(lines)

def get_volume():
    rc, out, err = run(["termux-volume"], timeout=15)
    if rc != 0 or not out:
        return None, err or "volume info unavailable"
    try:
        return json.loads(out), ""
    except Exception:
        return None, out

def set_volume(stream, level):
    extras = [("--es", "action", "set-volume"),
              ("--es", "stream", str(stream)),
              ("--ei", "volume", str(level))]
    cli = ["termux-volume", str(stream), str(level)]
    rc, out, err = termux_api("Volume", extras, cli=cli, timeout=12)
    return rc == 0, (err or out or "ok")

def post_notification(title, body):
    extras = [("--es", "title", str(title)),
              ("--es", "id", "21340"),
              ("--es", "priority", "high")]
    cli = ["termux-notification", "--title", str(title),
           "--content", str(body), "--id", "21340", "--priority", "high"]
    rc, out, err = termux_api("Notification", extras, stdin_text=str(body),
                              cli=cli, timeout=12)
    if rc != 0:
        rc, out, err = termux_api("Notification", [("--es", "title", str(title))],
                                  stdin_text=str(body),
                                  cli=["termux-notification", "--title", str(title),
                                       "--content", str(body)], timeout=12)
    return rc == 0, (err or out or "ok")

VOICE_PROFILES = {
    # Calm Jarvis default: measured British English.
    "jarvis": {"language": "en-GB", "pitch": 0.90, "rate": 1.00},
    # BOLT: deeper and noticeably faster. Built for rapid hands-free answers.
    "bolt":   {"language": "en-GB", "pitch": 0.82, "rate": 1.35},
    # Very deep, still quick - useful in noisy places.
    "deep":   {"language": "en-GB", "pitch": 0.72, "rate": 1.15},
    # Fastest, neutral pitch.
    "fast":   {"language": "en-GB", "pitch": 0.90, "rate": 1.50},
}


def current_voice_profile():
    name = str((load_json(CONFIG_PATH, {}) or {}).get("voice_profile") or "bolt").lower()
    return name, VOICE_PROFILES.get(name, VOICE_PROFILES["jarvis"])


def set_voice_profile(name):
    key = str(name or "").strip().lower()
    if key not in VOICE_PROFILES:
        return ("ERROR: unknown voice profile. Choose: " + ", ".join(sorted(VOICE_PROFILES)))
    cfg = load_config() or {}
    cfg["voice_profile"] = key
    save_json(CONFIG_PATH, cfg, private=True)
    _, p = current_voice_profile()
    return ("Voice profile: %s (language %s, pitch %s, rate %s). "
            "New speech uses it immediately." % (
                key, p["language"], p["pitch"], p["rate"]))


def _tts_extras():
    _, p = current_voice_profile()
    return [("--es", "language", p["language"]),
            ("--ef", "pitch", str(p["pitch"])),
            ("--ef", "rate", str(p["rate"]))]


def _tts_cli(spoken):
    _, p = current_voice_profile()
    return ["termux-tts-speak", "-l", p["language"],
            "-p", str(p["pitch"]), "-r", str(p["rate"]), spoken]


def _clean_speech(text):
    spoken = re.sub(r"[*_`#>\[\]]", "", text or "")[:900]
    return spoken.replace("\u202f", " ").replace("\u00a0", " ").strip()


def speak_async(text):
    spoken = _clean_speech(text)
    if not spoken:
        return False

    def background():
        rc, _, _ = api_call("TextToSpeech", _tts_extras(),
                            stdin_text=spoken, timeout=120)
        if rc == 0:
            return
        _, p = current_voice_profile()
        for cmd in (_tts_cli(spoken),
                    ["termux-tts-speak", "-l", p["language"], spoken],
                    ["termux-tts-speak", spoken]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return
            except Exception:
                continue

    threading.Thread(target=background, daemon=True).start()
    return True


def speak_blocking(text):
    spoken = _clean_speech(text)
    if not spoken:
        return False
    rc, _, _ = termux_api("TextToSpeech", _tts_extras(), stdin_text=spoken,
                          cli=_tts_cli(spoken), timeout=120)
    return rc == 0

WAKE_WORDS = ("jarvis", "anas", "computer")


def clean_voice_text(text):
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    s = re.sub(r"^(um+|uh+|er+|okay|ok|hey)\b[\s,]*", "", s, flags=re.I)
    return s.strip(" .,!?:;'\"-")


def has_wake_word(text):
    low = clean_voice_text(text).lower()
    return any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in WAKE_WORDS)


def strip_wake_word(text):
    s = clean_voice_text(text)
    s = re.sub(r"\b(jarvis|anas|computer)\b", "", s, flags=re.I)
    return clean_voice_text(s)


def listen_once(timeout=45):
    """Hear one utterance using direct Termux:API first, CLI as fallback."""
    rc, out, err = api_call("SpeechToText", [], "", timeout)
    for raw in reversed((out or "").strip().splitlines()):
        text = clean_voice_text(raw)
        if text:
            return text
    rc2, out2, _ = run(["termux-speech-to-text"], timeout=timeout)
    if rc2 == 0:
        for raw in reversed((out2 or "").strip().splitlines()):
            text = clean_voice_text(raw)
            if text:
                return text
    return ""

def open_url(url):
    if not url.lower().startswith(("http://", "https://")):
        return "ERROR: only http(s) URLs are supported."
    rc, out, err = run(["termux-open-url", url], timeout=20)
    if rc == 0:
        return f"Opened {url} in the browser."
    rc2, out2, err2 = run(["am", "start", "-a", "android.intent.action.VIEW",
                           "-d", url], timeout=20)
    if rc2 == 0:
        return f"Opened {url} in the browser."
    return f"ERROR: could not open URL ({err or err2})."


# ---------------------------------------------------------------- music / life helpers (module-level)

PIPED_INSTANCES = [
    "https://api.piped.private.coffee",
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.reallyaweso.me",
]

def resolve_youtube_id(query, timeout=20):
    """Resolve a free-text song query to a YouTube video id (autoplay)."""
    import urllib.request as _r
    for base in PIPED_INSTANCES:
        try:
            url = base + "/search?q=" + urllib.parse.quote_plus(str(query)) + "&filter=videos"
            req = _r.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            raw = _r.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
            data = json.loads(raw)
            items = data.get("items") or []
            if items:
                href = items[0].get("url", "")
                title = items[0].get("title", "")
                vid = href.split("v=")[-1] if "v=" in href else href.rstrip("/").split("/")[-1]
                if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid or ""):
                    return vid, title
        except Exception:
            continue
    return None, None

def play_on_youtube(query):
    vid, title = resolve_youtube_id(query)
    if not vid:
        return None
    # vnd.youtube:<id> autoplays in the YouTube app
    rc, out, err = run(["am", "start", "-a", "android.intent.action.VIEW",
                        "-d", "vnd.youtube:" + vid], timeout=20)
    blob = (out + " " + err).lower()
    if rc == 0 and "error" not in blob and "not found" not in blob:
        return "Playing \"%s\" on YouTube." % (title or query)
    return open_url("https://www.youtube.com/watch?v=" + vid)

# ---------------------------------------------------------------- tech news

TECH_FEEDS = [
    ("Hacker News", "https://hnrss.org/frontpage"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("Engadget", "https://www.engadget.com/rss.xml"),
    ("Android Authority", "https://www.androidauthority.com/feed/"),
    ("GSMArena", "https://www.gsmarena.com/rss-news-reviews.php3"),
]
TECH_NEWS_PATH = os.path.join(BASE, "tech_news.json")
TECH_NEWS_TTL = 3 * 3600

def _feed_tag(node):
    return node.tag.split("}")[-1].lower()

def _feed_child(node, name):
    for c in list(node):
        if _feed_tag(c) == name:
            return c
    return None

def _fetch_feed(source, url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
        raw = urllib.request.urlopen(req, timeout=timeout).read()
        root = ET.fromstring(raw)
    except Exception:
        return []
    out = []
    for it in root.iter():
        if _feed_tag(it) not in ("item", "entry"):
            continue
        title_el = _feed_child(it, "title")
        title = clean_text(title_el.text if title_el is not None else "")
        link = ""
        link_el = _feed_child(it, "link")
        if link_el is not None:
            link = (link_el.text or "").strip() or (link_el.get("href") or "")
        if not link:
            for c in list(it):
                if _feed_tag(c) == "link" and c.get("href"):
                    link = c.get("href")
                    break
        date = ""
        for key in ("pubdate", "published", "updated", "date"):
            el = _feed_child(it, key)
            if el is not None and el.text:
                date = el.text.strip()
                break
        ts = 0
        for fmt in (email.utils.parsedate_to_datetime,):
            try:
                ts = int(fmt(date).timestamp())
                break
            except Exception:
                pass
        if not ts:
            try:
                from datetime import datetime as _dt
                ts = int(_dt.fromisoformat(date.replace("Z", "+00:00")).timestamp())
            except Exception:
                ts = 0
        if title and link:
            out.append({"title": title, "link": link, "source": source,
                        "ts": ts, "date": date})
    return out

def tech_news(limit=10, force=False, query=""):
    """Latest technology headlines from major feeds, cached for 3 hours."""
    items = []
    fresh = False
    if not force and os.path.exists(TECH_NEWS_PATH):
        try:
            cache = load_json(TECH_NEWS_PATH, {})
            if time.time() - float(cache.get("ts", 0)) < TECH_NEWS_TTL:
                items = cache.get("items") or []
                fresh = True
        except Exception:
            items = []
    if not fresh:
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(TECH_FEEDS)) as pool:
                results = list(pool.map(lambda f: _fetch_feed(f[0], f[1]), TECH_FEEDS))
        except Exception:
            results = [_fetch_feed(s, u) for s, u in TECH_FEEDS]
        items = [x for group in results for x in group]
        items.sort(key=lambda x: x.get("ts", 0), reverse=True)
        seen = set()
        uniq = []
        for it in items:
            key = re.sub(r"[^a-z0-9]+", "", it["title"].lower())[:60]
            if key in seen:
                continue
            seen.add(key)
            uniq.append(it)
        items = uniq[:60]
        try:
            save_json(TECH_NEWS_PATH, {"ts": time.time(), "items": items}, private=True)
        except Exception:
            pass
    if query:
        qt = set(re.findall(r"[a-z0-9]+", query.lower()))
        items = [it for it in items
                 if qt & set(re.findall(r"[a-z0-9]+", it["title"].lower()))] or items
    if not items:
        return "ERROR: could not fetch tech news right now (network?)."
    lines = []
    for i, it in enumerate(items[:max(1, int(limit))], 1):
        lines.append("%d. %s  [%s]" % (i, it["title"], it["source"]))
        lines.append("   " + it["link"])
    return "Latest tech news:\n" + "\n".join(lines)

# ---------------------------------------------------------------- email (IMAP/SMTP)

def _cfg_email():
    cfg = load_config() or {}
    addr = (cfg.get("email_address") or "").strip()
    pw = cfg.get("email_app_password") or ""
    if not addr or not pw:
        raise RuntimeError("Email is not set up. Run: anas jarvis mail-setup")
    return cfg, addr, pw


def _mail_error(exc):
    text = str(exc)
    low = text.lower()
    if ("application-specific password" in low or "app password" in low
            or "application specific" in low):
        return ("ERROR: Gmail rejected the saved password. It must be a 16-character "
                "Google App Password, not your normal account password. Create one at "
                "Google Account > Security > 2-Step Verification > App passwords, then "
                "run: anas jarvis mail-setup <address> xxxx xxxx xxxx xxxx")
    return "ERROR: " + text[:200]


def _mail_conn():
    cfg, addr, pw = _cfg_email()
    host = cfg.get("imap_host") or "imap.gmail.com"
    M = imaplib.IMAP4_SSL(host, timeout=30)
    M.login(addr, pw)
    return M, addr

def _hdr(msg, name):
    raw = msg.get(name) or ""
    out = ""
    try:
        for txt, enc in email.header.decode_header(raw):
            if isinstance(txt, bytes):
                out += txt.decode(enc or "utf-8", "ignore")
            else:
                out += txt
    except Exception:
        out = str(raw)
    return re.sub(r"\s+", " ", out).strip()

def _extract_body(msg, maxlen=6000):
    def part_text(part):
        try:
            raw = part.get_payload(decode=True)
            if not raw:
                return ""
            return raw.decode(part.get_content_charset() or "utf-8", "ignore")
        except Exception:
            return ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or ""):
                t = part_text(part)
                if t.strip():
                    return t[:maxlen]
        for part in msg.walk():
            if part.get_content_type() == "text/html" and "attachment" not in str(part.get("Content-Disposition") or ""):
                t = clean_text(part_text(part))
                if t.strip():
                    return t[:maxlen]
        return ""
    t = part_text(msg)
    if msg.get_content_type() == "text/html":
        t = clean_text(t)
    return t[:maxlen]

def _mail_list(uids, M, limit):
    lines = []
    for uid in list(reversed(uids))[:limit]:
        uid_s = uid.decode() if isinstance(uid, bytes) else str(uid)
        try:
            typ, d = M.uid("fetch", uid_s, "(BODY.PEEK[HEADER])")
            raw = None
            for part in d or []:
                if isinstance(part, tuple) and len(part) > 1:
                    raw = part[1]
                    break
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            lines.append("[%s] %s | %s | %s" % (
                uid_s, _hdr(msg, "From")[:60], _hdr(msg, "Subject")[:90],
                _hdr(msg, "Date")[:40]))
        except Exception:
            continue
    return lines

def mail_inbox(count=8, unread_only=False):
    try:
        M, addr = _mail_conn()
    except Exception as e:
        return _mail_error(e)
    try:
        M.select("INBOX", readonly=True)
        crit = "UNSEEN" if unread_only else "ALL"
        typ, data = M.uid("search", None, crit)
        uids = (data[0].split() if data and data[0] else [])
        if not uids:
            return "Inbox is empty." if not unread_only else "No unread mail."
        lines = _mail_list(uids, M, int(count))
        label = "Unread mail" if unread_only else "Latest mail"
        return "%s (%s):\n" % (label, addr) + "\n".join(lines)
    except Exception as e:
        return _mail_error(e)
    finally:
        try:
            M.logout()
        except Exception:
            pass

def mail_search(query, count=8):
    try:
        M, addr = _mail_conn()
    except Exception as e:
        return _mail_error(e)
    try:
        M.select("INBOX", readonly=True)
        q = str(query).replace('"', " ").strip()
        typ, data = M.uid("search", None, 'TEXT "%s"' % q)
        uids = (data[0].split() if data and data[0] else [])
        if not uids:
            return "No mail found for '%s'." % query
        lines = _mail_list(uids, M, int(count))
        return "Mail matching '%s':\n" % query + "\n".join(lines)
    except Exception as e:
        return _mail_error(e)
    finally:
        try:
            M.logout()
        except Exception:
            pass

def mail_read(uid):
    try:
        M, addr = _mail_conn()
    except Exception as e:
        return _mail_error(e)
    try:
        M.select("INBOX", readonly=True)
        typ, d = M.uid("fetch", str(uid), "(RFC822)")
        raw = None
        for part in d or []:
            if isinstance(part, tuple) and len(part) > 1:
                raw = part[1]
                break
        if not raw:
            return "ERROR: mail %s not found." % uid
        msg = email.message_from_bytes(raw)
        head = "From: %s\nTo: %s\nSubject: %s\nDate: %s\n\n" % (
            _hdr(msg, "From"), _hdr(msg, "To"), _hdr(msg, "Subject"), _hdr(msg, "Date"))
        return head + _extract_body(msg, 4000)
    except Exception as e:
        return _mail_error(e)
    finally:
        try:
            M.logout()
        except Exception:
            pass

def mail_send(to, subject, body):
    try:
        cfg, addr, pw = _cfg_email()
    except Exception as e:
        return _mail_error(e)
    host = cfg.get("smtp_host") or "smtp.gmail.com"
    try:
        msg = email.message.EmailMessage()
        msg["From"] = addr
        msg["To"] = str(to)
        msg["Subject"] = str(subject)
        msg.set_content(str(body))
        with smtplib.SMTP_SSL(host, 465, timeout=30) as s:
            s.login(addr, pw)
            s.send_message(msg)
        return "Email sent to %s." % to
    except Exception as e:
        msg = _mail_error(e)
        return msg.replace("ERROR: ", "ERROR: could not send mail: ", 1)

def mail_setup(address, app_password, imap_host="imap.gmail.com", smtp_host="smtp.gmail.com"):
    """Validate the password with a real IMAP login BEFORE saving anything."""
    addr = str(address or "").strip().lower()
    pw = re.sub(r"\s+", "", str(app_password or ""))
    if "@" not in addr or "." not in addr.split("@")[-1]:
        return "ERROR: invalid email address: %r" % addr
    if not pw:
        return "ERROR: empty password."
    try:
        M = imaplib.IMAP4_SSL(imap_host, timeout=30)
        M.login(addr, pw)
        M.logout()
    except Exception as e:
        return ("ERROR: %s rejected that password (%s).\n"
                "Gmail does NOT accept your normal account password here. Create a "
                "16-character App Password: Google Account > Security > 2-Step "
                "Verification > App passwords, then run:\n"
                "  anas jarvis mail-setup %s xxxx xxxx xxxx xxxx"
                % (imap_host, str(e)[:120], addr))
    cfg = load_config() or {}
    cfg["email_address"] = addr
    cfg["email_app_password"] = pw
    cfg["imap_host"] = imap_host
    cfg["smtp_host"] = smtp_host
    save_json(CONFIG_PATH, cfg, private=True)
    return "Email configured and verified for %s.\n%s" % (addr, mail_inbox(3))

# ---------------------------------------------------------------- file / image RAG

UPLOAD_DIRS = [
    "/sdcard/Download",
    "/sdcard/Documents",
    "/sdcard/Pictures",
    "/sdcard/Pictures/Screenshots",
    "/sdcard/DCIM",
    "/sdcard/DCIM/Camera",
    "/sdcard/DCIM/Screenshots",
    "/sdcard/Screenshots",
    "/sdcard/WhatsApp/Media/WhatsApp Images",
    "/sdcard/Telegram",
    os.path.expanduser("~/storage/shared/Download"),
    os.path.expanduser("~/storage/shared/DCIM/Camera"),
    os.path.expanduser("~/storage/shared/Pictures/Screenshots"),
]

def _resolve_upload(path):
    p = str(path or "").strip().strip("'\"")
    if not p:
        return None
    if os.path.exists(p):
        return p
    if os.path.exists("/sdcard/" + p.lstrip("/")):
        return "/sdcard/" + p.lstrip("/")
    for d in UPLOAD_DIRS:
        cand = os.path.join(d, p)
        if os.path.exists(cand):
            return cand
    try:
        base = os.path.basename(p)
        for d in UPLOAD_DIRS:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f == base:
                    return os.path.join(d, f)
    except Exception:
        pass
    return None

def _chunks(text, size=900, overlap=150):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    out = []
    i = 0
    while i < len(text):
        out.append(text[i:i + size])
        if i + size >= len(text):
            break
        i += size - overlap
    return out

def _pdf_text(path):
    txt = shutil.which("pdftotext")
    if txt:
        rc, out, err = run([txt, "-layout", path, "-"], timeout=60)
        if rc == 0 and out.strip():
            return out
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(path)
        return "\n".join((pg.extract_text() or "") for pg in reader.pages)
    except Exception:
        pass
    try:
        import PyPDF2  # type: ignore
        reader = PyPDF2.PdfReader(path)
        return "\n".join((pg.extract_text() or "") for pg in reader.pages)
    except Exception:
        return ""

def _image_mime(path):
    ext = os.path.splitext(path)[1].lower()
    return {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
            ".bmp": "image/bmp", ".heic": "image/heic"}.get(ext, "image/jpeg")

VISION_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
]

GEMINI_VISION_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
]

def _gemini_vision(path, question):
    cfg = load_config() or {}
    key = cfg.get("gemini_api_key")
    if not key:
        return None, "No Gemini API key configured."
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        return None, "could not read image: " + str(e)[:120]
    body = {"contents": [{"parts": [
        {"text": str(question)},
        {"inline_data": {"mime_type": _image_mime(path), "data": b64}},
    ]}]}
    data = json.dumps(body).encode("utf-8")
    last = ""
    for model in GEMINI_VISION_MODELS:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:"
               "generateContent?key=%s" % (model, key))
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=90)
                              .read().decode("utf-8", "ignore"))
            parts = resp["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
            if text:
                return text, None
            last = "empty response from " + model
        except urllib.error.HTTPError as e:
            last = "HTTP %s from %s" % (e.code, model)
        except Exception as e:
            last = "%s: %s" % (model, repr(e)[:100])
    return None, last

def _groq_chat(payload, model, timeout=90):
    cfg = load_config() or {}
    key = cfg.get("groq_api_key")
    if not key:
        return None, "No Groq API key configured."
    payload = dict(payload)
    payload["model"] = model
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions", data=data,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json",
                 "User-Agent": "Jarvis-Termux/1.0"})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore"))
        return resp["choices"][0]["message"].get("content", ""), None
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            body = ""
        return None, "HTTP %s: %s" % (e.code, body)
    except Exception as e:
        return None, repr(e)[:200]

def analyze_image(path, question="Describe this image in detail, including any visible text."):
    real = _resolve_upload(path)
    if not real:
        return "ERROR: image not found: %s" % path
    try:
        size = os.path.getsize(real)
        if size > 8 * 1024 * 1024:
            return "ERROR: image is larger than 8 MB."
    except Exception as e:
        return "ERROR: could not read image: " + str(e)[:120]
    # Gemini is the reliable vision backend here
    text, gerr = _gemini_vision(real, question)
    if text:
        return text
    # Groq vision fallback (if the account ever exposes it)
    try:
        with open(real, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        return "ERROR: could not read image: " + str(e)[:120]
    data_url = "data:%s;base64,%s" % (_image_mime(real), b64)
    messages = [{"role": "user", "content": [
        {"type": "text", "text": str(question)},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]}]
    err = ""
    for model in VISION_MODELS:
        out, err = _groq_chat({"messages": messages, "max_completion_tokens": 900}, model)
        if out:
            return out.strip()
    return "ERROR: image understanding failed. %s" % (gerr or err or "")

def ask_file(path, question):
    real = _resolve_upload(path)
    if not real:
        return "ERROR: file not found: %s" % path
    ext = os.path.splitext(real)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic"):
        return analyze_image(real, question)
    if ext == ".pdf":
        text = _pdf_text(real)
    else:
        try:
            with open(real, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception as e:
            return "ERROR: could not read file: " + str(e)[:120]
    if not text.strip():
        return "ERROR: no readable text found in that file."
    text = text[:60000]
    prompt = ("Answer the question using ONLY the document below. If the answer is not in it, "
              "say so.\n\nQUESTION: %s\n\nDOCUMENT:\n%s" % (question, text))
    cfg = load_config() or {}
    for model in (cfg.get("model"), cfg.get("fallback_model")):
        if not model:
            continue
        out, err = _groq_chat({"messages": [{"role": "user", "content": prompt}],
                               "max_completion_tokens": 1000}, model)
        if out:
            return out.strip()
    return "ERROR: could not answer from that file."

def ingest_file(path):
    real = _resolve_upload(path)
    if not real:
        return "ERROR: file not found: %s" % path
    name = os.path.basename(real)
    ext = os.path.splitext(real)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic"):
        desc = analyze_image(real, "Describe this image in detail and transcribe all visible text.")
        if desc.startswith("ERROR"):
            return desc
        store_knowledge("Image %s: %s" % (name, desc), "image:" + name)
        return "Stored image understanding for %s." % name
    if ext == ".pdf":
        text = _pdf_text(real)
        if not text.strip():
            return ("ERROR: could not extract PDF text. Install a extractor with: pip install pypdf")
    else:
        try:
            with open(real, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception as e:
            return "ERROR: could not read file: " + str(e)[:120]
    parts = _chunks(text)
    if not parts:
        return "ERROR: nothing readable to store."
    for i, chunk in enumerate(parts):
        store_knowledge(chunk, "file:%s#%d" % (name, i))
    return "Stored %d chunks from %s." % (len(parts), name)

def ingest_dir(path):
    real = _resolve_upload(path)
    if not real or not os.path.isdir(real):
        return "ERROR: folder not found: %s" % path
    ok = 0
    skipped = 0
    for f in sorted(os.listdir(real))[:80]:
        full = os.path.join(real, f)
        if not os.path.isfile(full):
            continue
        res = ingest_file(full)
        if res.startswith("ERROR"):
            skipped += 1
        else:
            ok += 1
    return "Ingested %d files (%d skipped) from %s." % (ok, skipped, os.path.basename(real))

def list_uploads():
    seen = set()
    lines = []
    for d in UPLOAD_DIRS:
        if not os.path.isdir(d):
            continue
        try:
            for f in sorted(os.listdir(d)):
                full = os.path.join(d, f)
                if not os.path.isfile(full):
                    continue
                if f in seen:
                    continue
                seen.add(f)
                lines.append("%s  (%s, %.1f KB)" % (full, f.rsplit(".", 1)[-1].lower(),
                                                    os.path.getsize(full) / 1024.0))
        except Exception:
            continue
    if not lines:
        return "No files found in Downloads, Documents or Pictures."
    return "Uploadable files:\n" + "\n".join(lines[:40])

# ---------------------------------------------------------------- reminders / briefing / alarms

WAKE_SONGS = {
    "gentle": [
        "Here Comes The Sun The Beatles",
        "Lovely Day Bill Withers",
        "Three Little Birds Bob Marley",
        "Banana Pancakes Jack Johnson",
        "Sunrise Norah Jones",
    ],
    "energetic": [
        "Wake Me Up Avicii",
        "Happy Pharrell Williams",
        "Walking on Sunshine Katrina and the Waves",
        "Can't Stop The Feeling Justin Timberlake",
        "Good Feeling Flo Rida",
    ],
    "focus": [
        "Weightless Marconi Union",
        "Clair de Lune Debussy",
        "Lo-fi study beats",
    ],
    "calm": [
        "Better Together Jack Johnson",
        "Holocene Bon Iver",
        "River Flows In You Yiruma",
    ],
}

def _load_scheduled():
    data = load_json(SCHEDULED_PATH, [])
    return data if isinstance(data, list) else []

def _save_scheduled(items):
    save_json(SCHEDULED_PATH, items[-200:], private=True)

def _seconds_until(hh, mm):
    now = datetime.datetime.now()
    target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return int((target - now).total_seconds())

def choose_wake_song(mood="", for_what="wake"):
    """Pick a reliable, uplifting song. Personalized from memory when possible."""
    mem = load_json(MEMORY_PATH, {}) or {}
    pref_keys = ("wake_song", "alarm_song", "morning_song", "favorite_wake_song",
                 "favorite_song", "favourite_song")
    for k in pref_keys:
        v = str(mem.get(k) or "").strip()
        if v:
            return v
    mood = str(mood or "").lower()
    if "sleep" in for_what or "calm" in mood or "relax" in mood:
        pool = WAKE_SONGS["calm"]
    elif "focus" in mood or "study" in mood or "work" in mood:
        pool = WAKE_SONGS["focus"]
    elif "gentle" in mood or "soft" in mood:
        pool = WAKE_SONGS["gentle"]
    else:
        hour = datetime.datetime.now().hour
        pool = WAKE_SONGS["energetic"] if 4 <= hour <= 11 else WAKE_SONGS["gentle"]
    return random.choice(pool)

def _bg_shell(cmd, delay=0):
    script = ("sleep %d; %s" % (max(0, int(delay)), cmd)) if delay else cmd
    try:
        subprocess.Popen(["sh", "-c", script], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except Exception:
        return False

def _play_wake_song_blocking(query, label="Wake up"):
    q = str(query or "").strip() or choose_wake_song(for_what="wake")
    speak_blocking("Good morning Anas. Time to wake up. " + str(label))
    played = play_song(q, timeout=300)
    if not played:
        # fallback: open YouTube search so something audible is available
        try:
            open_url("https://www.youtube.com/results?search_query=" +
                     urllib.parse.quote(q + " audio"))
            speak_blocking("I opened your wake-up song: " + q)
            return "Opened wake song: " + q
        except Exception:
            return "Wake alarm fired, but could not play: " + q
    return str(played)

def schedule_wake_music(hour, minute, song="", label="Wake up"):
    """Schedule a background wake-up: speak + play best song at alarm time."""
    h, m = int(hour), int(minute)
    delay = _seconds_until(h, m)
    song = (str(song or "").strip()) or choose_wake_song(for_what="wake")
    py = sys.executable or "python3"
    jarvis_py = os.path.join(BASE, "jarvis.py")
    # run in a fresh process so it survives even if current chat exits
    inner = ("%s -c 'import sys; sys.path.insert(0,%r); "
             "import jarvis; jarvis._play_wake_song_blocking(%r,%r)'"
             % (shlex.quote(py), BASE, song, str(label)[:80]))
    cmd = ("termux-notification --title %s --content %s --priority high --id 21355 >/dev/null 2>&1; "
           "%s" % (shlex.quote("Jarvis wake-up: " + str(label)[:40]),
                   shlex.quote("Playing: " + song[:120]),
                   inner))
    ok = _bg_shell(cmd, delay)
    rec = {"type": "wake_music", "hour": h, "minute": m, "song": song,
           "label": str(label)[:80], "at": time.time(), "delay": delay}
    items = _load_scheduled()
    items.append(rec)
    _save_scheduled(items)
    return ok, song, delay

def smart_alarm(hour, minute, label="Wake up", song=""):
    """Set a real Android alarm and schedule Jarvis to play the best wake song."""
    try:
        h, m = int(hour), int(minute)
        assert 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        return "ERROR: hour must be 0-23 and minute 0-59."
    rc, out, err = run(["am", "start", "-a", "android.intent.action.SET_ALARM",
                        "--ei", "hour", str(h),
                        "--ei", "minute", str(m),
                        "--es", "message", str(label)[:100],
                        "--ez", "skipUi", "false"], timeout=20)
    if rc != 0:
        rc, out, err = run(["am", "start", "-a", "android.intent.action.SET_ALARM",
                            "--ei", "hour", str(h),
                            "--ei", "minute", str(m),
                            "--es", "message", str(label)[:100]], timeout=20)
    alarm_msg = ("Alarm set for %02d:%02d (%s)." % (h, m, str(label)[:60])
                 if rc == 0 else "Could not open system alarm app (%s)." % (err or out)[:120])
    ok, picked, delay = schedule_wake_music(h, m, song, label)
    hrs, mins = delay // 3600, (delay % 3600) // 60
    when = ("%dh %dm" % (hrs, mins)) if hrs else ("%dm" % mins)
    wake_msg = ("Jarvis will also wake you in %s with: %s." % (when, picked)
                if ok else "System alarm set, but wake-song scheduler failed.")
    return alarm_msg + " " + wake_msg

def remind(minutes, text):
    try:
        mins = max(1, int(float(minutes)))
    except Exception:
        mins = 5
    msg = str(text or "Reminder").replace("'", " ")[:200]
    script = (
        "sleep %d; termux-notification --title 'Jarvis reminder' --content \"%s\" "
        "--priority high --id 21341; termux-tts-speak -l en-GB \"Reminder: %s\""
        % (mins * 60, msg, msg)
    )
    try:
        subprocess.Popen(["sh", "-c", script], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return "Okay, I'll remind you in %d minute(s): %s" % (mins, msg)
    except Exception as e:
        return "ERROR: could not schedule reminder: " + str(e)[:120]

def daily_briefing(city=""):
    cfg = load_config() or {}
    city = city or cfg.get("city") or ""
    parts = ["Briefing for " + datetime.datetime.now().strftime("%A, %d %b %Y, %I:%M %p")]
    parts.append(fmt_battery(battery_info()))
    try:
        parts.append(weather(city or ""))
    except Exception:
        pass
    try:
        parts.append(tech_news(5))
    except Exception:
        pass
    if cfg.get("email_address") and cfg.get("email_app_password"):
        try:
            box = mail_inbox(3, unread_only=True)
            if not box.startswith("ERROR"):
                parts.append(box)
        except Exception:
            pass
    return "\n\n".join(parts)

AUDIO_CACHE = os.path.join(BASE, "cache")

def play_song(query, timeout=300):
    """Download bestaudio with yt-dlp and play it inside Termux (background-capable).
    Returns a status string, or None if yt-dlp is unavailable/failed."""
    q = str(query or "").strip()
    if not q:
        return "ERROR: no song given."
    if shutil.which("yt-dlp") is None:
        return None
    try:
        os.makedirs(AUDIO_CACHE, exist_ok=True)
    except Exception:
        return None
    # clear previous downloads
    for old in glob.glob(os.path.join(AUDIO_CACHE, "nowplaying.*")):
        try:
            os.remove(old)
        except Exception:
            pass
    template = os.path.join(AUDIO_CACHE, "nowplaying.%(ext)s")
    rc, out, err = run(["yt-dlp", "--no-playlist", "-f", "bestaudio",
                        "-o", template, "--force-overwrites",
                        "ytsearch1:" + q], timeout=timeout)
    files = [f for f in glob.glob(os.path.join(AUDIO_CACHE, "nowplaying.*"))
             if os.path.getsize(f) > 10000]
    if not files:
        return None
    path = max(files, key=os.path.getmtime)
    rc2, out2, err2 = run(["termux-media-player", "play", path], timeout=30)
    if rc2 != 0:
        return None
    return "Playing \"%s\" now." % q

def media_control(action="play"):
    """Control whatever media is active via Android media session."""
    action = (action or "play").lower().strip()
    # Prefer the Termux audio player (our own playback)
    local = {"play": "play", "resume": "play", "pause": "pause", "stop": "stop"}
    if action in local:
        rc, out, err = run(["termux-media-player", local[action]], timeout=15)
        if rc == 0:
            return "Media %s." % action
    mapping = {
        "play": "play", "pause": "pause", "resume": "play",
        "next": "next", "skip": "next", "previous": "previous",
        "prev": "previous", "stop": "stop",
    }
    cmd = mapping.get(action)
    if not cmd:
        return "ERROR: unknown media action '%s'. Use play, pause, next, previous, stop." % action
    rc, out, err = run(["cmd", "media_session", "dispatch", cmd], timeout=15)
    if rc == 0:
        return "Media %s sent." % cmd
    return "ERROR: media control failed (%s)" % ((err or out or "")[:120])

def play_music(query, app="spotify"):
    q = urllib.parse.quote(str(query))
    app = (app or "spotify").lower()
    if app in ("spotify", "sp"):
        url = "spotify:search:" + urllib.parse.quote(str(query))
        rc, out, err = run(["am", "start", "-a", "android.intent.action.VIEW",
                            "-d", url], timeout=20)
        if rc == 0:
            return "Opened Spotify search for %r." % query
        # fallback to web search (redirects to app if installed)
        url = "https://open.spotify.com/search/" + q
    elif app in ("youtube music", "ytmusic", "yt music"):
        played = play_song(str(query)) or play_on_youtube(str(query))
        if played:
            return played
        url = "https://music.youtube.com/search?q=" + q
    elif app in ("youtube", "yt"):
        played = play_song(str(query)) or play_on_youtube(str(query))
        if played:
            return played
        url = "https://www.youtube.com/results?search_query=" + q
    elif app in ("jiosaavn", "saavn"):
        url = "https://www.jiosaavn.com/search/" + q
    elif app in ("gaana",):
        url = "https://gaana.com/search/" + q
    else:
        url = "https://open.spotify.com/search/" + q
    return open_url(url)

_SAFE_NAMES = {"abs": abs, "round": round, "min": min, "max": max, "pow": pow,
               "int": int, "float": float}

def calculate_expr(expr):
    expr = str(expr).strip()
    if not expr:
        return "ERROR: empty expression."
    if not re.fullmatch(r"[0-9eE+\-*/().,\s%]+", expr):
        return "ERROR: expression contains unsafe characters."
    try:
        node = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return "ERROR: " + str(e)
    for n in ast.walk(node):
        if isinstance(n, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num,
                          ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div,
                          ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Call)):
            if isinstance(n, ast.Call):
                if not (isinstance(n.func, ast.Name) and n.func.id in _SAFE_NAMES):
                    return "ERROR: function not allowed."
            continue
        return "ERROR: unsupported syntax."
    try:
        val = eval(compile(node, "<calc>", "eval"), {"__builtins__": {}}, _SAFE_NAMES)
    except Exception as e:
        return "ERROR: " + str(e)
    return "%s = %s" % (expr, val)

_UNIT_TABLE = {
    ("km", "mi"): 0.621371, ("mi", "km"): 1.60934,
    ("m", "ft"): 3.28084, ("ft", "m"): 0.3048,
    ("cm", "in"): 0.393701, ("in", "cm"): 2.54,
    ("km", "m"): 1000, ("m", "km"): 0.001,
    ("kg", "lb"): 2.20462, ("lb", "kg"): 0.453592,
    ("g", "oz"): 0.035274, ("oz", "g"): 28.3495,
    ("l", "gal"): 0.264172, ("gal", "l"): 3.78541,
    ("ml", "oz"): 0.033814, ("oz", "ml"): 29.5735,
}

def convert_units(value, frm, to):
    try:
        v = float(value)
    except Exception:
        return "ERROR: value must be a number."
    f = str(frm).lower().strip()
    t = str(to).lower().strip()
    if f in ("c", "celsius") and t in ("f", "fahrenheit"):
        return "%.2f C = %.2f F" % (v, v * 9 / 5 + 32)
    if f in ("f", "fahrenheit") and t in ("c", "celsius"):
        return "%.2f F = %.2f C" % (v, (v - 32) * 5 / 9)
    if f in ("c", "celsius") and t in ("k", "kelvin"):
        return "%.2f C = %.2f K" % (v, v + 273.15)
    if f in ("k", "kelvin") and t in ("c", "celsius"):
        return "%.2f K = %.2f C" % (v, v - 273.15)
    key = (f, t)
    if key in _UNIT_TABLE:
        return "%s %s = %s %s" % (v, f, round(v * _UNIT_TABLE[key], 6), t)
    return "ERROR: unsupported conversion. Try km/mi, kg/lb, C/F, L/gal, etc."

def qr_url(text):
    return "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" + urllib.parse.quote(str(text))

def translate_url(text, to="hi"):
    return ("https://translate.google.com/?sl=auto&tl=" + urllib.parse.quote(str(to)) +
            "&text=" + urllib.parse.quote(str(text)) + "&op=translate")

_LOCAL_JOKES = (
    "Why did the computer go to the doctor?\nBecause it had a virus.",
    "Why do programmers prefer dark mode?\nBecause light attracts bugs.",
    "I told my wife she should embrace her mistakes.\nShe gave me a hug.",
)

_LOCAL_QUOTES = (
    ("The best way to predict the future is to invent it.", "Alan Kay"),
    ("Simplicity is the soul of efficiency.", "Austin Freeman"),
    ("Any sufficiently advanced technology is indistinguishable from magic.",
     "Arthur C. Clarke"),
)


def joke():
    try:
        d = free_json("https://official-joke-api.appspot.com/random_joke", timeout=10)
        text = "%s\n%s" % (d.get("setup", ""), d.get("punchline", ""))
        if text.strip():
            return text
    except Exception:
        pass
    try:
        d = free_json("https://v2.jokeapi.dev/joke/Any?type=single", timeout=10)
        if d.get("joke"):
            return str(d["joke"])
    except Exception:
        pass
    try:
        text = (_fetch_text("https://icanhazdadjoke.com/", timeout=10) or "").strip()
        if text:
            return text
    except Exception:
        pass
    return random.choice(_LOCAL_JOKES)


def fact():
    try:
        d = free_json("https://uselessfacts.jsph.pl/api/v2/facts/random")
        return d.get("text", "no fact")
    except Exception as e:
        return "ERROR: " + str(e)


def quote():
    try:
        d = free_json("https://api.quotable.io/random", timeout=10)
        if d.get("content"):
            return '"%s" - %s' % (d.get("content", ""), d.get("author", ""))
    except Exception:
        pass
    try:
        arr = free_json("https://zenquotes.io/api/random", timeout=10)
        if isinstance(arr, list) and arr and arr[0].get("q"):
            return '"%s" - %s' % (arr[0].get("q"), arr[0].get("a", "Unknown"))
    except Exception:
        pass
    text, author = random.choice(_LOCAL_QUOTES)
    return '"%s" - %s' % (text, author)

def advice():
    try:
        d = free_json("https://api.adviceslip.com/advice")
        return d.get("slip", {}).get("advice", "no advice")
    except Exception as e:
        return "ERROR: " + str(e)

def define_word(word):
    try:
        d = free_json("https://api.dictionaryapi.dev/api/v2/entries/en/" + urllib.parse.quote(str(word)))
        if isinstance(d, list) and d:
            m = d[0].get("meanings", [])
            out = []
            for mm in m[:3]:
                pos = mm.get("partOfSpeech", "")
                defs = [dd.get("definition", "") for dd in mm.get("definitions", [])[:2]]
                out.append("%s: %s" % (pos, "; ".join(defs)))
            return "\n".join(out) if out else "No definition found."
        return "No definition found."
    except Exception as e:
        return "ERROR: " + str(e)

def wiki_summary(topic):
    try:
        url = ("https://en.wikipedia.org/api/rest_v1/page/summary/" +
               urllib.parse.quote(str(topic).replace(" ", "_")))
        d = free_json(url)
        return d.get("extract", "No summary found.")[:1200]
    except Exception as e:
        return "ERROR: " + str(e)

def crypto_price(coin):
    try:
        c = str(coin).lower().strip()
        d = free_json("https://api.coingecko.com/api/v3/simple/price?ids=%s&vs_currencies=usd,inr" % urllib.parse.quote(c))
        if c in d:
            info = d[c]
            return "%s: $%s USD / Rs %s INR" % (coin, info.get("usd"), info.get("inr"))
        return "Coin not found. Try 'bitcoin', 'ethereum', etc."
    except Exception as e:
        return "ERROR: " + str(e)

def book_search(query):
    try:
        d = free_json("https://openlibrary.org/search.json?q=" + urllib.parse.quote(str(query)) + "&limit=5")
        docs = d.get("docs", [])
        out = []
        for dd in docs[:5]:
            title = dd.get("title", "?")
            author = ", ".join(dd.get("author_name", [])[:2])
            year = dd.get("first_publish_year", "")
            out.append("- %s by %s (%s)" % (title, author, year))
        return "\n".join(out) if out else "No books found."
    except Exception as e:
        return "ERROR: " + str(e)

def currency_convert(amount, frm, to):
    try:
        a = float(amount)
    except Exception:
        return "ERROR: amount must be a number."
    f = str(frm).upper().strip()
    t = str(to).upper().strip()
    try:
        d = free_json("https://api.exchangerate-api.com/v4/latest/" + urllib.parse.quote(f))
        rate = d.get("rates", {}).get(t)
        if rate is None:
            return "ERROR: unknown currency code."
        return "%.2f %s = %.2f %s" % (a, f, a * rate, t)
    except Exception as e:
        return "ERROR: " + str(e)

def tip_calc(bill, percent=15, people=1):
    try:
        b = float(bill); p = float(percent); n = max(1, int(people))
    except Exception:
        return "ERROR: bill/percent/people must be numbers."
    tip = b * p / 100.0
    total = b + tip
    per = total / n
    return "Bill %.2f + %.0f%% tip (%.2f) = %.2f total; %.2f per person (%d people)." % (
        b, p, tip, total, per, n)

def record_audio(seconds=10):
    try:
        s = max(1, min(300, int(seconds)))
    except Exception:
        s = 10
    path = "/sdcard/recordings/jarvis_rec_%d.wav" % int(time.time())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rc, out, err = run(["termux-microphone-record", "-f", path, "-l", str(s)], timeout=s + 10)
    if rc != 0:
        return "ERROR: recording failed (%s)." % (err or out)
    return "Recording %d seconds to %s." % (s, path)

def stop_recording():
    rc, out, err = run(["termux-microphone-record", "-q"], timeout=10)
    return "Recording stopped." if rc == 0 else "ERROR: %s" % (err or out)

def open_contacts():
    rc, out, err = run(["am", "start", "-a", "android.intent.action.VIEW",
                        "content://contacts/people"], timeout=20)
    if rc != 0:
        rc, out, err = run(["am", "start", "-n", "com.android.contacts/.activities.PeopleActivity"], timeout=20)
    return "Opened contacts." if rc == 0 else "ERROR: %s" % (err or out)


def _api_available(cmd):
    return bool(shutil.which(cmd))


def _proc_starttime(pid=None):
    """Linux process starttime (field 22 of /proc/pid/stat)."""
    try:
        p = int(pid or os.getpid())
        data = open("/proc/%d/stat" % p, encoding="utf-8").read()
        tail = data[data.rfind(")") + 2:].split()
        return tail[19]
    except Exception:
        return "-1"


def api_call(method, extras=None, stdin_text="", timeout=20):
    """Talk directly to com.termux.api over its real socket protocol.

    This bypasses the stock termux-api CLI's fragile /data/data check while
    using the exact broadcast contract from termux-api.c.  Returns the same
    (rc, out, err) tuple as run().
    """
    read_name = "jarvis.r." + uuid.uuid4().hex
    write_name = "jarvis.w." + uuid.uuid4().hex
    read_sock = write_sock = None
    try:
        read_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        write_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        read_sock.bind(b"\0" + read_name.encode())
        write_sock.bind(b"\0" + write_name.encode())
        read_sock.listen(1)
        write_sock.listen(1)

        prefix = os.environ.get("PREFIX") or "/data/data/com.termux/files/usr"
        am = next((c for c in (os.path.join(prefix, "bin", "am"),
                               "/system/bin/am", "am") if c == "am" or os.path.exists(c)), "am")
        cmd = [
            am, "broadcast", "--user", "0",
            "-n", "com.termux.api/.TermuxApiReceiver",
            "--es", "socket_input", write_name,   # app reads from here
            "--es", "socket_output", read_name,   # app writes here
            "--ei", "api_server_pid", str(os.getpid()),
            "--ei", "api_server_uid", str(os.getuid()),
            "--ei", "api_server_starttime", _proc_starttime(),
            "--es", "api_method", str(method),
        ]
        for item in (extras or []):
            flag = item[0]
            cmd.extend([flag, str(item[1]), str(item[2])])
        rc, out, err = run(cmd, timeout=10)
        if rc != 0:
            return rc, out, err or "am broadcast failed"

        got = {}

        def reader():
            try:
                read_sock.settimeout(timeout)
                conn, _ = read_sock.accept()
                buf = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                got["out"] = buf.decode("utf-8", "ignore")
                conn.close()
            except Exception as e:
                got["read_err"] = repr(e)

        def writer():
            try:
                write_sock.settimeout(timeout)
                conn, _ = write_sock.accept()
                if stdin_text:
                    conn.sendall(stdin_text.encode("utf-8"))
                conn.shutdown(socket.SHUT_WR)
                conn.close()
            except Exception as e:
                got["write_err"] = repr(e)

        tr = threading.Thread(target=reader, daemon=True)
        tw = threading.Thread(target=writer, daemon=True)
        tr.start(); tw.start()
        tr.join(timeout + 2); tw.join(timeout + 2)
        if "out" in got:
            return 0, got["out"], ""
        why = got.get("read_err") or got.get("write_err") or "companion app did not respond"
        return 1, "", "Termux:API socket: " + why
    except Exception as e:
        return 1, "", "Termux:API call failed: %s" % e
    finally:
        for s in (read_sock, write_sock):
            try:
                if s:
                    s.close()
            except Exception:
                pass


def termux_api(method, extras=None, stdin_text="", cli=None, timeout=20):
    """Prefer the direct broadcast protocol, fall back to the stock CLI.

    When both fail, keep BOTH messages: the CLI's filesystem check is often
    misleading, while the direct socket error explains the real failure.
    """
    rc, out, err = api_call(method, extras, stdin_text, timeout)
    if rc == 0:
        return rc, out, err
    direct = (err or out or "direct API gave no response").strip()
    if not cli:
        return rc, out, direct
    cli_rc, cli_out, cli_err = run(cli, timeout=timeout + 10)
    if cli_rc == 0:
        return cli_rc, cli_out, cli_err
    cli_msg = (cli_err or cli_out or "CLI gave no response").strip()
    return 1, cli_out, (direct + " | CLI: " + cli_msg)[:500]


FILLER_WORDS = {
    "jarvis", "anas", "call", "dial", "phone", "number", "find", "get", "search",
    "contact", "friend", "my", "the", "a", "an", "now", "please", "pls", "plz",
    "who", "is", "his", "her", "me", "on", "mobile", "cell", "for", "to", "of",
    "and", "or", "hello", "hey", "ok", "okay", "there", "from", "this", "that",
    "already", "saved", "contact", "address", "book", "do", "it", "need", "want",
}


def _norm_name(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _soundex(s):
    s = _norm_name(s)
    if not s:
        return ""
    groups = {}
    for chars, digit in (("bpfv", "1"), ("cskgjxqz", "2"), ("dt", "3"),
                         ("l", "4"), ("mn", "5"), ("r", "6")):
        for ch in chars:
            groups[ch] = digit
    first = s[0]
    code = ""
    prev = groups.get(first, "")
    for ch in s[1:]:
        d = groups.get(ch, "")
        if d and d != prev:
            code += d
        if d:
            prev = d
        elif ch not in "hw":
            prev = ""
    return (first + (code + "000")[:3]).upper()


def _name_score(query, name):
    """Fuzzy score: exact/substring, sequence ratio, token overlap, phonetic."""
    q, n = _norm_name(query), _norm_name(name)
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    if q in n or n in q:
        return 0.93
    seq = difflib.SequenceMatcher(None, q, n).ratio()
    qt, nt = set(q.split()), set(n.split())
    overlap = len(qt & nt) / max(1, len(qt | nt))
    prefix = 0
    for a, b in zip(q, n):
        if a == b:
            prefix += 1
        else:
            break
    prefix_ratio = prefix / max(len(q), len(n))
    phonetic = 0.14 if _soundex(q) == _soundex(n) else 0.0
    return min(0.99, 0.45 * seq + 0.25 * overlap + 0.20 * prefix_ratio + phonetic)


def _name_candidates(text):
    """Generate 1-3 token chunks from both filtered and raw words.

    Keeping the raw words matters: 'gaurav anas' must still match a contact
    named 'Gaurav Anas' even though 'anas' is often filler in other phrases.
    """
    norm = _norm_name(text)
    all_words = norm.split()
    filtered = [w for w in all_words if w not in FILLER_WORDS]
    out = []
    for words in (filtered, all_words):
        for size in (3, 2, 1):
            for i in range(len(words) - size + 1):
                chunk = " ".join(words[i:i + size])
                if chunk and chunk not in out:
                    out.append(chunk)
    return out or [norm]


def _fetch_contacts():
    """Return (contacts, None) or (None, error string)."""
    rc, out, err = termux_api("ContactList", cli=["termux-contact-list"], timeout=20)
    blob = (out or "") + " " + (err or "")
    if ("not yet available on Google Play" in blob
            or "Termux:API is not installed" in blob
            or "not installed on this device" in blob
            or "did not respond" in blob
            or "Termux:API socket" in blob):
        return None, ("Termux:API companion app (com.termux.api) did not answer a "
                      "direct broadcast. The CLI check is not the real problem. "
                      "Either the app is not installed, or Termux and Termux:API "
                      "came from different sources (Play vs F-Droid/GitHub) so the "
                      "app rejects broadcasts from this Termux. Install both from "
                      "the SAME source, then allow Contacts/Phone/SMS in the "
                      "Termux:API app's App info.")
    if rc != 0:
        return None, ("cannot read contacts (%s). Open Termux:API > App info > "
                      "Permissions > allow Contacts." % blob[:150])
    try:
        data = json.loads(out)
    except Exception:
        return None, "unexpected contacts response: %s" % out[:200]
    if not isinstance(data, list):
        return None, "unexpected contacts format."
    cleaned = []
    for c in data:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or c.get("display_name") or "").strip()
        nums = c.get("numbers") or c.get("number") or []
        if isinstance(nums, str):
            nums = [nums]
        nums = [str(n).strip() for n in nums if str(n or "").strip()]
        cleaned.append({"name": name, "numbers": nums})
    return cleaned, None


def _rank_contacts(query, contacts, limit=10):
    cands = _name_candidates(query)
    ranked = []
    for c in contacts:
        name = c.get("name") or ""
        best = max((_name_score(cand, name) for cand in cands), default=0.0)
        for num in c.get("numbers") or []:
            best = max(best, _name_score(_norm_name(query), num))
        if best >= 0.30:
            ranked.append((best, c))
    ranked.sort(key=lambda x: -x[0])
    return ranked[:limit]


def contact_lookup(query="", limit=10, fuzzy=True):
    """Search real contacts, with fuzzy/phonetic matching for misspelled names."""
    contacts, err = _fetch_contacts()
    if err:
        return "ERROR: " + err
    if not contacts:
        return "Contacts are empty."
    q = str(query or "").strip()
    if not q:
        lines = ["- %s: %s" % (c["name"] or "(no name)",
                               ", ".join(c["numbers"]) or "(no number)")
                 for c in contacts[:limit]]
        return "All contacts:\n" + "\n".join(lines)
    ranked = _rank_contacts(q, contacts, limit)
    if not ranked:
        # fall back to loose substring so nothing is missed
        for c in contacts:
            if q.lower() in (c["name"] + " " + " ".join(c["numbers"])).lower():
                ranked.append((0.5, c))
    if not ranked:
        return "No contacts found for %r (even with fuzzy matching)." % q
    lines = []
    for score, c in ranked:
        tag = " BEST" if score >= 0.70 else ""
        lines.append("- %s: %s%s [match %.0f%%]" % (
            c["name"] or "(no name)", ", ".join(c["numbers"]) or "(no number)",
            tag, score * 100))
    return "Contacts close to %r:\n%s" % (q, "\n".join(lines))


def resolve_contact(value, threshold=0.62):
    """Turn a name (even misspelled) into a number; pass numbers straight through."""
    v = str(value or "").strip()
    if not v:
        return None, "ERROR: no name or number given."
    if re.fullmatch(r"[+\d][\d\s()\-]{2,}", v):
        return re.sub(r"[^\d+]", "", v), ""
    contacts, err = _fetch_contacts()
    if err:
        return None, "ERROR: " + err
    ranked = _rank_contacts(v, contacts, limit=5)
    if not ranked:
        return None, "No contact close to %r was found." % v
    best_score, best = ranked[0]
    tied = [c for score, c in ranked if score >= best_score - 0.04]
    nums = [n for n in best.get("numbers") or [] if len(re.sub(r"\D", "", n)) >= 7]
    if not nums:
        return None, "I found %s but there is no number saved." % (best.get("name") or v)
    if len(tied) > 1 and best_score < 0.85:
        names = ", ".join(c.get("name") or "?" for c in tied)
        return None, "Multiple close contacts: %s. Which one?" % names
    if best_score < threshold:
        return None, ("Closest contact is %s (%.0f%% match, %s) - confirm before calling."
                      % (best.get("name"), best_score * 100, nums[0]))
    return re.sub(r"[^\d+]", "", nums[0]), ""


def call_number(number, label=""):
    """Place a real call when Termux:API has CALL_PHONE, else open the dialer."""
    num = re.sub(r"[^\d+]", "", str(number or ""))
    who = label or num
    if len(re.sub(r"\D", "", num)) < 3:
        return "ERROR: incomplete phone number for %s." % who
    cli = ["termux-telephony-call", num] if _api_available("termux-telephony-call") else None
    rc, out, err = termux_api("TelephonyCall", [("--es", "number", num)],
                              cli=cli, timeout=15)
    if rc == 0:
        return "Calling %s (%s) now." % (who, num)
    rc, out, err = run(["am", "start", "-a", "android.intent.action.DIAL",
                        "-d", "tel:" + num], timeout=20)
    note = (err or out or "")[:100]
    return ("Dialer opened for %s (%s) - tap the call button. Real call via API "
            "failed%s" % (who, num, (": " + note) if note else ".")) if rc == 0 \
        else "ERROR: could not open dialer (%s)." % (err or out)


def send_sms_real(number, message):
    """Actually send an SMS when Termux:API has SEND_SMS, else leave a draft."""
    num = re.sub(r"[^\d+]", "", str(number or ""))
    msg = str(message or "")[:1500]
    if len(re.sub(r"\D", "", num)) < 3 or not msg:
        return "ERROR: need a valid number and message."
    cli = ["termux-sms-send", "-n", num, msg] if _api_available("termux-sms-send") else None
    rc, out, err = termux_api("SmsSend", [("--esa", "recipients", num)],
                              stdin_text=msg, cli=cli, timeout=20)
    if rc == 0:
        return "SMS sent to %s." % num
    rc, out, err = run(["am", "start", "-a", "android.intent.action.SENDTO",
                        "-d", "sms:" + num, "--es", "sms_body", msg,
                        "--ez", "exit_on_sent", "true"], timeout=20)
    note = (err or out or "")[:100]
    return ("Messages opened with a draft to %s - tap send. Direct send failed%s"
            % (num, (": " + note) if note else ".")) if rc == 0 \
        else "ERROR: could not open Messages (%s)." % (err or out)

def add_calendar_event(title, date, time_str="09:00"):
    rc, out, err = run(["am", "start", "-a", "android.intent.action.INSERT",
                        "-t", "vnd.android.cursor.item/event",
                        "--es", "title", str(title)[:120],
                        "--es", "beginTime", str(date) + " " + str(time_str)], timeout=20)
    if rc != 0:
        rc, out, err = run(["am", "start", "-n", "com.android.calendar/.AllInOneActivity"], timeout=20)
    return "Opened calendar to add '%s'." % str(title)[:60] if rc == 0 else "ERROR: %s" % (err or out)

def find_phone():
    for i in range(5):
        run(["termux-vibrate", "-d", "800"], timeout=5)
        speak_async("Anas, I am here. " * 2)
        run(["termux-notification", "--title", "Jarvis", "--content",
             "Find my phone triggered", "--id", "99999", "--priority", "max"], timeout=10)
        time.sleep(1.5)
    return "Ringing and vibrating. Check your phone."

def sos_flash():
    for _ in range(6):
        run(["termux-torch", "on"], timeout=5)
        time.sleep(0.3)
        run(["termux-torch", "off"], timeout=5)
        time.sleep(0.3)
    return "SOS flashed."

def emergency_call():
    rc, out, err = run(["am", "start", "-a", "android.intent.action.DIAL",
                        "-d", "tel:112"], timeout=20)
    return "Dialer opened for 112 (emergency)." if rc == 0 else "ERROR: %s" % (err or out)

def take_photo():
    rc, out, err = run(["am", "start", "-a", "android.media.action.IMAGE_CAPTURE"], timeout=20)
    if rc != 0:
        rc, out, err = run(["am", "start", "-n", "com.sec.android.app.camera/.Camera"], timeout=20)
    return "Camera opened." if rc == 0 else "ERROR: %s" % (err or out)

def scan_qr():
    rc, out, err = run(["am", "start", "-a", "android.intent.action.VIEW",
                        "-d", "https://lens.google.com"], timeout=20)
    return "Opened Google Lens for QR/barcode scan." if rc == 0 else "ERROR: %s" % (err or out)

def download_file(url):
    if not url.lower().startswith(("http://", "https://")):
        return "ERROR: only http(s) URLs."
    os.makedirs("/sdcard/Download", exist_ok=True)
    name = os.path.basename(urllib.parse.urlparse(url).path) or "download.bin"
    path = "/sdcard/Download/" + name
    rc, out, err = run(["wget", "-O", path, url], timeout=120)
    if rc != 0:
        return "ERROR: download failed (%s)." % (err or out)
    return "Downloaded to %s." % path

def list_files(path="~"):
    p = os.path.expanduser(path)
    try:
        entries = sorted(os.listdir(p))
    except Exception as e:
        return "ERROR: %s" % e
    out = []
    for e in entries[:60]:
        full = os.path.join(p, e)
        tag = "/" if os.path.isdir(full) else ""
        out.append(e + tag)
    return ("%s (%d entries):\n" % (p, len(entries))) + "\n".join(out)

def read_text_file(path):
    p = os.path.expanduser(path)
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()[:8000]
    except Exception as e:
        return "ERROR: %s" % e

def write_text_file(path, content):
    p = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return "Wrote %d bytes to %s." % (len(content), p)
    except Exception as e:
        return "ERROR: %s" % e

def random_choice(options):
    opts = [o.strip() for o in str(options).split(",") if o.strip()]
    if not opts:
        return "ERROR: give comma-separated options."
    return "Choice: " + random.choice(opts)

def roll_dice(sides=6, count=1):
    try:
        s = max(2, min(1000, int(sides)))
        c = max(1, min(20, int(count)))
    except Exception:
        return "ERROR: sides/count must be numbers."
    rolls = [random.randint(1, s) for _ in range(c)]
    return "Rolled %s: %s (total %d)" % (c, ", ".join(map(str, rolls)), sum(rolls))

def flip_coin():
    return "Heads" if random.random() < 0.5 else "Tails"

def open_app_store(app):
    if app:
        url = "https://play.google.com/store/search?q=" + urllib.parse.quote(str(app)) + "&c=apps"
    else:
        url = "https://play.google.com/store"
    return open_url(url)

def _load_items(path):
    return load_list(path)

def _save_items(path, items):
    save_list(path, items)

def note_add(text):
    items = _load_items(NOTES_PATH)
    items.append({"id": len(items) + 1, "text": str(text)[:500], "ts": now_str()})
    _save_items(NOTES_PATH, items)
    return "Note saved (id %d)." % items[-1]["id"]

def note_list():
    items = _load_items(NOTES_PATH)
    if not items:
        return "No notes."
    return "\n".join("- [%d] %s (%s)" % (n["id"], n["text"], n["ts"]) for n in items)

def note_delete(nid):
    items = _load_items(NOTES_PATH)
    new = [n for n in items if n.get("id") != int(nid)]
    if len(new) == len(items):
        return "No note with id %s." % nid
    _save_items(NOTES_PATH, new)
    return "Deleted note %s." % nid

def todo_add(text):
    items = _load_items(TODOS_PATH)
    items.append({"id": len(items) + 1, "text": str(text)[:300], "done": False})
    _save_items(TODOS_PATH, items)
    return "Added todo (id %d): %s" % (items[-1]["id"], items[-1]["text"])

def todo_list():
    items = _load_items(TODOS_PATH)
    if not items:
        return "No todos."
    out = []
    for t in items:
        mark = "x" if t.get("done") else " "
        out.append("- [%s] %d: %s" % (mark, t["id"], t["text"]))
    return "\n".join(out)

def todo_done(nid):
    items = _load_items(TODOS_PATH)
    for t in items:
        if t.get("id") == int(nid):
            t["done"] = True
            _save_items(TODOS_PATH, items)
            return "Marked done: %s" % t["text"]
    return "No todo with id %s." % nid

def todo_clear():
    _save_items(TODOS_PATH, [])
    return "All todos cleared."

def shopping_add(text):
    items = _load_items(SHOPPING_PATH)
    items.append({"id": len(items) + 1, "text": str(text)[:200], "done": False})
    _save_items(SHOPPING_PATH, items)
    return "Added to shopping list (id %d): %s" % (items[-1]["id"], items[-1]["text"])

def shopping_list():
    items = _load_items(SHOPPING_PATH)
    if not items:
        return "Shopping list is empty."
    out = []
    for s in items:
        mark = "x" if s.get("done") else " "
        out.append("- [%s] %d: %s" % (mark, s["id"], s["text"]))
    return "\n".join(out)

def shopping_clear():
    _save_items(SHOPPING_PATH, [])
    return "Shopping list cleared."

def expense_add(amount, category, note=""):
    try:
        a = float(amount)
    except Exception:
        return "ERROR: amount must be a number."
    items = _load_items(EXPENSES_PATH)
    items.append({"id": len(items) + 1, "amount": a, "category": str(category)[:60],
                  "note": str(note)[:120], "ts": now_str()})
    _save_items(EXPENSES_PATH, items)
    return "Recorded expense: %.2f (%s)." % (a, category)

def expense_list(limit=10):
    items = _load_items(EXPENSES_PATH)
    if not items:
        return "No expenses recorded."
    out = []
    for e in items[-int(limit):]:
        out.append("- %.2f  %s  %s" % (e["amount"], e["category"], e.get("note", "")))
    return "\n".join(out)

def expense_summary():
    items = _load_items(EXPENSES_PATH)
    if not items:
        return "No expenses recorded."
    total = sum(e.get("amount", 0) for e in items)
    by_cat = {}
    for e in items:
        by_cat[e.get("category", "?")] = by_cat.get(e.get("category", "?"), 0) + e.get("amount", 0)
    lines = ["Total: %.2f (%d entries)" % (total, len(items))]
    for c, a in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append("  %s: %.2f" % (c, a))
    return "\n".join(lines)

def voice_chat_loop(j):
    print(dim("Voice chat mode. Speak after the beep; say 'stop' or 'exit' to quit."))
    j.voice_confirm_callback = lambda _prompt: listen_once(timeout=15)
    speak_blocking("Voice chat active. I am listening, Anas.")
    misses = 0
    while True:
        print(dim("Listening..."))
        text = listen_once(timeout=45)
        if not text:
            misses += 1
            print(dim("(no speech detected)"))
            if misses in (3, 6):
                speak_async("I am not hearing you. Say something, or type /exit.")
            continue
        misses = 0
        print(cyan("You > ") + text)
        low = text.lower().strip(" .!?")
        if low in ("stop", "exit", "quit", "bye", "goodbye", "jarvis stop"):
            speak_blocking("Goodbye, Anas.")
            print(dim("Voice chat ended."))
            break
        try:
            handled, answer = fast_voice_command(text, j)
            if not handled:
                answer = j.ask(text)
        except Exception as e:
            answer = "Sorry, something went wrong: " + str(e)[:200]
        print(green("Jarvis > ") + answer)
        speak_blocking(answer)


def ears_loop(j, wake_word=True, stop_file=None):
    """Always-on ears: hear, wake, answer out loud, keep listening."""
    stop_file = stop_file or os.path.join(BASE, "stop_ears")
    try:
        if os.path.exists(stop_file):
            os.remove(stop_file)
    except Exception:
        pass
    mode = "Wake word on" if wake_word else "Always listening"
    j.voice_confirm_callback = lambda _prompt: listen_once(timeout=15)
    print(dim("Ears mode. " + mode + ". Say 'stop listening' to end."))
    speak_blocking("Ears online. " + mode + ", Anas.")
    post_notification("Jarvis ears online", mode + ". Say 'stop listening' to end.")
    misses = 0
    while True:
        try:
            if os.path.exists(stop_file):
                print(dim("Ears stopped by stop file."))
                break
            text = listen_once(timeout=45)
            if not text:
                misses += 1
                if misses in (3, 6):
                    speak_async("I am not hearing you. Check the microphone permission.")
                continue
            misses = 0
            low = clean_voice_text(text).lower()
            if low in ("stop listening", "ears off", "jarvis stop listening",
                       "stop", "exit", "quit", "goodbye"):
                speak_blocking("Ears offline, Anas.")
                print(dim("Ears offline."))
                break
            if wake_word and not has_wake_word(text):
                print(dim("(heard, no wake word) " + text[:100]))
                continue
            question = strip_wake_word(text) if wake_word else text
            if not question:
                speak_async("Yes?")
                continue
            print(cyan("You > ") + question)
            try:
                handled, answer = fast_voice_command(question, j)
                if not handled:
                    answer = j.ask(question)
            except Exception as exc:
                answer = "Sorry, something went wrong: " + str(exc)[:180]
            print(green("Jarvis > ") + answer)
            speak_blocking(answer)
        except KeyboardInterrupt:
            speak_blocking("Ears offline, Anas.")
            print(dim("Ears offline."))
            break
        except Exception as exc:
            print(dim("ears error: " + repr(exc)[:160]))
            time.sleep(2)
    try:
        post_notification("Jarvis ears offline", "Voice listening has stopped.")
    except Exception:
        pass

# ---------------------------------------------------------------- RAG / memory brain

def _tokenize(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))

def store_conversation(q, a):
    try:
        os.makedirs(BASE, exist_ok=True)
        with open(CONVERSATIONS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"q": q, "a": a, "ts": now_str()}, ensure_ascii=False) + "\n")
    except Exception:
        pass

def retrieve_context(query, k=3):
    if not os.path.exists(CONVERSATIONS_PATH):
        return ""
    lines = []
    try:
        with open(CONVERSATIONS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception:
        return ""
    if not lines:
        return ""
    qtoks = _tokenize(query)
    scored = []
    for ln in lines[-200:]:  # last 200 conversations
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        toks = _tokenize(obj.get("q", "") + " " + obj.get("a", ""))
        overlap = len(qtoks & toks)
        if overlap > 0:
            scored.append((overlap, obj))
    scored.sort(key=lambda x: -x[0])
    out = []
    for _, obj in scored[:k]:
        out.append("Q: %s\nA: %s" % (obj.get("q", "")[:200], obj.get("a", "")[:300]))
    return "\n---\n".join(out)

def store_knowledge(text, tag=""):
    try:
        os.makedirs(BASE, exist_ok=True)
        with open(KNOWLEDGE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"text": text, "tag": tag, "ts": now_str()}, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False

def retrieve_knowledge(query, k=3):
    if not os.path.exists(KNOWLEDGE_PATH):
        return ""
    lines = []
    try:
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception:
        return ""
    qtoks = _tokenize(query)
    scored = []
    for ln in lines:
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        toks = _tokenize(obj.get("text", "") + " " + obj.get("tag", ""))
        overlap = len(qtoks & toks)
        if overlap > 0:
            scored.append((overlap, obj))
    scored.sort(key=lambda x: -x[0])
    out = [o.get("text", "")[:400] for _, o in scored[:k]]
    return "\n---\n".join(out)

import math
import re
import json
import os
from collections import Counter, defaultdict

# ---- TF-IDF + cosine similarity for RAG ----

def _tokenize(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())

def _tfidf_vectors(docs):
    """Compute TF-IDF vectors for a list of documents. Returns (vectors, idf)."""
    N = len(docs)
    if N == 0:
        return [], {}
    # document frequency
    df = Counter()
    tokenized = [_tokenize(d) for d in docs]
    for toks in tokenized:
        for t in set(toks):
            df[t] += 1
    idf = {}
    for t, f in df.items():
        idf[t] = math.log((N + 1) / (f + 1)) + 1.0
    vectors = []
    for toks in tokenized:
        tf = Counter(toks)
        total = len(toks) if toks else 1
        vec = {}
        for t, count in tf.items():
            vec[t] = (count / total) * idf.get(t, 1.0)
        vectors.append(vec)
    return vectors, idf

def _cosine(a, b):
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

def retrieve_context(query, k=5, recency_weight=0.3):
    """Enhanced RAG: TF-IDF cosine similarity + recency decay."""
    if not os.path.exists(CONVERSATIONS_PATH):
        return ""
    lines = []
    try:
        with open(CONVERSATIONS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception:
        return ""
    if not lines:
        return ""
    # parse entries
    entries = []
    for ln in lines[-500:]:
        try:
            obj = json.loads(ln)
            entries.append(obj)
        except Exception:
            continue
    if not entries:
        return ""
    docs = [e.get("q", "") + " " + e.get("a", "") for e in entries]
    vectors, idf = _tfidf_vectors(docs + [query])
    qvec = vectors[-1]
    docvecs = vectors[:-1]
    # score each with recency decay
    n = len(entries)
    scored = []
    for i, (entry, vec) in enumerate(zip(entries, docvecs)):
        sim = _cosine(qvec, vec)
        recency = (i + 1) / n  # 0..1, newer = higher
        score = sim * (1 - recency_weight) + recency * recency_weight
        if score > 0.05:
            scored.append((score, entry))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, entry in scored[:k]:
        out.append("Q: %s\nA: %s" % (entry.get("q", "")[:250], entry.get("a", "")[:400]))
    return "\n---\n".join(out)

def retrieve_knowledge(query, k=5):
    if not os.path.exists(KNOWLEDGE_PATH):
        return ""
    lines = []
    try:
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception:
        return ""
    if not lines:
        return ""
    entries = []
    for ln in lines:
        try:
            entries.append(json.loads(ln))
        except Exception:
            continue
    if not entries:
        return ""
    docs = [e.get("text", "") + " " + e.get("tag", "") for e in entries]
    vectors, idf = _tfidf_vectors(docs + [query])
    qvec = vectors[-1]
    docvecs = vectors[:-1]
    scored = []
    for entry, vec in zip(entries, docvecs):
        sim = _cosine(qvec, vec)
        if sim > 0.05:
            scored.append((sim, entry))
    scored.sort(key=lambda x: -x[0])
    out = [e.get("text", "")[:500] for _, e in scored[:k]]
    return "\n---\n".join(out)

# ---- Knowledge graph ----

GRAPH_PATH = os.path.join(BASE, "knowledge_graph.json")

def _load_graph():
    return load_json(GRAPH_PATH, {"entities": {}, "relations": []})

def _save_graph(g):
    save_json(GRAPH_PATH, g)

def add_entity(name, etype="concept", props=None):
    g = _load_graph()
    name = name.strip().lower()
    if name not in g["entities"]:
        g["entities"][name] = {"type": etype, "props": props or {}, "mentions": 1}
    else:
        g["entities"][name]["mentions"] += 1
        if props:
            g["entities"][name]["props"].update(props)
    _save_graph(g)
    return name

def add_relation(subj, pred, obj):
    g = _load_graph()
    subj = subj.strip().lower()
    obj = obj.strip().lower()
    # ensure entities exist
    if subj not in g["entities"]:
        g["entities"][subj] = {"type": "concept", "props": {}, "mentions": 1}
    if obj not in g["entities"]:
        g["entities"][obj] = {"type": "concept", "props": {}, "mentions": 1}
    g["relations"].append({"subj": subj, "pred": pred, "obj": obj})
    # dedup
    seen = set()
    uniq = []
    for r in g["relations"]:
        key = (r["subj"], r["pred"], r["obj"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    g["relations"] = uniq
    _save_graph(g)

def query_graph(entity):
    g = _load_graph()
    entity = entity.strip().lower()
    if entity not in g["entities"]:
        return "No knowledge about '%s'." % entity
    info = g["entities"][entity]
    rels = [r for r in g["relations"] if r["subj"] == entity or r["obj"] == entity]
    out = ["%s (%s, mentioned %dx)" % (entity, info.get("type", "concept"), info.get("mentions", 1))]
    if info.get("props"):
        out.append("Properties: " + ", ".join("%s=%s" % (k, v) for k, v in info["props"].items()))
    for r in rels[:15]:
        if r["subj"] == entity:
            out.append("  -> %s -> %s" % (r["pred"], r["obj"]))
        else:
            out.append("  <- %s <- %s" % (r["pred"], r["subj"]))
    return "\n".join(out)

def graph_stats():
    g = _load_graph()
    return "Knowledge graph: %d entities, %d relations." % (len(g["entities"]), len(g["relations"]))

# ---- Episodic memory ----

EPISODES_PATH = os.path.join(BASE, "episodes.jsonl")

def store_episode(event, context="", outcome=""):
    try:
        os.makedirs(BASE, exist_ok=True)
        with open(EPISODES_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": event, "context": context, "outcome": outcome,
                                "ts": now_str()}, ensure_ascii=False) + "\n")
    except Exception:
        pass

def retrieve_episodes(query, k=3):
    if not os.path.exists(EPISODES_PATH):
        return ""
    lines = []
    try:
        with open(EPISODES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception:
        return ""
    entries = []
    for ln in lines[-200:]:
        try:
            entries.append(json.loads(ln))
        except Exception:
            continue
    if not entries:
        return ""
    docs = [e.get("event", "") + " " + e.get("context", "") for e in entries]
    vectors, _ = _tfidf_vectors(docs + [query])
    qvec = vectors[-1]
    docvecs = vectors[:-1]
    scored = []
    for entry, vec in zip(entries, docvecs):
        sim = _cosine(qvec, vec)
        if sim > 0.05:
            scored.append((sim, entry))
    scored.sort(key=lambda x: -x[0])
    out = []
    for _, e in scored[:k]:
        out.append("[%s] %s" % (e.get("ts", ""), e.get("event", "")))
    return "\n".join(out)

# ---- Planning ----

def plan_task(task):
    """Break a task into steps using heuristics + tool awareness."""
    task_l = task.lower()
    steps = []
    # detect multi-step patterns
    if " and " in task_l or " then " in task_l or "," in task_l:
        # split on conjunctions
        parts = re.split(r"\band\b|\bthen\b|,", task_l)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) > 1:
            steps = ["Step %d: %s" % (i + 1, p) for i, p in enumerate(parts)]
    if not steps:
        steps = ["Step 1: " + task]
    return steps

# ---- Self-reflection ----

def reflect(answer, query):
    """Simple heuristic reflection: check length, tool usage, hedging."""
    issues = []
    if len(answer) < 20:
        issues.append("answer too short")
    if "i don't know" in answer.lower() or "i'm not sure" in answer.lower():
        issues.append("uncertain")
    if "error" in answer.lower():
        issues.append("contains error")
    return issues

def auto_update():
    src_dir = "/sdcard/jarvis_pkg"
    dst_dir = BASE
    if not os.path.isdir(src_dir):
        return
    try:
        src_jarvis = os.path.join(src_dir, "jarvis.py")
        dst_jarvis = os.path.join(dst_dir, "jarvis.py")
        if os.path.exists(src_jarvis):
            src_mtime = os.path.getmtime(src_jarvis)
            dst_mtime = os.path.getmtime(dst_jarvis) if os.path.exists(dst_jarvis) else 0
            if src_mtime > dst_mtime:
                import shutil as _sh
                _sh.copy2(src_jarvis, dst_jarvis)
                for fn in ("jarvisd.py",):
                    s = os.path.join(src_dir, fn)
                    d = os.path.join(dst_dir, fn)
                    if os.path.exists(s):
                        _sh.copy2(s, d)
                src_anas = os.path.join(src_dir, "anas")
                prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
                dst_anas = os.path.join(prefix, "bin", "anas")
                if os.path.exists(src_anas):
                    _sh.copy2(src_anas, dst_anas)
                    os.chmod(dst_anas, 0o755)
                src_boot = os.path.join(src_dir, "boot.sh")
                if os.path.exists(src_boot):
                    boot_dir = os.path.join(os.path.expanduser("~"), ".termux", "boot")
                    os.makedirs(boot_dir, exist_ok=True)
                    _sh.copy2(src_boot, os.path.join(boot_dir, "00-jarvis.sh"))
                    os.chmod(os.path.join(boot_dir, "00-jarvis.sh"), 0o700)
    except Exception:
        pass

# ---------------------------------------------------------------- assistant

# ---------------------------------------------------------------- super mode
WORLD_ZONES = {
    "delhi": "Asia/Kolkata", "new delhi": "Asia/Kolkata", "mumbai": "Asia/Kolkata",
    "bangalore": "Asia/Kolkata", "bengaluru": "Asia/Kolkata", "chennai": "Asia/Kolkata",
    "hyderabad": "Asia/Kolkata", "kolkata": "Asia/Kolkata", "pune": "Asia/Kolkata",
    "goa": "Asia/Kolkata", "london": "Europe/London", "new york": "America/New_York",
    "los angeles": "America/Los_Angeles", "chicago": "America/Chicago",
    "toronto": "America/Toronto", "tokyo": "Asia/Tokyo", "sydney": "Australia/Sydney",
    "dubai": "Asia/Dubai", "singapore": "Asia/Singapore", "paris": "Europe/Paris",
    "berlin": "Europe/Berlin", "moscow": "Europe/Moscow", "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai", "karachi": "Asia/Karachi", "dhaka": "Asia/Dhaka",
    "kathmandu": "Asia/Kathmandu", "colombo": "Asia/Colombo",
}


def translate_text(text, to="hi"):
    """Real translation with a Google Translate link as the final fallback."""
    text = str(text or "").strip()
    if not text:
        return "ERROR: no text to translate."
    link = translate_url(text, to)
    try:
        url = ("https://translate.googleapis.com/translate_a/single?client=gtx"
               "&sl=auto&tl=%s&dt=t&q=%s" % (
                   urllib.parse.quote(str(to or "hi")), urllib.parse.quote(text)))
        data = free_json(url, timeout=12)
        chunks = data[0] if isinstance(data, list) and data else []
        out = "".join(c[0] for c in chunks
                      if isinstance(c, list) and c and isinstance(c[0], str))
        if out.strip():
            return out.strip()
    except Exception:
        pass
    return "Translation page: " + link


def ip_info():
    """Public IP, city and ISP from two free providers."""
    providers = ("https://ipinfo.io/json", "https://ipapi.co/json/")
    for url in providers:
        try:
            d = free_json(url, timeout=10)
            ip = d.get("ip") or d.get("query") or ""
            if not ip:
                continue
            city = d.get("city") or ""
            region = d.get("region") or d.get("region_name") or ""
            country = d.get("country") or d.get("country_name") or ""
            org = (d.get("org") or d.get("asn") or "").split()[-1] if (
                d.get("org") or d.get("asn")) else ""
            loc = d.get("loc") or ""
            parts = ["Public IP: " + str(ip)]
            place = ", ".join(x for x in (city, region, country) if x)
            if place:
                parts.append("Location: " + place)
            if org:
                parts.append("ISP: " + str(org))
            if loc:
                parts.append("Coordinates: " + str(loc))
            return "\n".join(parts)
        except Exception:
            continue
    return "ERROR: could not determine public IP."


def net_speed(bytes_to_read=1000000):
    """Small real download speed check with two free fallback endpoints."""
    size = int(bytes_to_read)
    urls = (
        "https://speed.cloudflare.com/__down?bytes=%d" % size,
        "https://httpbin.org/bytes/%d" % size,
        "https://proof.ovh.net/files/1Mb.dat",
    )
    last_error = ""
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            started = time.time()
            with urllib.request.urlopen(req, timeout=25) as response:
                payload = response.read()
            if not payload:
                raise ValueError("empty response")
            elapsed = max(0.001, time.time() - started)
            mbps = (len(payload) * 8) / elapsed / 1000000.0
            return ("Download: %.2f Mbps (%d bytes in %.2fs) via %s" %
                    (mbps, len(payload), elapsed,
                     urllib.parse.urlparse(url).netloc))
        except Exception as exc:
            last_error = str(exc)[:120]
            continue
    return "ERROR: speed test failed: %s" % last_error


def world_time(city=""):
    key = str(city or "").strip().lower()
    if not key:
        key = "delhi"
    zone = WORLD_ZONES.get(key)
    if not zone:
        for name, candidate in WORLD_ZONES.items():
            if key in name or name in key:
                zone = candidate
                break
    if not zone:
        return "ERROR: unknown city. Try: " + ", ".join(
            sorted(set(WORLD_ZONES))[:14])
    try:
        from zoneinfo import ZoneInfo
        now = datetime.datetime.now(ZoneInfo(zone))
        return "%s: %s (%s)" % (
            str(city or zone).title(), now.strftime("%I:%M %p, %A %d %B %Y"), zone)
    except Exception:
        try:
            d = free_json("https://timeapi.io/api/Time/current/zone?timeZone=" +
                          urllib.parse.quote(zone), timeout=10)
            return "%s: %s" % (zone, d.get("dateTime") or d.get("time") or d)
        except Exception as exc:
            return "ERROR: time lookup failed: %s" % str(exc)[:150]


def summarize_url(url, sentences=5):
    """Extractive summary of a page, no extra API key required."""
    page = read_page(url)
    if page.startswith("ERROR"):
        return page
    lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
    body = "\n".join(ln for ln in lines
                     if not ln.startswith("Page:") and not ln.startswith("URL:"))
    parts = re.split(r"(?<=[.!?])\s+", body)
    parts = [re.sub(r"\s+", " ", p).strip() for p in parts if len(p.split()) >= 4]
    if not parts:
        return "Summary: page has no readable text."
    stop = set(FILLER_WORDS) | {
        "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
        "have", "has", "had", "its", "their", "they", "you", "your", "our", "but",
        "not", "can", "will", "into", "about", "more", "also", "than", "then", "when",
    }
    words = [w for w in re.findall(r"[a-z0-9]+", body.lower()) if w not in stop]
    freq = Counter(words)
    scored = []
    for idx, sentence in enumerate(parts):
        score = sum(freq.get(w, 0) for w in re.findall(r"[a-z0-9]+", sentence.lower()))
        score = score / max(1, (len(sentence.split()) ** 0.5))
        scored.append((score, idx, sentence))
    best = sorted(scored, reverse=True)[:max(1, int(sentences))]
    best.sort(key=lambda item: item[1])
    title = lines[0] if lines and lines[0].startswith("Page:") else str(url)
    return "Summary of %s:\n%s" % (
        title.replace("Page: ", ""), "\n".join("- " + x[2] for x in best))


def share_content(text="", path="", action="view", title=""):
    """Use the Android share sheet through the direct Termux:API protocol."""
    action = str(action or "view").lower()
    if action not in ("view", "send", "edit"):
        return "ERROR: action must be view, send or edit."
    extras = [("--es", "action", action)]
    cli = ["termux-share", "-a", action]
    if title:
        extras.append(("--es", "title", str(title)))
        cli += ["-t", str(title)]
    stdin_text = ""
    if path:
        full = os.path.realpath(os.path.expanduser(str(path)))
        if not os.path.isfile(full):
            return "ERROR: file not found: %s" % path
        extras.append(("--es", "file", full))
        cli.append(full)
    else:
        stdin_text = str(text or "")
        if not stdin_text.strip():
            return "ERROR: no text or file to share."
    rc, out, err = termux_api("Share", extras, stdin_text=stdin_text,
                              cli=cli, timeout=15)
    return "Share sheet opened." if rc == 0 else (
        "ERROR: share failed (%s)" % (err or out or "no response")[:150])


def _json_call(method, cli, extras=None, timeout=12):
    rc, out, err = termux_api(method, extras or [], cli=cli, timeout=timeout)
    if rc != 0:
        return None, (err or out or "no response")
    try:
        return json.loads(out), ""
    except Exception:
        return None, "unexpected response: %s" % (out or "")[:150]


def device_info():
    d, err = _json_call("TelephonyDeviceInfo", ["termux-telephony-deviceinfo"])
    if err:
        return "ERROR: " + err
    keys = ("device", "brand", "model", "product", "android_version", "sdk",
            "release", "board", "hardware", "cpu_abi")
    lines = ["%s: %s" % (k.replace("_", " ").title(), d.get(k))
             for k in keys if d.get(k)]
    return "Device info:\n" + ("\n".join(lines) if lines else str(d)[:600])


def call_log(limit=10, offset=0):
    try:
        lim = max(1, min(50, int(limit)))
        off = max(0, int(offset))
    except Exception:
        return "ERROR: limit and offset must be numbers."
    extras = [("--ei", "offset", str(off)), ("--ei", "limit", str(lim))]
    cli = ["termux-call-log", "-l", str(lim), "-o", str(off)]
    d, err = _json_call("CallLog", cli, extras)
    if err:
        return "ERROR: " + err
    if not isinstance(d, list) or not d:
        return "Call log is empty."
    lines = []
    for item in d[:lim]:
        if not isinstance(item, dict):
            continue
        who = item.get("name") or item.get("number") or "?"
        num = item.get("number") or ""
        kind = item.get("type") or item.get("call_type") or "?"
        date = item.get("date") or ""
        dur = item.get("duration") or ""
        lines.append("- %s | %s | %s | %s%s" % (
            str(kind), who, num, date,
            (" (%ss)" % dur) if dur else ""))
    return "Recent calls:\n" + ("\n".join(lines) if lines else str(d[:3])[:500])


def sms_recent(limit=5, message_type="inbox", address=""):
    types = {"all": 0, "inbox": 1, "sent": 2, "draft": 3,
             "outbox": 4, "failed": 5, "queued": 6}
    kind = str(message_type or "inbox").lower()
    if kind not in types:
        return "ERROR: type must be all/inbox/sent/draft/outbox/failed/queued."
    try:
        lim = max(1, min(30, int(limit)))
    except Exception:
        return "ERROR: limit must be a number."
    extras = [("--ei", "limit", str(lim)), ("--ei", "offset", "0"),
              ("--ei", "type", str(types[kind]))]
    cli = ["termux-sms-list", "-l", str(lim), "-t", kind]
    if address:
        extras.append(("--es", "from", str(address)))
        cli += ["-f", str(address)]
    d, err = _json_call("SmsInbox", cli, extras, timeout=15)
    if err:
        return "ERROR: " + err
    if not isinstance(d, list) or not d:
        return "No %s SMS found." % kind
    lines = []
    for item in d[:lim]:
        if not isinstance(item, dict):
            continue
        who = item.get("address") or item.get("from") or "?"
        body = re.sub(r"\s+", " ", str(item.get("body") or ""))[:160]
        date = item.get("date") or ""
        lines.append("- %s | %s: %s" % (who, date, body))
    return "Recent %s SMS:\n" % kind + ("\n".join(lines) if lines else str(d[:2])[:500])


def notification_list():
    d, err = _json_call("NotificationList", ["termux-notification-list"])
    if err:
        return "ERROR: " + err
    if not isinstance(d, list) or not d:
        return "No active notifications."
    lines = []
    for item in d[:30]:
        if isinstance(item, dict):
            lines.append("- [%s] %s: %s" % (
                item.get("id", "?"), item.get("title", ""),
                re.sub(r"\s+", " ", str(item.get("content") or ""))[:120]))
    return "Active notifications:\n" + ("\n".join(lines) if lines else str(d[:2])[:400])


def notification_remove(nid):
    nid = str(nid or "").strip()
    if not nid:
        return "ERROR: notification id required."
    rc, out, err = termux_api(
        "NotificationRemove", [("--es", "id", nid)],
        cli=["termux-notification-remove", nid], timeout=12)
    return "Notification %s removed." % nid if rc == 0 else (
        "ERROR: could not remove notification (%s)" % (err or out)[:150])


def set_brightness(level="auto"):
    value = str(level).strip().lower()
    if value == "auto":
        extras = [("--ez", "auto", "true")]
    else:
        try:
            num = max(0, min(255, int(value)))
        except Exception:
            return "ERROR: brightness must be 0-255 or auto."
        extras = [("--ei", "brightness", str(num)), ("--ez", "auto", "false")]
        value = str(num)
    rc, out, err = termux_api(
        "Brightness", extras, cli=["termux-brightness", value], timeout=12)
    return "Brightness set to %s." % value if rc == 0 else (
        "ERROR: brightness failed (%s)" % (err or out)[:150])


def device_location(provider="gps", request="once"):
    provider = str(provider or "gps").lower()
    request = str(request or "once").lower()
    if provider not in ("gps", "network", "passive"):
        return "ERROR: provider must be gps, network or passive."
    if request not in ("once", "last", "updates"):
        return "ERROR: request must be once, last or updates."
    extras = [("--es", "provider", provider), ("--es", "request", request)]
    cli = ["termux-location", "-p", provider, "-r", request]
    d, err = _json_call("Location", cli, extras, timeout=30)
    if err:
        return "ERROR: " + err
    if not isinstance(d, dict):
        return "ERROR: unexpected location response."
    lat, lon = d.get("latitude"), d.get("longitude")
    if lat is None or lon is None:
        return "ERROR: no location returned."
    lines = ["Location: %.6f, %.6f" % (float(lat), float(lon))]
    if d.get("accuracy") is not None:
        lines.append("Accuracy: %s m" % d.get("accuracy"))
    lines.append("Maps: https://www.google.com/maps?q=%s,%s" % (lat, lon))
    return "\n".join(lines)


def wifi_info():
    d, err = _json_call("WifiConnectionInfo", ["termux-wifi-connectioninfo"])
    if err:
        return "ERROR: " + err
    keys = ("ssid", "bssid", "ip", "signal", "speed", "frequency_mhz", "link_speed")
    lines = ["%s: %s" % (k.replace("_", " ").title(), d.get(k))
             for k in keys if d.get(k) not in (None, "", 0)]
    return "Wi-Fi:\n" + ("\n".join(lines) if lines else str(d)[:500])


def wifi_scan():
    d, err = _json_call("WifiScanInfo", ["termux-wifi-scaninfo"], timeout=20)
    if err:
        return "ERROR: " + err
    if not isinstance(d, list) or not d:
        return "No Wi-Fi networks in the last scan."
    names = []
    for item in d[:30]:
        if isinstance(item, dict):
            ssid = item.get("ssid") or "Hidden"
            signal = item.get("level") or item.get("signal") or ""
            names.append("- %s%s" % (ssid, (" (%s)" % signal) if signal else ""))
    return "Wi-Fi networks:\n" + ("\n".join(names) if names else str(d[:3])[:400])


def sound_mode(mode="normal"):
    """Best-effort ringer/sound mode: normal, vibrate, silent, loud."""
    key = str(mode or "").lower().strip()
    steps = []
    if key in ("silent", "mute", "quiet"):
        for stream in ("ring", "notification", "system"):
            ok, info = set_volume(stream, 0)
            steps.append("%s=%s" % (stream, ok))
        try:
            run(["cmd", "notification", "set_dnd", "on"], timeout=10)
        except Exception:
            pass
        return "Sound mode silent: " + ", ".join(steps)
    if key in ("vibrate",):
        for stream in ("ring", "notification"):
            ok, info = set_volume(stream, 0)
            steps.append("%s=%s" % (stream, ok))
        run(["termux-vibrate", "-d", "150"], timeout=8)
        return "Sound mode vibrate (best effort): " + ", ".join(steps)
    if key in ("normal", "ring", "ringer"):
        for stream, lvl in (("ring", 7), ("notification", 5), ("system", 5)):
            ok, info = set_volume(stream, lvl)
            steps.append("%s=%s" % (stream, ok))
        try:
            run(["cmd", "notification", "set_dnd", "off"], timeout=10)
        except Exception:
            pass
        return "Sound mode normal: " + ", ".join(steps)
    if key in ("loud", "max"):
        for stream, lvl in (("ring", 15), ("notification", 15), ("alarm", 15), ("music", 12)):
            ok, info = set_volume(stream, lvl)
            steps.append("%s=%s" % (stream, ok))
        return "Sound mode loud: " + ", ".join(steps)
    return "ERROR: mode must be normal, vibrate, silent, or loud."


def read_notifications_aloud(limit=10):
    text = notification_list()
    if text.startswith("ERROR") or text.startswith("No active"):
        return text
    # speak a short version
    speak_async(text[:350].replace("\n", ". "))
    return text


def read_sms_aloud(limit=5):
    text = sms_recent(limit=min(10, max(1, int(limit or 5))))
    if text.startswith("ERROR") or text.startswith("No "):
        return text
    speak_async(text[:350].replace("\n", ". "))
    return text


def run_routine(name):
    """One-command multi-action routines. Never places calls or sends messages."""
    key = re.sub(r"[^a-z ]", "", str(name or "").lower()).strip()
    steps = []

    if key in ("good night", "goodnight", "sleep", "bedtime"):
        steps.append("Torch: " + str(termux_api(
            "Torch", [("--ez", "enabled", "false")],
            cli=["termux-torch", "off"], timeout=12)[0] == 0))
        ok, info = set_volume("music", 1)
        steps.append("Music volume: %s (%s)" % (ok, info))
        ok, info = set_volume("notification", 0)
        steps.append("Notification volume: %s (%s)" % (ok, info))
        ok, info = post_notification("Good night, Anas", "Phone is set for sleep. Rest well.")
        steps.append("Notification: %s" % ok)
    elif key in ("focus", "work", "study"):
        ok, info = set_volume("ring", 0)
        steps.append("Ring volume: %s (%s)" % (ok, info))
        steps.append("Torch: " + str(termux_api(
            "Torch", [("--ez", "enabled", "false")],
            cli=["termux-torch", "off"], timeout=12)[0] == 0))
        ok, info = post_notification("Focus mode", "Distractions reduced. Stay focused, Anas.")
        steps.append("Notification: %s" % ok)
    elif key in ("drive", "driving", "car"):
        ok, info = set_volume("music", 8)
        steps.append("Music volume: %s (%s)" % (ok, info))
        rc, out, err = run(["am", "start", "-a", "android.intent.action.VIEW",
                            "-d", "google.maps://"], timeout=15)
        steps.append("Maps: %s" % (rc == 0))
    elif key in ("morning", "wake up", "wakeup", "wake"):
        steps.append("Battery: " + str(battery_info())[:180])
        steps.append("Time: " + now_str())
        try:
            steps.append("Weather: " + weather(load_config().get("city", "") or "Delhi").split("\n")[0][:120])
        except Exception:
            pass
        try:
            steps.append("News: " + tech_news(2).replace("\n", " ")[:180])
        except Exception:
            pass
    elif key in ("quiet", "silent", "meeting"):
        ok, info = set_volume("ring", 0)
        steps.append("Ring volume: %s (%s)" % (ok, info))
        ok, info = set_volume("notification", 0)
        steps.append("Notification volume: %s (%s)" % (ok, info))
    elif key in ("workout", "exercise", "gym"):
        ok, info = set_volume("music", 12)
        steps.append("Music volume: %s (%s)" % (ok, info))
        ok, info = post_notification("Workout mode", "Let's go, Anas.")
        steps.append("Notification: %s" % ok)
    elif key in ("relax", "chill"):
        ok, info = set_volume("music", 4)
        steps.append("Music volume: %s (%s)" % (ok, info))
        ok, info = set_volume("ring", 3)
        steps.append("Ring volume: %s (%s)" % (ok, info))
    else:
        return ("ERROR: unknown routine %r. Available: goodnight, bedtime, focus, drive, "
                "morning, quiet, workout, relax." % name)
    return "Routine %s:\n%s" % (key.title(), "\n".join("- " + s for s in steps))


def self_test_summary(quick=True):
    """Run selftest.py and return a short, redacted summary."""
    path = os.path.join(BASE, "selftest.py")
    if not os.path.isfile(path):
        return "ERROR: selftest.py is not installed."
    env = os.environ.copy()
    env["JARVIS_SKIP_CHAT"] = "1"
    env["JARVIS_SELFTEST_QUICK"] = "1" if quick else "0"
    try:
        proc = subprocess.run([sys.executable, path], capture_output=True,
                              text=True, timeout=180, env=env)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except Exception as exc:
        return "ERROR: selftest failed to run: %s" % str(exc)[:150]
    report_path = os.path.join(BASE, "selftest_report.json")
    try:
        with open(report_path, encoding="utf-8") as handle:
            data = json.load(handle)
        summary = data.get("summary", {})
        failed = [r["name"] for r in data.get("results", []) if not r.get("ok")]
        return ("Self-test: %s/%s passed, %s failed, %s skipped.\n"
                "Failed: %s\nReport: %s\n%s" % (
                    summary.get("passed", 0), summary.get("total", 0),
                    summary.get("failed", 0), summary.get("skipped", 0),
                    ", ".join(failed) or "none", report_path, out[:400]))
    except Exception:
        return "Self-test finished: " + out[:600]


# ------------------------------------------------------------ exhaustive smoke

def _smoke_value(key, typ="string"):
    fixed = {
        "query": "smoke test", "url": "https://example.com", "city": "Delhi",
        "number": "9876543210", "person": "Gaurav Anas", "to": "smoke@example.com",
        "from": "smoke@example.com", "subject": "smoke", "body": "smoke",
        "title": "Smoke", "text": "smoke", "content": "smoke", "message": "smoke",
        "hour": 12, "minute": 30, "seconds": 60, "minutes": 1, "ms": 100,
        "stream": "music", "level": 5, "state": "off", "action": "get",
        "key": "smoke_key", "value": "smoke_value", "panel": "wifi",
        "place": "Delhi", "app": "youtube", "expression": "2+3*4",
        "value": 2, "from_unit": "km", "to_unit": "m", "word": "robot",
        "topic": "Delhi", "coin": "bitcoin", "amount": 1, "frm": "USD",
        "options": "alpha,beta", "date": "2026-11-20", "time": "09:00",
        "address": "smoke@example.com", "app_password": "FAKE-APP-PASSWORD",
        "path": os.path.join(BASE, "README.md"), "question": "What is this?",
        "uid": "1", "id": 1, "name": "quiet", "category": "smoke",
        "note": "smoke", "limit": 2, "count": 1, "provider": "gps",
        "request": "last", "message_type": "inbox", "delay_ms": 0,
        "camera": "0", "sort": "stars", "force": False, "confirmed": False,
        "x": 1, "y": 1, "x2": 2, "y2": 2, "duration": 100, "label": "Smoke",
        "bill": 100, "percent": 10, "people": 1, "unread_only": False,
        "alias": "smoke app",
    }
    if key in fixed:
        return fixed[key]
    if typ == "integer":
        return 1
    if typ == "number":
        return 1
    if typ == "boolean":
        return False
    return "smoke"


def _smoke_args(name, schema):
    overrides = {
        "call_tool": {"name": "note_list", "args": {}},
        "convert": {"value": 1, "from_unit": "km", "to_unit": "m"},
        "tip": {"bill": 100, "percent": 10, "people": 1},
        "ui_action": {"action": "tap", "x": 1, "y": 1, "confirmed": False},
        "media_control": {"action": "pause"},
        "clipboard": {"action": "get"},
        "voice_profile": {"name": "bolt"},
        "quick_command": {"text": "battery"},
        "app_find": {"name": "youtube"},
        "app_open": {"name": "youtube"},
        "app_close": {"name": "youtube"},
        "app_info": {"name": "youtube"},
        "app_alias": {"name": "youtube", "alias": "smoke app"},
        "startup_macro": {"name": "smoke"},
        "smart_alarm": {"hour": 7, "minute": 0, "label": "Wake up", "song": "best"},
        "play_wake_song": {"song": "best"},
        "choose_wake_song": {"mood": "gentle"},
        "sound_mode": {"mode": "silent"},
        "read_notifications": {"limit": 5},
        "read_sms": {"limit": 3},
        "macro_add": {"name": "smoke", "steps": [{"tool": "get_time", "args": {}}]},
        "macro_run": {"name": "smoke"},
        "macro_delete": {"name": "smoke"},
        "sensor_read": {"sensor": "accelerometer", "limit": 1, "delay": 200},
        "wifi_switch": {"enable": False},
        "torch": {"state": "off"},
        "mail_setup": {"address": "smoke@example.com",
                       "app_password": "FAKE-APP-PASSWORD"},
        "take_screenshot": {"delay_ms": 0, "path": os.path.join(BASE, "captures", "smoke.png")},
        "camera_photo": {"camera": "0", "path": os.path.join(BASE, "captures", "smoke.jpg")},
    }
    if name in overrides:
        return dict(overrides[name])
    f = schema.get("function", {})
    props = (f.get("parameters") or {}).get("properties") or {}
    args = {}
    for key in (f.get("parameters") or {}).get("required") or []:
        args[key] = _smoke_value(key, (props.get(key) or {}).get("type", "string"))
    extras = {
        "volume": {"stream": "music", "level": 5},
        "recall": {"key": "smoke_key"},
        "brightness": {"level": "auto"},
        "location": {"provider": "gps", "request": "last"},
        "sms_recent": {"message_type": "inbox"},
        "news": {"topic": "technology", "limit": 2},
        "tech_news": {"limit": 2},
        "mail_inbox": {"count": 1},
        "expense_list": {"limit": 2},
        "share": {"text": "smoke", "action": "view"},
        "see_screen": {"question": "What is on the screen?"},
        "see_camera": {"question": "What do you see?"},
        "world_time": {"city": "London"},
        "daily_briefing": {"city": "Delhi"},
        "open_store": {"app": "youtube"},
        "list_files": {"path": BASE},
        "record_audio": {"seconds": 1},
        "self_test": {"quick": True},
        "analyze_image": {"question": "What is this?"},
    }
    args.update(extras.get(name, {}))
    return args


def smoke_summary(report):
    """Short, redacted text version of an exhaustive smoke report."""
    if not report:
        return "No smoke report is available yet."
    return ("Exhaustive smoke: %d/%d handlers OK, %d safety gates, "
            "%d blocked real actions, %d failed.\nFailures: %s\nReport: %s" % (
                report.get("passed", 0), report.get("total", 0),
                report.get("safety_gates", 0), len(report.get("blocked") or []),
                report.get("failed", 0),
                ", ".join(report.get("failure_names") or []) or "none",
                SMOKE_REPORT_PATH))


def exhaustive_smoke(j=None, verbose=False):
    """Invoke every registered tool handler once with all outside effects stubbed.

    No real call, SMS, email, UI tap, file write, network request, TTS or
    screenshot/camera capture happens. Side-effecting boundaries are replaced
    with deterministic fakes, then restored before returning.
    """
    own_jarvis = j is None
    j = j or Jarvis(interactive=False, auto_confirm=False)
    G = globals()
    MISSING = object()
    saved = {}
    blocked = []
    intercepted = []
    expected_safety = {"ui_action"}

    def patch(name, value):
        if name not in saved:
            saved[name] = G.get(name, MISSING)
        G[name] = value

    def dry(label, prefix="DRYRUN "):
        def fn(*_a, **_k):
            return prefix + label
        return fn

    def block(label):
        def fn(*_a, **_k):
            blocked.append(label)
            return "ERROR: BLOCKED real " + label
        return fn

    def fake_run(cmd, timeout=25, stdin_text=None):
        intercepted.append("run")
        return 0, "DRYRUN run", ""

    def fake_api_call(method, extras=None, stdin_text="", timeout=20):
        intercepted.append("api_call:" + str(method))
        return 0, "DRYRUN " + str(method), ""

    def fake_termux_api(method, extras=None, stdin_text="", cli=None, timeout=20):
        method = str(method)
        intercepted.append("termux_api:" + method)
        json_map = {
            "BatteryStatus": {"percentage": 77, "status": "DISCHARGING",
                              "temperature": 30.0, "health": "GOOD",
                              "plugged": "UNPLUGGED"},
            "Volume": [{"stream": "music", "volume": 5, "max_volume": 15}],
            "TelephonyDeviceInfo": {"device": "DryRun", "brand": "Jarvis",
                                    "model": "Smoke", "android_version": "14"},
            "CallLog": [{"name": "A", "number": "9876543210",
                         "type": "incoming", "date": "today", "duration": 3}],
            "SmsInbox": [{"address": "9876543210", "body": "smoke",
                          "date": "today"}],
            "NotificationList": [{"id": "1", "title": "Smoke", "content": "ok"}],
            "Location": {"latitude": 28.6, "longitude": 77.2, "accuracy": 10},
            "WifiConnectionInfo": {"ssid": "SmokeNet", "ip": "192.168.1.2",
                                   "signal": -50, "link_speed": 100},
            "WifiScanInfo": [{"ssid": "SmokeNet", "level": -50}],
            "CameraInfo": [{"id": 0, "manufacturer": "DryRun",
                            "model": "Cam", "facing": "back"}],
        }
        if method in json_map:
            return 0, json.dumps(json_map[method]), ""
        if method in ("CameraPhoto", "Screenshot"):
            path = ""
            for extra in extras or []:
                if len(extra) >= 3 and extra[1] in ("file", "path"):
                    path = extra[2]
            return 0, path or os.path.join(BASE, "README.md"), ""
        return 0, "DRYRUN " + method, ""

    def fake_diag():
        return {"data_dir": True, "pm_path": "dryrun", "pkg_list": "com.termux.api",
                "api_ok": True, "api_msg": "dryrun", "broadcast_ok": True,
                "direct_ok": True, "termux_packages": "com.termux.api",
                "api_server_pid": "1", "api_server_uid": "1"}

    def fake_contact_lookup(query="", limit=5):
        return "- Gaurav Anas: 9876543210 (dry-run match for %s)" % str(query)[:40]

    def fake_get_volume():
        return [{"stream": "music", "volume": 5, "max_volume": 15}], ""

    real_ui_action = G.get("ui_action")

    def safe_ui_action(*args, **kwargs):
        confirmed = bool(kwargs.get("confirmed", False))
        if not confirmed and len(args) >= 9:
            confirmed = bool(args[8])
        if confirmed:
            blocked.append("ui_action")
            return "ERROR: BLOCKED real UI action"
        return real_ui_action(*args, **kwargs)

    patch("run", fake_run)
    patch("api_call", fake_api_call)
    patch("termux_api", fake_termux_api)
    patch("save_json", lambda *_a, **_k: True)
    patch("_save_items", lambda *_a, **_k: True)
    patch("speak_async", dry("speak_async"))
    patch("speak_blocking", dry("speak_blocking", "DRYRUN blocking "))
    patch("battery_info", lambda: {"percentage": 77, "status": "DISCHARGING",
                                   "temperature": 30.0, "health": "GOOD",
                                   "plugged": "UNPLUGGED"})
    patch("system_info", dry("system_info"))
    patch("get_volume", fake_get_volume)
    patch("set_volume", lambda *_a: (True, "dryrun"))
    patch("termux_api_diagnostics", fake_diag)
    patch("open_url", dry("open_url", "Opened DRYRUN "))
    patch("launch_app", dry("launch_app", "Opened DRYRUN "))
    patch("open_app_store", dry("open app store", "Opened DRYRUN "))
    patch("contact_lookup", fake_contact_lookup)
    patch("resolve_contact", lambda *_a: ("9876543210", ""))
    patch("call_number", block("call"))
    patch("send_sms_real", block("SMS"))
    patch("mail_send", dry("email", "DRYRUN email not sent: "))
    patch("mail_setup", dry("mail setup", "DRYRUN mail setup not changed: "))
    patch("mail_inbox", dry("mail inbox"))
    patch("mail_search", dry("mail search"))
    patch("mail_read", dry("mail read"))
    patch("record_audio", dry("record audio"))
    patch("stop_recording", dry("stop recording"))
    patch("find_phone", dry("find phone"))
    patch("sos_flash", dry("SOS flash"))
    patch("emergency_call", dry("emergency dialer"))
    patch("take_photo", dry("camera photo"))
    patch("scan_qr", dry("QR scan"))
    patch("open_contacts", dry("contacts"))
    patch("add_calendar_event", dry("calendar event"))
    patch("download_file", dry("download"))
    patch("list_files", dry("list files"))
    patch("read_text_file", dry("read file"))
    patch("write_text_file", dry("write file"))
    for n in ("note_add", "note_list", "note_delete", "todo_add", "todo_list",
              "todo_done", "todo_clear", "shopping_add", "shopping_list",
              "shopping_clear", "expense_add", "expense_list", "expense_summary"):
        patch(n, dry(n))
    patch("store_knowledge", lambda *_a, **_k: True)
    patch("retrieve_knowledge", dry("knowledge search"))
    patch("tech_news", dry("tech news"))
    patch("daily_briefing", dry("daily briefing"))
    patch("remind", dry("reminder"))
    patch("smart_alarm", dry("smart alarm", "DRYRUN alarm: "))
    patch("schedule_wake_music", lambda *_a, **_k: (True, "DRYRUN song", 3600))
    patch("_play_wake_song_blocking", dry("wake song", "DRYRUN wake song: "))
    patch("choose_wake_song", lambda *_a, **_k: "DRYRUN best song")
    patch("sound_mode", dry("sound mode"))
    patch("read_notifications_aloud", dry("read notifications"))
    patch("read_sms_aloud", dry("read sms"))
    patch("self_test_summary", dry("self test"))
    for n in ("web_search", "deep_search", "github_search", "wiki_search",
              "read_page", "news", "weather", "joke", "fact", "quote",
              "advice", "define_word", "wiki_summary", "crypto_price",
              "book_search", "currency_convert", "play_music",
              "play_on_youtube", "play_song", "media_control",
              "translate_text", "ip_info", "net_speed", "world_time",
              "summarize_url", "share_content", "analyze_image", "ask_file",
              "ingest_file", "ingest_dir", "list_uploads",
              "macro_add", "macro_list", "macro_run", "macro_delete",
              "wifi_switch", "sensor_list", "sensor_read",
              "tts_engines", "network_quality", "phone_status",
              "set_startup_macro", "refresh_app_catalog"):
        patch(n, dry(n))
    patch("fast_voice_command", lambda *_a, **_k: (True, "DRYRUN quick command"))
    patch("take_screenshot", dry("screenshot", "Screenshot saved: DRYRUN "))
    patch("camera_photo", dry("camera photo", "Photo saved: DRYRUN "))
    patch("ui_action", safe_ui_action)

    old_memory = dict(j.memory)
    results = {}
    try:
        for schema in TOOL_SCHEMAS_FULL:
            name = schema["function"]["name"]
            args = _smoke_args(name, schema)
            try:
                value = j.execute(name, args)
            except Exception as exc:
                value = "ERROR: %s failed: %s" % (name, exc)
            text = str(value)
            safety = ("Cancelled" in text or "No call" in text or "No SMS" in text
                      or "No email draft" in text or name in expected_safety)
            bad_args = text.startswith("ERROR: bad arguments for " + name)
            handler_crash = text.startswith("ERROR: %s failed:" % name)
            error = text.startswith("ERROR")
            ok = bool(text.strip()) and not bad_args and not handler_crash and not (error and not safety)
            results[name] = {
                "ok": ok,
                "safety": bool(safety),
                "detail": text[:180],
                "args": sorted(args.keys()),
            }
            if verbose:
                mark = "OK  " if ok else "FAIL"
                print("  %s %-22s %s" % (mark, name, text[:100]))
    finally:
        j.memory = old_memory
        for name, value in saved.items():
            if value is MISSING:
                G.pop(name, None)
            else:
                G[name] = value

    failures = [n for n, item in results.items() if not item["ok"]]
    report = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "passed": sum(1 for item in results.values() if item["ok"]),
        "failed": len(failures),
        "failure_names": failures,
        "safety_gates": sum(1 for item in results.values() if item["safety"]),
        "blocked": blocked,
        "intercepted_count": len(intercepted),
        "note": "Every tool handler was called with stubbed I/O; no real side effects.",
        "results": results,
    }
    try:
        os.makedirs(os.path.dirname(SMOKE_REPORT_PATH) or BASE, exist_ok=True)
        with open(SMOKE_REPORT_PATH, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return report


def _capture_dir():
    folder = os.path.join(BASE, "captures")
    os.makedirs(folder, exist_ok=True)
    return folder


def take_screenshot(delay_ms=800, path=""):
    """Capture the real screen via Termux:API Screenshot, with fallbacks."""
    try:
        delay = max(0, min(5000, int(delay_ms)))
    except Exception:
        return "ERROR: delay_ms must be a number."
    full = str(path or "").strip()
    full = os.path.realpath(os.path.expanduser(full)) if full else os.path.join(
        _capture_dir(), "screen_%d.png" % int(time.time()))
    try:
        os.makedirs(os.path.dirname(full) or BASE, exist_ok=True)
    except Exception as exc:
        return "ERROR: cannot create capture folder: %s" % str(exc)[:120]

    extras = [("--es", "file", full), ("--ei", "delay_ms", str(delay))]
    cli = ["termux-screenshot", "-d", str(delay), full]
    rc, out, err = termux_api("Screenshot", extras, cli=cli, timeout=45)
    if rc == 0 and os.path.isfile(full):
        return "Screenshot saved: " + full
    for raw in reversed((out or "").strip().splitlines()):
        candidate = raw.strip().strip("'\"")
        if candidate and os.path.isfile(candidate):
            return "Screenshot saved: " + candidate
    rc2, _, err2 = run(["screencap", "-p", full], timeout=30)
    if rc2 == 0 and os.path.isfile(full):
        return "Screenshot saved: " + full
    return ("ERROR: screenshot unavailable. Need a Termux:API build with "
            "Screenshot/MediaProjection, or screencap access. %s" %
            ((err or err2 or "no response")[:160]))


def camera_photo(camera="0", path=""):
    """Take a real photo through the phone camera."""
    full = str(path or "").strip()
    full = os.path.realpath(os.path.expanduser(full)) if full else os.path.join(
        _capture_dir(), "camera_%d.jpg" % int(time.time()))
    try:
        os.makedirs(os.path.dirname(full) or BASE, exist_ok=True)
    except Exception as exc:
        return "ERROR: cannot create capture folder: %s" % str(exc)[:120]
    cid = str(camera or "0")
    extras = [("--es", "camera", cid), ("--es", "file", full)]
    cli = ["termux-camera-photo", "-c", cid, full]
    rc, out, err = termux_api("CameraPhoto", extras, cli=cli, timeout=45)
    if rc == 0 and os.path.isfile(full):
        return "Photo saved: " + full
    for raw in reversed((out or "").strip().splitlines()):
        candidate = raw.strip().strip("'\"")
        if candidate and os.path.isfile(candidate):
            return "Photo saved: " + candidate
    return "ERROR: camera photo failed (%s)" % ((err or out or "no response")[:160])


def camera_info():
    d, err = _json_call("CameraInfo", ["termux-camera-info"])
    if err:
        return "ERROR: " + err
    if not isinstance(d, list) or not d:
        return "No cameras reported."
    lines = []
    for item in d[:8]:
        if isinstance(item, dict):
            lines.append("- id %s: %s %s [%s]" % (
                item.get("id", "?"), item.get("manufacturer", ""),
                item.get("model", ""), item.get("facing", "")))
    return "Cameras:\n" + ("\n".join(lines) if lines else str(d[:3])[:500])


def see_screen(question="What is on the screen? Read all visible text."):
    shot = take_screenshot()
    if shot.startswith("ERROR"):
        return shot
    understood = analyze_image(shot.replace("Screenshot saved: ", ""), question)
    return "Screen understood:\n" + str(understood)


def see_camera(question="Describe what the camera sees and read any visible text."):
    shot = camera_photo()
    if shot.startswith("ERROR"):
        return shot
    understood = analyze_image(shot.replace("Photo saved: ", ""), question)
    return "Camera understood:\n" + str(understood)


def ui_action(action, x=0, y=0, x2=0, y2=0, duration=300, text="", key="",
              confirmed=False):
    """Real UI taps/swipes via rish/adb/input. Requires confirmed=true."""
    if not confirmed:
        return ("ERROR: UI control changes the phone. Ask the user first, then "
                "call again with confirmed=true.")
    act = str(action or "").strip().lower()
    try:
        x, y, x2, y2 = (int(x), int(y), int(x2), int(y2))
        duration = max(50, min(5000, int(duration)))
    except Exception:
        return "ERROR: coordinates and duration must be numbers."
    if act == "tap":
        parts = ["input", "tap", str(x), str(y)]
    elif act == "swipe":
        parts = ["input", "swipe", str(x), str(y), str(x2), str(y2), str(duration)]
    elif act == "text":
        safe = str(text or "").replace(" ", "%s")
        parts = ["input", "text", safe]
    elif act == "key":
        parts = ["input", "keyevent", str(key or "66")]
    elif act in ("home", "back", "power"):
        parts = ["input", "keyevent", {"home": "3", "back": "4", "power": "26"}[act]]
    else:
        return "ERROR: action must be tap, swipe, text, key, home, back or power."

    shell_cmd = " ".join(shlex.quote(p) for p in parts)
    if shutil.which("rish"):
        cmd = ["rish", "-c", shell_cmd]
        via = "rish"
    elif shutil.which("adb"):
        cmd = ["adb", "shell", shell_cmd]
        via = "adb"
    elif shutil.which("input"):
        cmd = ["sh", "-c", shell_cmd]
        via = "input"
    else:
        return ("ERROR: no UI input bridge found. Install rish or adb, or grant "
                "shell input access. No UI action was taken.")
    rc, out, err = run(cmd, timeout=20)
    return "UI %s done via %s. %s" % (
        act, via, ((err or out or "")[:120])) if rc == 0 else (
        "ERROR: UI %s failed (%s)" % (act, (err or out or "no response")[:150]))


def phone_capabilities():
    """Report what this phone/Jarvis can really do right now."""
    diag = termux_api_diagnostics()
    state = lambda ok: "yes" if ok else "no"
    lines = [
        "Direct Termux:API: " + state(diag.get("direct_ok")),
        "Android broadcast: " + state(diag.get("broadcast_ok")),
        "Speech-to-text CLI: " + state(shutil.which("termux-speech-to-text")),
        "Text-to-speech CLI: " + state(shutil.which("termux-tts-speak")),
        "Camera CLI: " + state(shutil.which("termux-camera-photo")),
        "Screenshot CLI: " + state(shutil.which("termux-screenshot")),
        "UI bridge (rish): " + state(shutil.which("rish")),
        "UI bridge (adb): " + state(shutil.which("adb")),
        "Vision backend: " + state(bool((load_json(CONFIG_PATH, {}) or {}).get("gemini_api_key"))),
    ]
    lines.append("Note: screenshots need a Termux:API build with Screenshot/MediaProjection.")
    return "Phone capabilities:\n" + "\n".join(lines)


# ---------------------------------------------------------- voice automation

VOICE_YES = {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay",
             "go ahead", "do it", "confirm", "approved", "please do"}
VOICE_NO = {"no", "n", "nope", "cancel", "stop", "don't", "dont", "never",
            "abort", "not now"}

DANGEROUS_TOOLS = {
    "call_contact", "dial", "send_sms", "whatsapp", "compose_email",
    "mail_send", "ui_action", "emergency",
}


def load_macros():
    data = load_json(MACROS_PATH, {}) or {}
    return data if isinstance(data, dict) else {}


def save_macros(data):
    save_json(MACROS_PATH, data, private=True)


def _macro_key(name):
    return re.sub(r"[^a-z0-9 ]+", "", str(name or "").lower()).strip()


def macro_add(name, steps, description=""):
    key = _macro_key(name)
    if not key:
        return "ERROR: macro needs a name."
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except Exception:
            return "ERROR: macro steps must be a JSON list."
    if not isinstance(steps, list) or not steps:
        return "ERROR: macro steps must be a non-empty list."
    if len(steps) > 24:
        return "ERROR: a macro can have at most 24 steps."
    clean = []
    for step in steps:
        if not isinstance(step, dict):
            return "ERROR: every macro step must be an object."
        tool = str(step.get("tool") or step.get("name") or "").strip()
        args = step.get("args") or {}
        if not hasattr(Jarvis, "tool_" + tool):
            return "ERROR: unknown tool in macro: %s" % tool
        if not isinstance(args, dict):
            return "ERROR: args for %s must be an object." % tool
        clean.append({"tool": tool, "args": args})
    data = load_macros()
    data[key] = {"name": key, "description": str(description or "")[:160],
                 "steps": clean, "updated": now_str()}
    save_macros(data)
    return "Macro '%s' saved with %d step(s)." % (key, len(clean))


def macro_list():
    data = load_macros()
    if not data:
        return "No macros saved."
    lines = []
    for key in sorted(data):
        item = data[key] or {}
        lines.append("- %s: %s (%d steps)" % (
            key, item.get("description", ""), len(item.get("steps") or [])))
    return "Voice macros:\n" + "\n".join(lines)


def macro_delete(name):
    key = _macro_key(name)
    data = load_macros()
    if key not in data:
        return "ERROR: no macro named '%s'." % key
    data.pop(key, None)
    save_macros(data)
    return "Macro '%s' deleted." % key


def macro_run(name, j=None):
    key = _macro_key(name)
    data = load_macros()
    if key not in data:
        return "ERROR: no macro named '%s'." % key
    runner = j or Jarvis(interactive=False)
    steps = (data[key] or {}).get("steps") or []
    lines = ["Macro %s:" % key]
    for index, step in enumerate(steps, 1):
        tool = str(step.get("tool") or "")
        args = dict(step.get("args") or {})
        try:
            result = runner.execute(tool, args)
        except Exception as exc:
            result = "ERROR: %s failed: %s" % (tool, exc)
        lines.append("%d. %s -> %s" % (index, tool, str(result).replace("\n", " ")[:160]))
    return "\n".join(lines)


def wifi_switch(enable=True):
    on = str(enable).strip().lower() in ("1", "true", "yes", "on", "enable")
    word = "true" if on else "false"
    rc, out, err = termux_api(
        "WifiEnable", [("--ez", "enabled", word)],
        cli=["termux-wifi-enable", word], timeout=20)
    return ("Wi-Fi turned %s." % ("on" if on else "off")) if rc == 0 else (
        "ERROR: Wi-Fi switch failed (%s)" % (err or out or "no response"))


def sensor_list():
    rc, out, err = termux_api(
        "Sensor", [("--es", "action", "list")],
        cli=["termux-sensor", "-l"], timeout=20)
    if rc != 0:
        return "ERROR: could not list sensors (%s)" % (err or out or "no response")
    return (out or "").strip()[:3000] or "No sensors reported."


def sensor_read(sensor="accelerometer", limit=1, delay=200):
    try:
        n = max(1, min(20, int(limit)))
        d = max(50, min(5000, int(delay)))
    except Exception:
        return "ERROR: limit and delay must be numbers."
    name = str(sensor or "accelerometer")[:80]
    rc, out, err = termux_api(
        "Sensor",
        [("--es", "action", "sensors"), ("--es", "sensors", name),
         ("--ei", "limit", str(n)), ("--ei", "delay", str(d))],
        cli=["termux-sensor", "-s", name, "-n", str(n), "-d", str(d)],
        timeout=max(20, n * 3))
    if rc != 0:
        return "ERROR: sensor read failed (%s)" % (err or out or "no response")
    return (out or "").strip()[:2500] or "No sensor data returned."


def tts_engines():
    rc, out, err = termux_api(
        "TextToSpeech", [("--es", "engine", "LIST_AVAILABLE")],
        cli=["termux-tts-engines"], timeout=20)
    if rc != 0:
        return "ERROR: could not list TTS engines (%s)" % (err or out or "no response")
    return (out or "").strip()[:2000] or "No TTS engines reported."


def network_quality():
    lines = []
    try:
        ip = socket.gethostbyname("one.one.one.one")
        lines.append("DNS: OK (%s)" % ip)
    except Exception as exc:
        lines.append("DNS: failed (%s)" % str(exc)[:80])
    started = time.monotonic()
    try:
        req = urllib.request.Request("https://1.1.1.1/cdn-cgi/trace",
                                     headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "ignore")
        ms = int((time.monotonic() - started) * 1000)
        country = ""
        for line in raw.splitlines():
            if line.startswith("loc="):
                country = line.split("=", 1)[1]
                break
        lines.append("Internet: online (%d ms%s)" % (
            ms, (", " + country) if country else ""))
    except Exception as exc:
        lines.append("Internet: unreachable (%s)" % str(exc)[:90])
    return "Network quality:\n" + "\n".join(lines)


def phone_status():
    lines = ["Phone status:"]
    lines.append("- " + fmt_battery(battery_info()))
    lines.append("- Time: " + datetime.datetime.now().strftime("%I:%M %p, %d %b %Y"))
    lines.append("- Voice: " + current_voice_profile()[0])
    try:
        wifi = wifi_info().replace("\n", "; ")
        lines.append("- " + wifi[:150])
    except Exception:
        pass
    try:
        notes = notification_list().replace("\n", " ")[:120]
        lines.append("- Notifications: " + notes)
    except Exception:
        pass
    return "\n".join(lines)


def fast_voice_command(text, j=None):
    """Instant, deterministic voice commands. Returns (handled, spoken_answer).

    These run before the LLM, so common phone actions feel immediate and still
    work if Groq is rate-limited. Dangerous actions still go through Jarvis's
    normal confirmation gate, which uses spoken yes/no in ears mode.
    """
    raw = strip_wake_word(str(text or ""))
    q = clean_voice_text(raw)
    low = q.lower().strip(" .!?")
    if not low:
        return False, ""
    runner = j or Jarvis(interactive=False)

    def answer(value):
        return True, str(value)

    try:
        if re.search(r"\b(battery|charge level|charging status)\b", low):
            return answer(fmt_battery(battery_info()))
        if re.search(r"\b(phone status|system status|status report|how is my phone)\b", low):
            return answer(phone_status())
        m = re.search(r"\b(?:world time|time in|time at)\s+(.+)", low)
        if m:
            return answer(runner.tool_world_time(m.group(1).strip()))
        if re.search(r"\bwhat(?:'s| is) the time\b", low) or low in ("time", "date", "today"):
            return answer(runner.tool_get_time())
        if re.search(r"\b(weather|forecast)\b", low):
            city = re.sub(r"^(?:what(?:'s| is) the )?(?:weather|forecast)(?: in| at| for)?\s*",
                          "", low).strip()
            return answer(runner.tool_weather(city or "Delhi"))
        if re.search(r"\b(briefing|morning report)\b", low) or low in ("good morning", "good morning jarvis"):
            return answer(runner.tool_daily_briefing())

        # read things aloud / check communications (local, no LLM)
        if re.search(r"\bread (?:my )?(?:latest |recent )?(?:notifications?|notifs?)\b", low) or re.search(r"\bwhat(?:'s| are) my notifications?\b", low):
            return answer(read_notifications_aloud(10))
        if re.search(r"\b(?:read|check) (?:my )?(?:latest |recent )?(?:sms|text messages?|messages?)\b", low):
            return answer(read_sms_aloud(5))
        if re.search(r"\b(?:check|show|read) (?:my )?(?:unread )?(?:email|mail|inbox)\b", low):
            return answer(runner.tool_mail_inbox(count=5, unread_only=True))

        # sound / focus modes
        if re.search(r"\b(?:silent mode|go silent|mute (?:my )?phone|make (?:my )?phone silent)\b", low):
            return answer(sound_mode("silent"))
        if re.search(r"\b(?:vibrate mode|vibration mode|set (?:to )?vibrate)\b", low):
            return answer(sound_mode("vibrate"))
        if re.search(r"\b(?:normal mode|ringer on|sound on|unmute)\b", low):
            return answer(sound_mode("normal"))
        if re.search(r"\b(?:loud mode|max volume mode)\b", low):
            return answer(sound_mode("loud"))

        # routines by voice
        m = re.match(r"^(?:run |start |activate )?(good ?night|bedtime|sleep|focus|work|study|drive|driving|morning|wake ?up routine|quiet|meeting|workout|exercise|gym|relax|chill)(?: routine| mode)?$", low)
        if m:
            return answer(run_routine(m.group(1)))

        # wake-up alarm with best song / specific song
        m = re.search(r"\b(?:wake me up|wake up|set (?:a )?(?:smart |wake[- ]?up )?alarm)\b.*?\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", low)
        if m:
            hour = int(m.group(1)); minute = int(m.group(2) or 0)
            ap = m.group(3)
            if ap == "pm" and hour < 12: hour += 12
            if ap == "am" and hour == 12: hour = 0
            wants_song = bool(re.search(r"\b(song|music|play|best|wake.*song|energetic|gentle|calm|soft)\b", low))
            song = ""
            sm = re.search(r"\b(?:play|with|song)\s+(.+)$", low)
            if sm:
                candidate = sm.group(1).strip()
                candidate = re.sub(r"^(?:the )?(?:best|good|nice|perfect) (?:song|music)\s*(?:for me|for waking up)?", "", candidate, flags=re.I).strip()
                if candidate and not re.search(r"\b(?:best|good|for me|to wake)\b", candidate):
                    song = candidate
            if wants_song or re.search(r"\bwake me up\b", low):
                return answer(smart_alarm(hour, minute, "Wake up", song))
            return answer(runner.tool_set_alarm(hour, minute, "Alarm"))
        m = re.search(r"\b(?:pick|choose|suggest|play)\b.*\b(?:best )?(?:wake[- ]?up )?song\b", low)
        if m or re.search(r"\bbest song (?:for|to) (?:wake|waking)\b", low):
            return answer("Best wake-up song for you: %s" % choose_wake_song("", "wake"))
        if re.search(r"\b(tech news|latest news|news headlines)\b", low) or low == "news":
            return answer(runner.tool_tech_news(limit=5))

        if "switch to" in low and "voice" in low:
            m = re.search(r"switch to (?:the )?(jarvis|bolt|deep|fast) voice", low)
            if m:
                return answer(set_voice_profile(m.group(1)))
        if re.search(r"\b(what can you do|your capabilities|capabilities)\b", low):
            return answer(phone_capabilities())

        m = re.search(r"\bdeep search\s+(.+)", low)
        if m:
            return answer(runner.tool_deep_search(m.group(1)))
        m = re.search(r"\b(?:github repos?|github)\s+(?:for|about|on)?\s*(.+)", low)
        if m:
            return answer(runner.tool_github_search(m.group(1)))
        m = re.search(r"\b(?:wikipedia|wiki)\s+(?:about|for|on)?\s*(.+)", low)
        if m:
            return answer(runner.tool_wiki_search(m.group(1)))
        m = re.search(r"\b(?:search (?:the web )?for|search|google)\s+(.+)", low)
        if m:
            return answer(runner.tool_web_search(m.group(1)))
        if low.startswith("http://") or low.startswith("https://"):
            return answer(runner.tool_read_page(q))

        if re.search(r"\b(?:list|show) (?:all )?(?:my )?apps\b", low):
            return answer(runner.tool_app_list(limit=40))
        if re.search(r"\brefresh (?:my )?apps\b", low):
            return answer(runner.tool_refresh_apps())
        m = re.match(r"^(?:find|search for|search) (?:an )?app (.+)$", low)
        if m:
            return answer(runner.tool_app_find(m.group(1).strip()))
        m = re.match(r"^(?:app info|info for app|details for app) (.+)$", low)
        if m:
            return answer(runner.tool_app_info(m.group(1).strip()))
        m = re.match(r"^(?:close|force stop|force-close|kill) (?:the )?(?:app )?(.+)$", low)
        if m:
            return answer(runner.tool_app_close(m.group(1).strip()))
        m = re.match(r"^(?:when i unlock|on startup|at boot)(?: run)? macro (.+)$", low)
        if m:
            return answer(runner.tool_startup_macro(m.group(1).strip()))
        m = re.search(r"^(?:open|launch|start)\s+(.+)", low)
        if m:
            target = m.group(1).strip()
            if "wifi" in target and "setting" in target:
                return answer(runner.tool_open_settings("wifi"))
            return answer(runner.tool_open_app(target))

        m = re.search(r"\b(?:navigate to|directions to|take me to|open maps for)\s+(.+)", low)
        if m:
            return answer(runner.tool_navigate(m.group(1)))

        if low.startswith("play "):
            return answer(runner.tool_play_song(low[5:].strip()))
        media_map = {"pause": "pause", "resume": "play", "next": "next",
                     "next song": "next", "previous": "previous",
                     "previous song": "previous", "stop music": "stop"}
        if low in media_map:
            return answer(runner.tool_media_control(media_map[low]))

        m = re.match(r"^(?:please\s+)?(?:call|dial|phone)\s+(.+)", low)
        if m:
            return answer(runner.tool_call_contact(m.group(1).strip()))
        m = re.match(r"^(?:send (?:an )?sms to|text|message|whatsapp|whats app)\s+(.+?)\s+(?:saying|that says|with message|message|:)\s+(.+)$", low)
        if m:
            who, msg = m.group(1).strip(), m.group(2).strip()
            if low.startswith("whatsapp") or low.startswith("whats app"):
                return answer(runner.tool_whatsapp(who, msg))
            return answer(runner.tool_send_sms(who, msg))

        m = re.search(r"\b(?:set )?brightness (?:to )?(auto|\d{1,3})\b", low)
        if m:
            return answer(runner.tool_brightness(m.group(1)))
        m = re.search(r"\b(?:set )?volume (?:to )?(\d{1,2})\b", low)
        if m:
            return answer(runner.tool_volume("music", int(m.group(1))))
        if re.search(r"\b(?:torch|flashlight)\s+on\b", low):
            return answer(runner.tool_torch("on"))
        if re.search(r"\b(?:torch|flashlight)\s+off\b", low):
            return answer(runner.tool_torch("off"))
        if re.search(r"\bvibrate\b", low):
            return answer(runner.tool_vibrate(400))
        m = re.search(r"\b(?:turn |switch )?(wifi)\s+(on|off)\b", low)
        if m:
            return answer(runner.tool_wifi_switch(m.group(2) == "on"))
        if re.search(r"\bread (?:my )?clipboard\b", low):
            return answer(runner.tool_clipboard("get"))
        m = re.match(r"^copy (.+?) to (?:my )?clipboard$", low)
        if m:
            return answer(runner.tool_clipboard("set", m.group(1)))

        if re.search(r"\b(see (?:my )?screen|what(?:'s| is) on (?:the )?screen|screenshot)\b", low):
            return answer(runner.tool_see_screen())
        if re.search(r"\b(look around|see through (?:the )?camera|look through (?:the )?camera)\b", low):
            return answer(runner.tool_see_camera())
        if re.search(r"\btake (?:a )?photo\b", low):
            return answer(runner.tool_camera_photo())
        if re.search(r"\blist sensors\b", low):
            return answer(sensor_list())
        m = re.search(r"\bread (?:the )?(?:sensor )?([a-z ]+?) sensor\b", low)
        if m:
            return answer(sensor_read(m.group(1).strip()))
        if re.search(r"\b(tts|voice) engines\b", low):
            return answer(tts_engines())
        if re.search(r"\b(network quality|internet quality)\b", low):
            return answer(network_quality())
        if re.search(r"\b(internet speed|speed test)\b", low):
            return answer(runner.tool_net_speed())

        m = re.search(r"\bset (?:a )?timer (?:for )?(\d+)\s*(seconds?|secs?|minutes?|mins?)\b", low)
        if m:
            amount = int(m.group(1))
            if m.group(2).startswith("m"):
                amount *= 60
            return answer(runner.tool_set_timer(amount))
        m = re.search(r"\bremind me in (\d+)\s*(minutes?|mins?|hours?)\s+(?:to\s+)?(.+)", low)
        if m:
            amount = int(m.group(1))
            if m.group(2).startswith("h"):
                amount *= 60
            return answer(runner.tool_remind(amount, m.group(3)))
        # specific-time reminder today: "remind me at 7 pm to ..."
        m = re.search(r"\bremind me at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+(?:to\s+)?(.+)", low)
        if m:
            hour = int(m.group(1)); minute = int(m.group(2) or 0)
            ap = m.group(3)
            if ap == "pm" and hour < 12: hour += 12
            if ap == "am" and hour == 12: hour = 0
            mins = max(1, _seconds_until(hour, minute) // 60)
            return answer(runner.tool_remind(mins, m.group(4)))
        m = re.search(r"\balarm at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", low)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)
            if m.group(3) == "pm" and hour < 12:
                hour += 12
            if m.group(3) == "am" and hour == 12:
                hour = 0
            # if user said wake/wakeup/song in full text, handled above; plain alarm here
            if re.search(r"\b(wake|song|music)\b", low):
                return answer(smart_alarm(hour, minute, "Wake up", ""))
            return answer(runner.tool_set_alarm(hour, minute, "Alarm"))

        m = re.match(r"^remember that (.+?) is (.+)$", low)
        if m:
            return answer(runner.tool_remember(m.group(1).strip(), m.group(2).strip()))
        m = re.match(r"^(?:what do you know about|recall|remember)\s+(.+)", low)
        if m:
            return answer(runner.tool_recall(m.group(1).strip()))
        m = re.match(r"^add (.+?) to (?:my )?(todo|to-do|shopping) list$", low)
        if m:
            item, kind = m.group(1).strip(), m.group(2)
            return answer(runner.tool_todo_add(item) if "todo" in kind else runner.tool_shopping_add(item))
        if re.search(r"\bshow (?:my )?(todo|to-do|shopping) list\b", low):
            return answer(runner.tool_todo_list() if "todo" in low else runner.tool_shopping_list())
        m = re.match(r"^expense (\d+(?:\.\d+)?)\s+(?:for|on)\s+(.+)$", low)
        if m:
            return answer(runner.tool_expense_add(float(m.group(1)), m.group(2).strip()))

        if re.search(r"\blist macros\b", low):
            return answer(macro_list())
        m = re.match(r"^(?:run macro|macro)\s+(.+)", low)
        if m:
            return answer(macro_run(m.group(1).strip(), runner))
    except Exception as exc:
        return True, "Fast command hit an error: " + str(exc)[:160]
    return False, ""


def autopilot(j=None):
    """Keep Jarvis awake and listening so voice alone is enough."""
    try:
        run(["termux-wake-lock"], timeout=5)
    except Exception:
        pass
    j = j or Jarvis(voice=True)
    j.voice = True
    j.voice_confirm_callback = lambda _prompt: listen_once(timeout=15)
    post_notification("Jarvis autopilot online",
                      "Wake word active. Say 'Jarvis, ...' for any command.")
    speak_blocking("Autopilot online, Anas. What do you need?")
    try:
        speak_blocking(j.tool_daily_briefing())
    except Exception:
        pass
    return ears_loop(j, wake_word=True)


def install_boot_hook(boot_dir=None):
    """Install a Termux:Boot hook so Jarvis OS starts after a reboot."""
    boot_dir = boot_dir or os.path.join(os.path.expanduser("~"), ".termux", "boot")
    os.makedirs(boot_dir, exist_ok=True)
    script = os.path.join(boot_dir, "jarvis")
    content = """#!/data/data/com.termux/files/usr/bin/sh
# Jarvis OS autostart - installed by: anas jarvis boot-install
sleep 8
export PATH=/data/data/com.termux/files/usr/bin:$PATH
mkdir -p "$HOME/.jarvis/logs"
nohup python "$HOME/.jarvis/jarvis.py" --headless >> "$HOME/.jarvis/logs/boot.log" 2>&1 &
"""
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(script, 0o755)
    return ("Boot hook installed: %s\n"
            "With Termux:Boot installed, Jarvis OS starts automatically "
            "after reboot in hands-free mode." % script)


def omni_mode(j=None, headless=False):
    """One command, everything on: fresh daemon, app catalog, briefing, ears."""
    try:
        run(["termux-wake-lock"], timeout=5)
    except Exception:
        pass

    print(dim("Jarvis OS: starting all systems..."))
    try:
        print(dim("  " + restart_daemon()))
    except Exception as exc:
        print(dim("  daemon restart skipped: " + str(exc)[:120]))
    try:
        print(dim("  " + refresh_app_catalog()))
    except Exception as exc:
        print(dim("  app catalog refresh skipped: " + str(exc)[:120]))

    cfg = load_config() or {}
    startup = str(cfg.get("startup_macro") or "").strip()
    if startup:
        try:
            print(dim("  " + macro_run(startup, j).replace("\n", " ")[:180]))
        except Exception as exc:
            print(dim("  startup macro skipped: " + str(exc)[:120]))

    j = j or Jarvis(voice=True)
    j.voice = True
    j.voice_confirm_callback = lambda _prompt: listen_once(timeout=15)
    post_notification("Jarvis OS online",
                      "All systems active. Say 'Jarvis, ...' for any command.")
    print(dim("Jarvis OS online. %d tools active; wake word on." % len(TOOL_SCHEMAS_FULL)))
    speak_blocking("Jarvis OS online. All systems active, Anas.")
    try:
        speak_blocking(j.tool_daily_briefing())
    except Exception:
        pass
    try:
        return ears_loop(j, wake_word=True)
    finally:
        try:
            run(["termux-wake-unlock"], timeout=5)
        except Exception:
            pass


class Jarvis:
    def __init__(self, voice=None, auto_confirm=False, interactive=True):
        self.cfg = load_config()
        self.name = self.cfg.get("name", "Anas")
        self.model = self.cfg.get("model", "openai/gpt-oss-120b")
        self.fallback = self.cfg.get("fallback_model", "openai/gpt-oss-20b")
        self.api_key = (self.cfg.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")).strip()
        self.voice = self.cfg.get("voice", False) if voice is None else voice
        self.auto_confirm = auto_confirm
        self.interactive = interactive
        self.voice_confirm_callback = None
        self.debug = False
        self.history = load_json(HISTORY_PATH, [])
        if not isinstance(self.history, list):
            self.history = []
        self.memory = load_json(MEMORY_PATH, {})
        if not isinstance(self.memory, dict):
            self.memory = {}
        self.last_tools = []

    # -- prompt -------------------------------------------------------
    def system_prompt(self, query=""):
        mem = json.dumps(self.memory, ensure_ascii=False) if self.memory else "(empty)"
        if len(mem) > 1200:
            mem = mem[:1200] + "..."
        persona = self.cfg.get("persona") or ""
        if os.path.exists(PERSONA_PATH):
            try:
                persona = open(PERSONA_PATH, encoding="utf-8").read().strip()
            except Exception:
                pass
        rag = retrieve_context(query, k=3)
        know = retrieve_knowledge(query, k=3)
        ctx_parts = []
        if rag:
            ctx_parts.append("Relevant past conversations:\n" + rag)
        if know:
            ctx_parts.append("Relevant stored knowledge:\n" + know)
        ctx = "\n\n".join(ctx_parts) if ctx_parts else "(none)"
        return f"""You are Jarvis, the personal AI assistant of {self.name}, running locally in Termux on their Samsung Galaxy A15 (Android 17).

Current date and time on the phone: {now_str()}.

Known facts about {self.name}: {mem}

Retrieved context (RAG - past conversations and stored knowledge relevant to this query):
{ctx}

Your personality: calm, warm, sharp, lightly witty. Call the user {self.name}, not "sir" every time. Be concise and practical; this is a narrow terminal. Use short paragraphs and simple "-" bullets. No tables, no heavy markdown. Think step by step internally before answering, but only show the final answer.

Tools available: {", ".join(t["function"]["name"] for t in TOOL_SCHEMAS_FULL)}. Use call_tool with the exact name and args for any tool not exposed as its own function.

Rules:
1. Use tools for live facts (time, battery, weather, news, search results, prices). Never invent them.
2. Only state facts that appear in tool results. If the results don't answer the question, say so instead of guessing.
3. For news or "today's headlines", use the news tool, not web_search. For technology news specifically, always use tech_news (it aggregates TechCrunch, The Verge, Ars Technica, Hacker News, Engadget, Android Authority, GSMArena).
3b. Email: use mail_inbox / mail_search / mail_read. If email is not set up, tell the user to run: anas jarvis mail-setup <address> <app-password>. Never send an email without explicit confirmation in the same turn, and quote the exact to/subject/body before sending.
3c. Files and images: use list_uploads to discover files in Downloads/Documents/Pictures. Use analyze_image for photos and screenshots, ask_file for questions about a specific file, and ingest_file/ingest_dir to add documents to long-term RAG memory. When the user says "remember this file/image", ingest it.
3d. For "remind me in N minutes", use remind. For a daily overview, use daily_briefing.
4. For music requests: use play_song when the user wants a song to actually play out loud (it downloads the track and plays it in Termux, and keeps playing in the background). Use play_music only when they name a specific app: Spotify cannot autoplay without its paid API, so play_music just opens Spotify's search — say "I opened Spotify's search for X; tap the first result to play", never claim it is playing. For Spotify specifically you may also offer to play the same song audibly via play_song. Use media_control to pause/resume/skip.
5. Calls and SMS use Termux:API: call_contact/dial place a real call and send_sms really sends when the Phone/SMS permissions are granted. Otherwise they open the dialer/Messages draft and {self.name} taps call/send. Always ask for confirmation first and report exactly what happened.
6. For "call Gaurav" or "find X's number", use find_contact (or call_contact) to look in the real contacts list. Never invent a number, and never claim a call was placed if the tool only opened the dialer.
6b. Web search uses a live multi-engine search chain. Use deep_search for research questions or when asked to find GitHub repos; it combines web, GitHub and Wikipedia. read_page can open a result for details.
6c. Contact lookup is fuzzy: it handles misspelled/near names (e.g. "Gaurav Anas friend" -> "Gaurav Anas"). If resolve returns a low-confidence match, tell the user the closest contact and ask before calling.
6d. If find_contact/call_contact returns an ERROR about Termux:API or permissions, call api_status once (it is attached to the tool error), then report ITS exact diagnosis and stop. If the package exists but the live call fails, say: install Termux and Termux:API from the SAME source (both F-Droid/GitHub or both Play) so they share a signature, then grant Contacts/Phone/SMS. Never tell the user to blindly install again if api_status shows the package is already present. Do NOT substitute open_contacts or open_settings - those do not solve it.
7. If a tool returns ERROR, say what failed in one line and suggest a fix. Do not retry the same failing tool more than once.
8. Keep normal answers under 120 words. Expand only when asked.
9. When you did something on the phone, confirm exactly what you did.
10. Never expose API keys, tokens, or internal file paths in replies.
11. For voice conversations, keep replies short and speakable.
12. The user wants hands-free control: prefer tools over instructions. Use quick_command for simple spoken phone actions, macro_* for repeatable routines, and wifi_switch/sensor_read/network_quality/phone_status when asked about the phone itself. For any app request, use app_find/app_open/app_close/app_info/app_alias; the catalog covers every installed package, not just a fixed list.
13. In ears, voicechat, listen or autopilot mode, dangerous tools require a spoken yes/no confirmation; never bypass it or claim the action happened without the tool result.
{persona}"""

    # -- API ----------------------------------------------------------
    def chat(self, messages, model=None):
        if not self.api_key:
            raise RuntimeError("No Groq API key configured.")
        payload = {
            "model": model or self.model,
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "tool_choice": "auto",
            "max_completion_tokens": 1200,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=data,
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "Jarvis-Termux/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))

    def chat_with_fallback(self, messages):
        models = [self.model]
        if self.fallback and self.fallback != self.model:
            models.append(self.fallback)
        last_error = None
        for model in models:
            for attempt in range(3):
                try:
                    return self.chat(messages, model=model)
                except urllib.error.HTTPError as e:
                    body = ""
                    try:
                        body = e.read().decode("utf-8", "ignore")
                    except Exception:
                        pass
                    last_error = f"HTTP {e.code}: {body[:200]}"
                    if e.code == 429 and attempt < 2:
                        delay = 5
                        try:
                            hdr = e.headers.get("Retry-After")
                            if hdr:
                                delay = min(60, max(1, int(hdr)))
                            else:
                                err = (json.loads(body).get("error") or {})
                                if err.get("retry_after"):
                                    delay = min(60, max(1, int(err["retry_after"])))
                                elif err.get("retry_after_ms"):
                                    delay = min(60, max(1, int(err["retry_after_ms"]) // 1000))
                        except Exception:
                            pass
                        time.sleep(delay)
                        continue
                    break
                except Exception as e:
                    last_error = str(e)
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    break
        raise RuntimeError(last_error or "unknown API error")

    # -- loop ---------------------------------------------------------
    def ask(self, text):
        self.last_tools = []
        messages = [{"role": "system", "content": self.system_prompt(text)}]
        messages += self.history[-16:]
        messages.append({"role": "user", "content": text})

        for _ in range(6):
            resp = self.chat_with_fallback(messages)
            try:
                msg = resp["choices"][0]["message"]
            except Exception:
                raise RuntimeError("Unexpected API response: " + json.dumps(resp)[:300])
            calls = msg.get("tool_calls") or []
            # sanitize tool calls (model may emit malformed args)
            clean_calls = []
            for tc in calls:
                fn = (tc.get("function") or {})
                name = fn.get("name", "")
                name = name.split("|")[0].split("<")[0].strip()
                raw_args = fn.get("arguments") or "{}"
                try:
                    json.loads(raw_args if isinstance(raw_args, str) else "{}")
                except Exception:
                    raw_args = "{}"
                tc2 = dict(tc)
                tc2["function"] = {"name": name, "arguments": raw_args}
                clean_calls.append(tc2)
            calls = clean_calls
            if not calls:
                answer = (msg.get("content") or "").strip()
                answer = answer.replace("\u202f", " ").replace("\u00a0", " ").strip()
                if not answer:
                    answer = "I'm here, but I didn't get anything useful back. Try again?"
                self.history.append({"role": "user", "content": text})
                self.history.append({"role": "assistant", "content": answer})
                self.history = self.history[-24:]
                save_json(HISTORY_PATH, self.history)
                store_conversation(text, answer)
                return answer
            messages.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": calls,
            })
            for tc in calls:
                fn = (tc.get("function") or {})
                name = fn.get("name", "")
                # sanitize model quirks (e.g. gpt-oss channel markers)
                name = name.split("|")[0].split("<")[0].strip()
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}
                self.last_tools.append(name)
                if self.interactive:
                    print(dim(f"  · {name}"), flush=True)
                if self.debug:
                    print(dim(f"    args: {json.dumps(args, ensure_ascii=False)[:300]}"), flush=True)
                try:
                    result = self.execute(name, args)
                except Exception as e:
                    result = f"ERROR: tool {name} failed: {e!r}"
                if self.debug:
                    print(dim(f"    result: {str(result)[:400]}"), flush=True)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", name),
                    "content": str(result)[:5000],
                })
        return "I got stuck in a tool loop. Try rephrasing that."

    # -- new life/music tools ------------------------------------------------
    # -- new life/music tools ------------------------------------------------
    def tool_weather(self, city, **_):
        try:
            return weather(str(city))
        except Exception as e:
            return "ERROR: weather failed: " + str(e)

    def tool_play_music(self, query, app="spotify", **_):
        return play_music(str(query), str(app or "spotify"))

    def tool_play_youtube(self, query, **_):
        played = play_on_youtube(str(query))
        if played:
            return played
        return "ERROR: could not resolve '%s' to a YouTube video." % query

    def tool_play_song(self, query, **_):
        played = play_song(str(query))
        if played:
            return played
        played = play_on_youtube(str(query))
        if played:
            return played
        return "ERROR: could not play '%s'." % query

    def tool_media_control(self, action="play", **_):
        return media_control(str(action or "play"))

    def tool_calculate(self, expression, **_):
        return calculate_expr(str(expression))

    def tool_convert(self, value, from_unit, to_unit, **_):
        return convert_units(value, str(from_unit), str(to_unit))

    def tool_qr_code(self, text, **_):
        url = qr_url(str(text))
        return "QR code URL: %s\n(opened in browser)" % url if open_url(url).startswith("Opened") else url

    def tool_translate(self, text, to="hi", **_):
        return "Translation page: " + translate_url(str(text), str(to))

    def tool_joke(self, **_):
        return joke()

    def tool_fact(self, **_):
        return fact()

    def tool_quote(self, **_):
        return quote()

    def tool_advice(self, **_):
        return advice()

    def tool_define(self, word, **_):
        return define_word(str(word))

    def tool_wiki(self, topic, **_):
        return wiki_summary(str(topic))

    def tool_crypto(self, coin, **_):
        return crypto_price(str(coin))

    def tool_book_search(self, query, **_):
        return book_search(str(query))

    def tool_currency(self, amount, frm, to, **_):
        return currency_convert(amount, str(frm), str(to))

    def tool_tip(self, bill, percent=15, people=1, **_):
        return tip_calc(bill, percent, people)

    def tool_random_choice(self, options, **_):
        return random_choice(str(options))

    def tool_roll_dice(self, sides=6, count=1, **_):
        return roll_dice(sides, count)

    def tool_flip_coin(self, **_):
        return flip_coin()

    def tool_record_audio(self, seconds=10, **_):
        return record_audio(seconds)

    def tool_stop_recording(self, **_):
        return stop_recording()

    def tool_scan_qr(self, **_):
        return scan_qr()

    def tool_open_contacts(self, query="", **_):
        if str(query or "").strip():
            return contact_lookup(query)
        return open_contacts()

    def tool_find_contact(self, query="", **_):
        res = contact_lookup(query or "", limit=10)
        if isinstance(res, str) and res.startswith("ERROR"):
            try:
                res += "\n\n" + self.tool_api_status()
            except Exception:
                pass
        return res

    def tool_api_status(self, **_):
        """Report the real state of the Termux:API companion app."""
        d = termux_api_diagnostics()
        pkg = d["pkg_list"] or d["pm_path"] or "NOT found"
        lines = [
            "Termux:API CLI: %s" % ("present" if shutil.which("termux-contact-list") else "missing"),
            "com.termux.api package: %s" % pkg,
            "all termux packages: %s" % (d["termux_packages"] or "none"),
            "app data dir: %s" % ("visible" if d["data_dir"] else "not visible"),
            "direct socket API: %s" % ("OK" if d["direct_ok"] else "no response"),
            "am broadcast: %s" % ("sent" if d["broadcast_ok"] else "failed"),
            "live battery call: %s" % ("OK" if d["api_ok"] else "FAIL - " + d["api_msg"]),
        ]
        if "NOT found" in pkg:
            if "api" in d["termux_packages"].lower():
                lines.append("DIAGNOSIS: a Termux:API variant is installed but not under "
                             "com.termux.api (likely .debug). The standard CLI and "
                             "broadcast cannot reach it; install the matching "
                             "com.termux.api build from the same source as Termux.")
            else:
                lines.append("DIAGNOSIS: companion app is not installed under com.termux.api.")
        elif not d["api_ok"]:
            lines.append("DIAGNOSIS: app is installed but rejects/does not answer this "
                         "Termux -> source/signature mismatch. Install Termux and "
                         "Termux:API from the SAME source (both F-Droid/GitHub or both "
                         "Play), then grant Contacts/Phone/SMS.")
        else:
            lines.append("DIAGNOSIS: API is healthy; any contact failure is a permission issue "
                         "in Termux:API's App info.")
        return "\n".join(lines)

    def tool_call_contact(self, person, **_):
        num, err = resolve_contact(person)
        if err:
            if ("Termux" in str(err) or "termux" in str(err)
                    or "permission" in str(err).lower()):
                try:
                    err += "\n\n" + self.tool_api_status()
                except Exception:
                    pass
            return err
        if not self.confirm("Call %s (%s)?" % (person, num)):
            return "Cancelled. No call was placed."
        return call_number(num, str(person))

    def tool_take_photo(self, **_):
        return take_photo()

    def tool_open_store(self, app="", **_):
        return open_app_store(str(app))

    def tool_add_event(self, title, date, time="09:00", **_):
        return add_calendar_event(str(title), str(date), str(time))

    def tool_emergency(self, **_):
        return emergency_call()

    def tool_find_phone(self, **_):
        return find_phone()

    def tool_sos(self, **_):
        return sos_flash()

    def tool_download(self, url, **_):
        return download_file(str(url))

    def tool_list_files(self, path="~", **_):
        return list_files(str(path))

    def tool_read_file(self, path, **_):
        return read_text_file(str(path))

    def tool_write_file(self, path, content, **_):
        return write_text_file(str(path), str(content))

    def tool_note_add(self, text, **_):
        return note_add(str(text))

    def tool_note_list(self, **_):
        return note_list()

    def tool_note_delete(self, id, **_):
        return note_delete(id)

    def tool_todo_add(self, text, **_):
        return todo_add(str(text))

    def tool_todo_list(self, **_):
        return todo_list()

    def tool_todo_done(self, id, **_):
        return todo_done(id)

    def tool_todo_clear(self, **_):
        return todo_clear()

    def tool_shopping_add(self, text, **_):
        return shopping_add(str(text))

    def tool_shopping_list(self, **_):
        return shopping_list()

    def tool_shopping_clear(self, **_):
        return shopping_clear()

    def tool_expense_add(self, amount, category, note="", **_):
        return expense_add(amount, str(category), str(note))

    def tool_expense_list(self, limit=10, **_):
        return expense_list(limit)

    def tool_expense_summary(self, **_):
        return expense_summary()

    def tool_learn(self, text, tag="", **_):
        ok = store_knowledge(str(text), str(tag))
        return "Learned and stored." if ok else "ERROR: could not store."

    def tool_knowledge_search(self, query, **_):
        res = retrieve_knowledge(str(query), k=5)
        return res if res else "No relevant knowledge found."

    def tool_tech_news(self, limit=10, query="", force=False, **_):
        return tech_news(limit=limit, query=str(query or ""), force=bool(force))

    def tool_mail_inbox(self, count=8, unread_only=False, **_):
        return mail_inbox(count=count, unread_only=bool(unread_only))

    def tool_mail_search(self, query, count=8, **_):
        return mail_search(str(query), count=count)

    def tool_mail_read(self, uid, **_):
        return mail_read(str(uid))

    def tool_mail_send(self, to, subject, body, **_):
        return mail_send(str(to), str(subject), str(body))

    def tool_mail_setup(self, address, app_password, **_):
        return mail_setup(str(address), str(app_password))

    def tool_analyze_image(self, path, question="Describe this image in detail, including any visible text.", **_):
        return analyze_image(str(path), str(question))

    def tool_ask_file(self, path, question, **_):
        return ask_file(str(path), str(question))

    def tool_ingest_file(self, path, **_):
        return ingest_file(str(path))

    def tool_ingest_dir(self, path, **_):
        return ingest_dir(str(path))

    def tool_list_uploads(self, **_):
        return list_uploads()

    def tool_remind(self, minutes, text, **_):
        return remind(minutes, str(text))

    def tool_smart_alarm(self, hour, minute, label="Wake up", song="", **_):
        return smart_alarm(hour, minute, str(label or "Wake up"), str(song or ""))

    def tool_choose_wake_song(self, mood="", **_):
        song = choose_wake_song(str(mood or ""), for_what="wake")
        return "Best wake-up song for you: %s" % song

    def tool_play_wake_song(self, song="", **_):
        picked = str(song or "").strip() or choose_wake_song(for_what="wake")
        result = play_song(picked)
        if result:
            return str(result)
        return open_url("https://www.youtube.com/results?search_query=" +
                        urllib.parse.quote(picked + " audio"))

    def tool_sound_mode(self, mode="normal", **_):
        return sound_mode(str(mode or "normal"))

    def tool_read_notifications(self, limit=10, **_):
        return read_notifications_aloud(limit)

    def tool_read_sms(self, limit=5, **_):
        return read_sms_aloud(limit)

    def tool_daily_briefing(self, city="", **_):
        return daily_briefing(str(city or ""))

    # -- confirmation -------------------------------------------------
    def confirm(self, summary):
        if self.auto_confirm:
            return True
        if self.voice_confirm_callback:
            speak_async("Confirm: " + str(summary) + ". Say yes or no.")
            try:
                spoken = self.voice_confirm_callback(str(summary))
            except Exception:
                spoken = ""
            answer = clean_voice_text(spoken).lower().strip(" .!?")
            words = set(re.findall(r"[a-z']+", answer))
            if (answer in VOICE_YES or words & VOICE_YES
                    or any(p in answer for p in ("go ahead", "do it", "sounds good"))):
                return True
            if answer in VOICE_NO or words & VOICE_NO or answer:
                return False
        if not self.interactive or not sys.stdin.isatty():
            return False
        print(yellow("  ! " + summary))
        try:
            ans = input(yellow("    Proceed? [y/N] ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return ans in ("y", "yes")

    # -- tool dispatch ------------------------------------------------
    def execute(self, name, a):
        try:
            return getattr(self, "tool_" + name)(**a)
        except TypeError as e:
            return f"ERROR: bad arguments for {name}: {e}"
        except Exception as e:
            return f"ERROR: {name} failed: {e}"

    # -- super mode -----------------------------------------------------
    def tool_translate_text(self, text, to="hi", **_):
        return translate_text(text, to)

    def tool_ip_info(self, **_):
        return ip_info()

    def tool_net_speed(self, **_):
        return net_speed()

    def tool_world_time(self, city="", **_):
        return world_time(city)

    def tool_summarize_url(self, url, **_):
        return summarize_url(url, 5)

    def tool_share(self, text="", path="", action="view", title="", **_):
        return share_content(text, path, action, title)

    def tool_device_info(self, **_):
        return device_info()

    def tool_call_log(self, limit=10, offset=0, **_):
        return call_log(limit, offset)

    def tool_sms_recent(self, limit=5, message_type="inbox", address="", **_):
        return sms_recent(limit, message_type, address)

    def tool_notification_list(self, **_):
        return notification_list()

    def tool_notification_remove(self, id, **_):
        return notification_remove(id)

    def tool_brightness(self, level="auto", **_):
        return set_brightness(level)

    def tool_location(self, provider="gps", request="once", **_):
        return device_location(provider, request)

    def tool_wifi_info(self, **_):
        return wifi_info()

    def tool_wifi_scan(self, **_):
        return wifi_scan()

    def tool_routine(self, name, **_):
        return run_routine(name)

    def tool_self_test(self, quick=True, **_):
        return self_test_summary(bool(quick))

    def tool_take_screenshot(self, delay_ms=800, path="", **_):
        return take_screenshot(delay_ms, path)

    def tool_see_screen(self, question="What is on the screen? Read all visible text.", **_):
        return see_screen(question)

    def tool_camera_photo(self, camera="0", path="", **_):
        return camera_photo(camera, path)

    def tool_see_camera(self, question="Describe what the camera sees and read any visible text.", **_):
        return see_camera(question)

    def tool_camera_info(self, **_):
        return camera_info()

    def tool_ui_action(self, action, x=0, y=0, x2=0, y2=0, duration=300,
                       text="", key="", confirmed=False, **_):
        return ui_action(action, x, y, x2, y2, duration, text, key, confirmed)

    def tool_phone_capabilities(self, **_):
        return phone_capabilities()

    def tool_call_tool(self, name, args=None, **_):
        """Reach any of the 90+ tools without sending every schema to the API."""
        n = str(name or "").strip()
        if not n:
            return "ERROR: no tool name given."
        if not hasattr(self, "tool_" + n):
            return f"ERROR: unknown tool {n}. Use /tools to list names."
        a = args if isinstance(args, dict) else {}
        return self.execute(n, a)

    # tools -----------------------------------------------------------
    def tool_web_search(self, query, **_):
        try:
            return web_search(str(query))
        except Exception as e:
            return f"ERROR: search failed: {e}"

    def tool_github_search(self, query, limit=5, sort="stars", **_):
        try:
            return github_search(str(query), int(limit or 5), str(sort or "stars"))
        except Exception as e:
            return f"ERROR: GitHub search failed: {e}"

    def tool_wiki_search(self, query, limit=5, **_):
        try:
            return wiki_search(str(query), int(limit or 5))
        except Exception as e:
            return f"ERROR: Wikipedia search failed: {e}"

    def tool_deep_search(self, query, limit=5, **_):
        try:
            return deep_search(str(query), int(limit or 5))
        except Exception as e:
            return f"ERROR: deep search failed: {e}"

    def tool_read_page(self, url, **_):
        try:
            return read_page(str(url))
        except Exception as e:
            return f"ERROR: could not read page: {e}"

    def tool_news(self, topic="", limit=6, **_):
        try:
            lim = max(3, min(10, int(limit or 6)))
        except Exception:
            lim = 6
        try:
            return news(str(topic or ""), lim)
        except Exception as e:
            return f"ERROR: news failed: {e}"

    def tool_get_time(self, **_):
        return "It is " + datetime.datetime.now().strftime("%I:%M %p on %A, %d %B %Y") + "."

    def tool_open_url(self, url, **_):
        return open_url(str(url))

    def tool_open_app(self, app, **_):
        return app_open(str(app))

    def tool_app_open(self, name, **_):
        return app_open(str(name))

    def tool_app_list(self, limit=50, refresh=False, **_):
        return app_list(limit, refresh)

    def tool_app_find(self, name, limit=5, **_):
        return app_search(name, limit)

    def tool_app_close(self, name, **_):
        return app_close(name, self)

    def tool_app_info(self, name, **_):
        return app_info(name)

    def tool_app_alias(self, name, alias, **_):
        return app_alias(name, alias)

    def tool_refresh_apps(self, **_):
        return refresh_app_catalog()

    def tool_startup_macro(self, name, **_):
        return set_startup_macro(name)

    def tool_dial(self, number, **_):
        num, err = resolve_contact(number)
        if err:
            return err
        if not self.confirm("Call %s?" % num):
            return "Cancelled. No call was placed."
        return call_number(num)

    def tool_send_sms(self, number, message, **_):
        num, err = resolve_contact(number)
        if err:
            return err
        msg = str(message or "")[:1500]
        if not self.confirm("Send SMS to %s: %s..." % (num, msg[:60])):
            return "Cancelled. No SMS was sent."
        return send_sms_real(num, msg)

    def tool_whatsapp(self, number, message, **_):
        digits = re.sub(r"\D", "", str(number or ""))
        msg = str(message or "")[:1500]
        if not digits:
            return "ERROR: I need a phone number with country code for WhatsApp."
        if not self.confirm(f"Open WhatsApp chat with {digits} and a draft?"):
            return "Cancelled. Nothing was opened."
        url = "https://wa.me/%s?text=%s" % (digits, urllib.parse.quote(msg))
        rc, out, err = run(["termux-open-url", url], timeout=20)
        if rc != 0:
            rc, out, err = run(["am", "start", "-a", "android.intent.action.VIEW",
                                "-d", url], timeout=20)
        if rc != 0:
            return f"ERROR: could not open WhatsApp ({err})."
        return (f"WhatsApp opened for {digits} with the message pre-filled. "
                f"{self.name} needs to tap send.")

    def tool_compose_email(self, to, subject, body, **_):
        to = str(to or "").strip()
        subject = str(subject or "")[:200]
        body = str(body or "")[:3000]
        if not self.confirm(f"Open an email draft to {to or '(no recipient)'}?"):
            return "Cancelled. No email draft was created."
        args = ["am", "start", "-a", "android.intent.action.SENDTO",
                "-d", "mailto:" + urllib.parse.quote(to, safe="@+.-_")]
        if subject:
            args += ["--es", "android.intent.extra.SUBJECT", subject]
        if body:
            args += ["--es", "android.intent.extra.TEXT", body]
        rc, out, err = run(args, timeout=20)
        if rc != 0:
            return f"ERROR: could not open email ({err})."
        return f"Email draft opened to {to or 'nobody yet'}. {self.name} must tap send."

    def tool_notify(self, title, body, **_):
        ok, info = post_notification(str(title)[:80], str(body)[:400])
        return "Notification posted." if ok else f"ERROR: notification failed ({info})."

    def tool_speak(self, text, **_):
        ok = speak_async(str(text))
        return "Speaking now." if ok else "ERROR: text-to-speech failed."

    def tool_voice_profile(self, name="bolt", **_):
        return set_voice_profile(name)

    def tool_quick_command(self, text, **_):
        handled, answer = fast_voice_command(text, self)
        return answer if handled else ("I did not match a quick command. " + answer).strip()

    def tool_macro_add(self, name, steps, description="", **_):
        return macro_add(name, steps, description)

    def tool_macro_list(self, **_):
        return macro_list()

    def tool_macro_run(self, name, **_):
        return macro_run(name, self)

    def tool_macro_delete(self, name, **_):
        return macro_delete(name)

    def tool_wifi_switch(self, enable=True, **_):
        return wifi_switch(enable)

    def tool_sensor_list(self, **_):
        return sensor_list()

    def tool_sensor_read(self, sensor="accelerometer", limit=1, delay=200, **_):
        return sensor_read(sensor, limit, delay)

    def tool_tts_engines(self, **_):
        return tts_engines()

    def tool_network_quality(self, **_):
        return network_quality()

    def tool_phone_status(self, **_):
        return phone_status()

    def tool_set_alarm(self, hour, minute, label="Alarm", song="", **_):
        if str(song or "").strip().lower() in ("best", "auto", "wake", "wakeup", "morning"):
            return smart_alarm(hour, minute, str(label or "Wake up"), "")
        if str(song or "").strip():
            return smart_alarm(hour, minute, str(label or "Wake up"), str(song))
        try:
            h, m = int(hour), int(minute)
            assert 0 <= h <= 23 and 0 <= m <= 59
        except Exception:
            return "ERROR: hour must be 0-23 and minute 0-59."
        rc, out, err = run(["am", "start", "-a", "android.intent.action.SET_ALARM",
                            "--ei", "hour", str(h),
                            "--ei", "minute", str(m),
                            "--es", "message", str(label)[:100]], timeout=20)
        if rc != 0:
            return f"ERROR: could not set alarm ({err})."
        return "Alarm set for %02d:%02d (%s)." % (h, m, str(label)[:60])

    def tool_set_timer(self, seconds, label="Timer", **_):
        try:
            secs = int(seconds)
            assert secs > 0
        except Exception:
            return "ERROR: seconds must be a positive number."
        rc, out, err = run(["am", "start", "-a", "android.intent.action.SET_TIMER",
                            "--ei", "android.intent.extra.alarm.LENGTH", str(secs),
                            "--es", "android.intent.extra.alarm.MESSAGE",
                            str(label)[:100]], timeout=20)
        if rc != 0:
            return f"ERROR: could not set timer ({err})."
        return "Timer started for %d seconds (%s)." % (secs, str(label)[:60])

    def tool_battery(self, **_):
        return fmt_battery(battery_info())

    def tool_system_info(self, **_):
        return system_info()

    def tool_volume(self, stream=None, level=None, **_):
        if not stream:
            data, err = get_volume()
            if not data:
                return "ERROR: " + err
            lines = []
            for v in data:
                lines.append(f"- {v.get('stream')}: {v.get('volume')}/{v.get('max_volume')}")
            return "Volume streams:\n" + "\n".join(lines)
        name = str(stream).lower()
        valid = ["music", "ring", "alarm", "notification", "call", "system"]
        if name not in valid:
            return "ERROR: stream must be one of " + ", ".join(valid)
        if level is None:
            data, err = get_volume()
            if not data:
                return "ERROR: " + err
            for v in data:
                if v.get("stream") == name:
                    return f"{name} volume is {v.get('volume')}/{v.get('max_volume')}."
            return "ERROR: unknown stream."
        try:
            lvl = max(0, min(15, int(level)))
        except Exception:
            return "ERROR: level must be a number 0-15."
        ok, info = set_volume(name, lvl)
        return f"{name} volume set to {lvl}." if ok else f"ERROR: {info}"

    def tool_torch(self, state="on", **_):
        s = str(state).lower()
        if s not in ("on", "off"):
            return "ERROR: state must be on or off."
        enabled = "true" if s == "on" else "false"
        rc, out, err = termux_api(
            "Torch", [("--ez", "enabled", enabled)],
            cli=["termux-torch", s], timeout=12)
        return f"Torch {s}." if rc == 0 else f"ERROR: torch failed ({err})."

    def tool_vibrate(self, ms=400, **_):
        try:
            d = max(50, min(5000, int(ms)))
        except Exception:
            d = 400
        rc, out, err = termux_api(
            "Vibrate", [("--ei", "duration_ms", str(d))],
            cli=["termux-vibrate", "-d", str(d)], timeout=12)
        return f"Vibrated for {d} ms." if rc == 0 else f"ERROR: vibration failed ({err})."

    def tool_clipboard(self, action="get", text="", **_):
        common = [("--ei", "api_version", "2")]
        if action == "get":
            rc, out, err = termux_api(
                "Clipboard", common + [("--ez", "get", "true")],
                cli=["termux-clipboard-get"], timeout=12)
            if rc != 0:
                return f"ERROR: {err}"
            return "Clipboard: " + ((out or "")[:1000] or "(empty)")
        rc, out, err = termux_api(
            "Clipboard", common + [("--ez", "set", "true")],
            stdin_text=str(text),
            cli=["termux-clipboard-set", str(text)], timeout=12)
        return "Clipboard updated." if rc == 0 else f"ERROR: {err}"

    def tool_remember(self, key, value, **_):
        self.memory[str(key)[:80]] = str(value)[:500]
        save_json(MEMORY_PATH, self.memory)
        return f"Remembered: {key} = {value}"

    def tool_recall(self, key=None, **_):
        if key:
            if str(key) in self.memory:
                return f"{key}: {self.memory[str(key)]}"
            return f"I don't have anything saved for {key}."
        if not self.memory:
            return "My memory is empty."
        return "Memory:\n" + "\n".join(f"- {k}: {v}" for k, v in self.memory.items())

    def tool_open_settings(self, panel, **_):
        key = str(panel).lower().strip()
        action = SETTINGS.get(key)
        if not action:
            return "ERROR: panel must be one of " + ", ".join(SETTINGS)
        rc, out, err = run(["am", "start", "-a", action], timeout=20)
        return f"Opened {key} settings." if rc == 0 else f"ERROR: {err}"

    def tool_navigate(self, place, **_):
        url = "geo:0,0?q=" + urllib.parse.quote(str(place))
        rc, out, err = run(["termux-open-url", url], timeout=20)
        if rc != 0:
            rc, out, err = run(["am", "start", "-a", "android.intent.action.VIEW",
                                "-d", url], timeout=20)
        return f"Opening maps for {place}." if rc == 0 else f"ERROR: {err}"

    def tool_youtube(self, query, **_):
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(str(query))
        return open_url(url)


# ---------------------------------------------------------------- schemas

def fn(name, desc, props=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": props or {},
                "required": required or [],
            },
        },
    }

TOOL_SCHEMAS = [
    fn("web_search", "Search the live web (Bing/DuckDuckGo fallback chain). Use for facts, prices, people, anything current.",
       {"query": {"type": "string", "description": "search query"}}, ["query"]),
    fn("deep_search", "Deep research: aggregates live web search, GitHub repositories and Wikipedia in one call. Use for 'research', 'find repos', or hard questions.",
       {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
    fn("github_search", "Search public GitHub repositories (free API, no token). Use for code, tools, libraries and repos.",
       {"query": {"type": "string"}, "limit": {"type": "integer"}, "sort": {"type": "string"}}, ["query"]),
    fn("wiki_search", "Search Wikipedia articles via the official free API.",
       {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
    fn("read_page", "Fetch a web page and return its readable text. Use after web_search when snippets are not enough.",
       {"url": {"type": "string"}}, ["url"]),
    fn("news", "Get the latest news headlines from Google News. Use for 'today's news', 'top headlines', or topic news.",
       {"topic": {"type": "string", "description": "topic or leave empty for top stories"},
        "limit": {"type": "integer"}}, []),
    fn("weather", "Get current weather for a city using wttr.in.",
       {"city": {"type": "string"}}, ["city"]),
    fn("get_time", "Get the phone's current date and time.", {}),
    fn("open_url", "Open a URL in the phone browser.",
       {"url": {"type": "string"}}, ["url"]),
    fn("open_app", "Launch an installed app by name (whatsapp, youtube, gmail, maps, chrome, camera, spotify, telegram, instagram, paytm, phonepe, swiggy, zomato, uber, amazon, flipkart, settings, clock, messages, dialer).",
       {"app": {"type": "string"}}, ["app"]),
    fn("dial", "Call a phone number or saved contact by name. Places the call directly when Termux:API has Phone permission, otherwise opens the dialer. Always confirm with the user first.",
       {"number": {"type": "string", "description": "number or contact name, e.g. 'Gaurav'"}}, ["number"]),
    fn("call_contact", "Find a saved contact by name and call them. Use this when the user says 'call Gaurav'.",
       {"person": {"type": "string", "description": "contact name or number"}}, ["person"]),
    fn("find_contact", "Look up a contact's phone number from the phone's real contacts list.",
       {"query": {"type": "string", "description": "name or number to search"}}, ["query"]),
    fn("send_sms", "Send an SMS to a number or saved contact. Sends directly when Termux:API has SMS permission, otherwise leaves a draft. Always confirm first.",
       {"number": {"type": "string"}, "message": {"type": "string"}}, ["number", "message"]),
    fn("whatsapp", "Open a WhatsApp chat with a pre-filled message. Does NOT send; the user taps send. Number needs country code. Always confirm first.",
       {"number": {"type": "string"}, "message": {"type": "string"}}, ["number", "message"]),
    fn("compose_email", "Open an email draft in the mail app. Does NOT send. Always confirm first.",
       {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
       ["to", "subject", "body"]),
    fn("notify", "Post an Android notification.",
       {"title": {"type": "string"}, "body": {"type": "string"}}, ["title", "body"]),
    fn("speak", "Speak text out loud through the phone speaker.",
       {"text": {"type": "string"}}, ["text"]),
    fn("voice_profile", "Change Jarvis's voice. Profiles: jarvis, bolt (fast+deep), deep, fast.",
       {"name": {"type": "string", "enum": ["jarvis", "bolt", "deep", "fast"]}}, ["name"]),
    fn("quick_command", "Run an instant local voice command without the LLM (battery, apps, media, lights, calls, messages, search, macros).",
       {"text": {"type": "string"}}, ["text"]),
    fn("macro_add", "Save a reusable multi-tool voice macro. Steps are a JSON list of {tool, args} objects.",
       {"name": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "object"}},
        "description": {"type": "string"}}, ["name", "steps"]),
    fn("macro_list", "List saved voice macros.", {}),
    fn("macro_run", "Run a saved voice macro by name.", {"name": {"type": "string"}}, ["name"]),
    fn("macro_delete", "Delete a saved voice macro.", {"name": {"type": "string"}}, ["name"]),
    fn("wifi_switch", "Turn the phone's Wi-Fi on or off.", {"enable": {"type": "boolean"}}, []),
    fn("sensor_list", "List real phone sensors available through Termux:API.", {}),
    fn("sensor_read", "Read a phone sensor briefly (accelerometer, gyroscope, light, etc.).",
       {"sensor": {"type": "string"}, "limit": {"type": "integer"}, "delay": {"type": "integer"}}, []),
    fn("tts_engines", "List installed Android text-to-speech engines.", {}),
    fn("network_quality", "Check DNS and internet latency/quality.", {}),
    fn("phone_status", "One-shot phone status: battery, time, Wi-Fi and notifications.", {}),
    fn("app_list", "List installed apps. Use refresh=true to rescan the phone.",
       {"limit": {"type": "integer"}, "refresh": {"type": "boolean"}}, []),
    fn("app_find", "Fuzzy-find any installed app by spoken name, alias or package.",
       {"name": {"type": "string"}, "limit": {"type": "integer"}}, ["name"]),
    fn("app_open", "Open any installed app by spoken name, alias or package.",
       {"name": {"type": "string"}}, ["name"]),
    fn("app_close", "Close an installed app after spoken confirmation.",
       {"name": {"type": "string"}}, ["name"]),
    fn("app_info", "Read version and install details for an installed app.",
       {"name": {"type": "string"}}, ["name"]),
    fn("app_alias", "Teach Jarvis a spoken alias for an installed app.",
       {"name": {"type": "string"}, "alias": {"type": "string"}}, ["name", "alias"]),
    fn("refresh_apps", "Rescan installed apps and refresh the local app catalog.", {}),
    fn("startup_macro", "Run a saved macro automatically whenever Jarvis OS starts.",
       {"name": {"type": "string"}}, ["name"]),
    fn("set_alarm", "Set a real Android alarm (24-hour). Pass song='best' or a song name to also wake with music.",
       {"hour": {"type": "integer"}, "minute": {"type": "integer"},
        "label": {"type": "string"}, "song": {"type": "string"}},
       ["hour", "minute"]),
    fn("smart_alarm", "Set alarm AND schedule Jarvis to wake you by speaking and playing the best song. Use for 'wake me up at 6 with a good song'.",
       {"hour": {"type": "integer"}, "minute": {"type": "integer"},
        "label": {"type": "string"}, "song": {"type": "string", "description": "song name/mood, or empty for auto-best"}},
       ["hour", "minute"]),
    fn("choose_wake_song", "Pick the best wake-up song for the user based on mood and preferences.",
       {"mood": {"type": "string"}}, []),
    fn("play_wake_song", "Play a wake-up/morning song now (or best auto-picked).",
       {"song": {"type": "string"}}, []),
    fn("sound_mode", "Set phone sound mode: normal, vibrate, silent, or loud.",
       {"mode": {"type": "string", "enum": ["normal", "vibrate", "silent", "loud"]}}, ["mode"]),
    fn("read_notifications", "Read current phone notifications aloud.",
       {"limit": {"type": "integer"}}, []),
    fn("read_sms", "Read recent SMS messages aloud.",
       {"limit": {"type": "integer"}}, []),
    fn("set_timer", "Start a real Android countdown timer.",
       {"seconds": {"type": "integer"}, "label": {"type": "string"}}, ["seconds"]),
    fn("battery", "Read battery percentage, charging state, temperature and health.", {}),
    fn("system_info", "Read battery, storage, uptime, local IP and time.", {}),
    fn("volume", "Read all volume streams, or set one stream's level (0-15).",
       {"stream": {"type": "string", "enum": ["music", "ring", "alarm", "notification", "call", "system"]},
        "level": {"type": "integer"}}),
    fn("torch", "Turn the flashlight on or off.",
       {"state": {"type": "string", "enum": ["on", "off"]}}, ["state"]),
    fn("vibrate", "Vibrate the phone for a number of milliseconds.",
       {"ms": {"type": "integer"}}),
    fn("clipboard", "Read or write the phone clipboard.",
       {"action": {"type": "string", "enum": ["get", "set"]}, "text": {"type": "string"}}, ["action"]),
    fn("remember", "Save a durable fact about the user (name, preferences, numbers, notes).",
       {"key": {"type": "string"}, "value": {"type": "string"}}, ["key", "value"]),
    fn("recall", "Read saved memory, all of it or one key.",
       {"key": {"type": "string"}}),
    fn("open_settings", "Open an Android settings panel: wifi, bluetooth, battery, display, sound, location, apps, airplane, data.",
       {"panel": {"type": "string"}}, ["panel"]),
    fn("navigate", "Open Google Maps navigation/search for a place or address.",
       {"place": {"type": "string"}}, ["place"]),
    fn("youtube", "Open a YouTube search in the browser.",
       {"query": {"type": "string"}}, ["query"]),
     fn("play_music", "Play music/search a song in Spotify, YouTube Music, YouTube, JioSaavn or Gaana.",
        {"query": {"type": "string"}, "app": {"type": "string"}}, ["query"]),
     fn("play_youtube", "Resolve a song/video and actually start playing it on YouTube right away.",
        {"query": {"type": "string"}}, ["query"]),
     fn("play_song", "Play a song out loud in Termux right now (downloads audio, works in background). Best for 'play <song>'.",
        {"query": {"type": "string"}}, ["query"]),
     fn("media_control", "Control current media playback: play, pause, next, previous, stop.",
        {"action": {"type": "string"}}, ["action"]),
     fn("calculate", "Evaluate a math expression.",
        {"expression": {"type": "string"}}, ["expression"]),
     fn("convert", "Convert units: km/mi, kg/lb, C/F/K, L/gal, cm/in, g/oz, ml/oz.",
        {"value": {"type": "number"}, "from_unit": {"type": "string"}, "to_unit": {"type": "string"}},
        ["value", "from_unit", "to_unit"]),
     fn("qr_code", "Generate a QR code for text/URL and open it.",
        {"text": {"type": "string"}}, ["text"]),
     fn("translate", "Open Google Translate for text.",
        {"text": {"type": "string"}, "to": {"type": "string"}}, ["text"]),
     fn("joke", "Tell a random joke.", {}),
     fn("fact", "Give a random interesting fact.", {}),
     fn("quote", "Give a random inspirational quote.", {}),
     fn("advice", "Give a piece of random advice.", {}),
     fn("define", "Define a word.", {"word": {"type": "string"}}, ["word"]),
     fn("wiki", "Wikipedia summary for a topic.", {"topic": {"type": "string"}}, ["topic"]),
     fn("crypto", "Get crypto price in USD and INR (CoinGecko).", {"coin": {"type": "string"}}, ["coin"]),
     fn("book_search", "Search books via Open Library.", {"query": {"type": "string"}}, ["query"]),
     fn("currency", "Convert currency amounts (free live rates).",
        {"amount": {"type": "number"}, "frm": {"type": "string"}, "to": {"type": "string"}},
        ["amount", "frm", "to"]),
     fn("tip", "Calculate tip and split a bill.",
        {"bill": {"type": "number"}, "percent": {"type": "number"}, "people": {"type": "integer"}}),
     fn("random_choice", "Pick randomly from comma-separated options.",
        {"options": {"type": "string"}}, ["options"]),
     fn("roll_dice", "Roll dice.", {"sides": {"type": "integer"}, "count": {"type": "integer"}}),
     fn("flip_coin", "Flip a coin.", {}),
     fn("record_audio", "Record audio from the microphone.", {"seconds": {"type": "integer"}}),
     fn("stop_recording", "Stop an ongoing recording.", {}),
     fn("take_photo", "Open the camera to take a photo.", {}),
     fn("scan_qr", "Open a QR/barcode scanner.", {}),
     fn("open_contacts", "Open the contacts app, or search contacts when a query is given.",
   {"query": {"type": "string", "description": "optional name/number to look up"}}),
     fn("add_event", "Add a calendar event (opens calendar).",
        {"title": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"}},
        ["title", "date"]),
     fn("emergency", "Open the dialer for 112 (emergency).", {}),
     fn("find_phone", "Make the phone ring and vibrate to find it.", {}),
     fn("sos", "Flash SOS with the flashlight.", {}),
     fn("download", "Download a file to /sdcard/Download.", {"url": {"type": "string"}}, ["url"]),
     fn("list_files", "List files in a directory.", {"path": {"type": "string"}}),
     fn("read_file", "Read a text file.", {"path": {"type": "string"}}, ["path"]),
     fn("write_file", "Write text to a file.", {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"]),
     fn("note_add", "Save a quick note.", {"text": {"type": "string"}}, ["text"]),
     fn("note_list", "List saved notes.", {}),
     fn("note_delete", "Delete a note by id.", {"id": {"type": "integer"}}, ["id"]),
     fn("todo_add", "Add a todo item.", {"text": {"type": "string"}}, ["text"]),
     fn("todo_list", "List todos.", {}),
     fn("todo_done", "Mark a todo done by id.", {"id": {"type": "integer"}}, ["id"]),
     fn("todo_clear", "Clear all todos.", {}),
     fn("shopping_add", "Add an item to the shopping list.", {"text": {"type": "string"}}, ["text"]),
     fn("shopping_list", "Show the shopping list.", {}),
     fn("shopping_clear", "Clear the shopping list.", {}),
     fn("expense_add", "Record an expense.",
        {"amount": {"type": "number"}, "category": {"type": "string"}, "note": {"type": "string"}},
        ["amount", "category"]),
     fn("expense_list", "List recent expenses.", {"limit": {"type": "integer"}}),
     fn("expense_summary", "Summarize expenses by category.", {}),
     fn("open_store", "Open Play Store search for an app.", {"app": {"type": "string"}}),
     fn("learn", "Store a fact or document in Jarvis's long-term knowledge base (RAG).",
        {"text": {"type": "string"}, "tag": {"type": "string"}}, ["text"]),
     fn("knowledge_search", "Search Jarvis's stored knowledge base.", {"query": {"type": "string"}}, ["query"]),
     fn("tech_news", "Latest technology news headlines from major tech sites (cached 3h).",
        {"limit": {"type": "integer"}, "query": {"type": "string"}, "force": {"type": "boolean"}}, []),
     fn("mail_inbox", "List recent emails from the user's inbox. unread_only=true for unread only.",
        {"count": {"type": "integer"}, "unread_only": {"type": "boolean"}}, []),
     fn("mail_search", "Search the user's email for a keyword.", {"query": {"type": "string"}, "count": {"type": "integer"}}, ["query"]),
     fn("mail_read", "Read one email by its uid (uid comes from mail_inbox/mail_search).", {"uid": {"type": "string"}}, ["uid"]),
     fn("mail_send", "Send an email. Requires explicit user confirmation.", {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, ["to", "subject", "body"]),
     fn("mail_setup", "Connect the user's email account using an app password (Gmail: imap.gmail.com).",
        {"address": {"type": "string"}, "app_password": {"type": "string"}}, ["address", "app_password"]),
     fn("analyze_image", "Look at an image file (Screenshot/Download/Pictures) and answer a question about it.",
        {"path": {"type": "string"}, "question": {"type": "string"}}, ["path"]),
     fn("ask_file", "Answer a question from a text/PDF/image file.", {"path": {"type": "string"}, "question": {"type": "string"}}, ["path", "question"]),
     fn("ingest_file", "Add a file (text, PDF, or image) to Jarvis's long-term RAG memory.", {"path": {"type": "string"}}, ["path"]),
     fn("ingest_dir", "Add every file in a folder to Jarvis's long-term RAG memory.", {"path": {"type": "string"}}, ["path"]),
     fn("list_uploads", "List files available to ingest from Downloads, Documents and Pictures.", {}),
     fn("remind", "Set a reminder that notifies and speaks after N minutes.", {"minutes": {"type": "integer"}, "text": {"type": "string"}}, ["minutes", "text"]),
     fn("daily_briefing", "One-shot daily briefing: battery, weather, tech news, unread mail.", {"city": {"type": "string"}}, []),
     fn("api_status", "Deep-check the Termux:API companion app: package, signature link and live call.", {}, []),
     fn("translate_text", "Actually translate text into another language (live, not just a link).",
        {"text": {"type": "string"}, "to": {"type": "string", "description": "language code, e.g. hi, en, ta"}}, ["text"]),
     fn("ip_info", "Show the phone's public IP address, city, country and ISP.", {}, []),
     fn("net_speed", "Measure current download speed and route latency.", {}),
     fn("world_time", "Get the current time in another city (Delhi, London, New York, Tokyo, etc.).",
        {"city": {"type": "string"}}, []),
     fn("summarize_url", "Fetch a web page and return a short extractive summary.",
        {"url": {"type": "string"}}, ["url"]),
     fn("share", "Open the Android share sheet for text or a file. Does not send anything itself.",
        {"text": {"type": "string"}, "path": {"type": "string"},
         "action": {"type": "string", "enum": ["view", "send", "edit"]},
         "title": {"type": "string"}}),
     fn("device_info", "Read real phone hardware/OS information through Termux:API.", {}),
     fn("call_log", "Read recent call history (number, name, type, duration).",
        {"limit": {"type": "integer"}, "offset": {"type": "integer"}}, []),
     fn("sms_recent", "Read recent SMS messages from the phone (read-only).",
        {"limit": {"type": "integer"},
         "message_type": {"type": "string", "enum": ["all", "inbox", "sent", "draft", "outbox", "failed", "queued"]},
         "address": {"type": "string"}}, []),
     fn("notification_list", "List currently visible Android notifications.", {}),
     fn("notification_remove", "Remove a notification previously posted with an id.",
        {"id": {"type": "string"}}, ["id"]),
     fn("brightness", "Set screen brightness 0-255 or auto.", {"level": {"type": "string"}}, []),
     fn("location", "Read the phone's GPS/network location and a Maps link.",
        {"provider": {"type": "string", "enum": ["gps", "network", "passive"]},
         "request": {"type": "string", "enum": ["once", "last", "updates"]}}, []),
     fn("wifi_info", "Show the currently connected Wi-Fi SSID, IP, signal and speed.", {}),
     fn("wifi_scan", "List nearby Wi-Fi networks from the last scan.", {}),
     fn("routine", "Run a named multi-action routine: goodnight/bedtime, focus, drive, morning, quiet, workout, relax.",
        {"name": {"type": "string"}}, ["name"]),
     fn("self_test", "Run Jarvis's full verification and return a redacted pass/fail summary.",
        {"quick": {"type": "boolean"}}, []),
     fn("take_screenshot", "Capture the real phone screen to a PNG file (needs a Screenshot-capable Termux:API).",
        {"delay_ms": {"type": "integer"}, "path": {"type": "string"}}, []),
     fn("see_screen", "Take a screenshot and use vision to read/understand the whole screen.",
        {"question": {"type": "string"}}, []),
     fn("camera_photo", "Take a real photo with the phone camera and save it.",
        {"camera": {"type": "string"}, "path": {"type": "string"}}, []),
     fn("see_camera", "Take a camera photo and use vision to describe what Jarvis sees.",
        {"question": {"type": "string"}}, []),
     fn("camera_info", "List available phone cameras and their IDs.", {}),
     fn("ui_action", "Tap, swipe, type or press keys on the real screen via rish/adb. Requires confirmed=true after explicit user approval.",
        {"action": {"type": "string", "enum": ["tap", "swipe", "text", "key", "home", "back", "power"]},
         "x": {"type": "integer"}, "y": {"type": "integer"},
         "x2": {"type": "integer"}, "y2": {"type": "integer"},
         "duration": {"type": "integer"}, "text": {"type": "string"},
         "key": {"type": "string"}, "confirmed": {"type": "boolean"}}, ["action"]),
     fn("phone_capabilities", "Report which real phone features are available: API, voice, camera, screenshot, UI bridge, vision.", {}),
]

# Keep the full catalogue for /tools, but send a compact set to the API.
# Groq's free tier has a low tokens-per-minute ceiling, and 94 verbose schemas
# alone used ~5.6k tokens per turn. Rare tools stay reachable via call_tool.
TOOL_SCHEMAS_FULL = TOOL_SCHEMAS
CORE_TOOL_NAMES = {
    "web_search", "deep_search", "github_search", "wiki_search", "read_page",
    "news", "tech_news", "weather", "get_time", "open_url", "open_app",
    "dial", "call_contact", "find_contact", "send_sms", "whatsapp",
    "mail_inbox", "mail_search", "mail_read", "mail_send", "notify", "speak",
    "voice_profile", "quick_command", "macro_run", "macro_list",
    "wifi_switch", "sensor_read", "network_quality", "phone_status",
    "app_list", "app_find", "app_open", "app_close", "startup_macro",
    "smart_alarm", "choose_wake_song", "sound_mode", "read_notifications", "read_sms",
    "battery", "system_info", "remember", "recall", "list_uploads",
    "analyze_image", "ask_file", "remind", "daily_briefing", "list_files",
    "read_file", "write_file", "media_control", "play_song", "calculate",
    "convert", "currency", "open_settings", "mail_setup", "api_status",
    "translate_text", "ip_info", "net_speed", "world_time", "summarize_url",
    "share", "device_info", "call_log", "sms_recent", "notification_list",
    "brightness", "location", "wifi_info", "wifi_scan", "routine", "self_test",
    "see_screen", "camera_photo", "ui_action", "phone_capabilities",
}


def _compact_schema(schema):
    f = schema["function"]
    props = {}
    for k, v in (f["parameters"].get("properties") or {}).items():
        props[k] = {"type": v.get("type", "string")}
        if "enum" in v:
            props[k]["enum"] = v["enum"]
    return fn(f["name"], f["description"].split(".")[0][:100], props,
              f["parameters"].get("required") or [])


TOOL_SCHEMAS = [_compact_schema(s) for s in TOOL_SCHEMAS_FULL
                if s["function"]["name"] in CORE_TOOL_NAMES]
TOOL_SCHEMAS.append(fn(
    "call_tool",
    "Call any other Jarvis tool by name. Use for tools not in the core list.",
    {"name": {"type": "string", "description": "exact tool name"},
     "args": {"type": "object", "description": "tool arguments"}},
    ["name"]))


# ---------------------------------------------------------------- UI

BANNER = r"""
  ┌──────────────────────────────┐
  │   J A R V I S   ·   online   │
  └──────────────────────────────┘
"""

def show_banner(j):
    b = battery_info()
    line = fmt_battery(b)
    print(cyan(BANNER.strip("\n")))
    print("  " + bold("J.A.R.V.I.S.") + dim("  ·  v" + VERSION + "  ·  online"))
    print("  " + dim(line))
    print("  " + dim("Model: " + j.model + " (Groq free tier)"))
    print("  " + dim("Type /help for commands, /quit to exit."))
    print()

def show_help():
    print(bold("\nCommands"))
    print("  /help              this list")
    print("  /status            battery, model, memory size")
    print("  /doctor            check tools, permissions, internet, email")
    print("  /selftest          full verification (calls/SMS/mail are dry-run)")
    print("  /smoke             invoke every tool with stubbed I/O (no real actions)")
    print("  /bolt              switch to the fast, deep BOLT voice")
    print("  /voice-profile <n> jarvis | bolt | deep | fast")
    print("  /autopilot         voice OS: wake lock + briefing + always-on ears")
    print("  /macro list|run|save voice macros")
    print("  /apps              list installed apps")
    print("  /startup <macro>   run a macro whenever Jarvis OS starts")
    print("  /ears              always-on voice with 'Jarvis' wake word")
    print("  /see [question]    screenshot + vision: read the whole screen")
    print("  /camera [question] camera photo + vision")
    print("  /capabilities      what this phone can really do")
    print("  /restart           restart the background daemon with latest code")
    print("  /reload            restart THIS chat with the latest code")
    print("  /tools             what Jarvis can do")
    print("  /voice             toggle spoken replies")
    print("  /listen            voice input (Google speech)")
    print("  /voicechat         continuous voice conversation")
    print("  /memory            show saved memory")
    print("  /forget <key>      delete one memory key")
    print("  /reset             clear conversation history")
    print("  /shell <command>   run a Termux command yourself")
    print("  /quit              exit")
    print("\nJust type normally, for example:")
    print("  search today's tech news")
    print("  what's my battery?")
    print("  open youtube")
    print("  message 98765 43210 that I'll be late")
    print("  call 98765 43210")
    print("  set an alarm for 6:30 am")
    print("  weather in Mumbai")
    print()

def show_tools():
    print(bold("\nJarvis tools"))
    for t in TOOL_SCHEMAS_FULL:
        print("  - " + t["function"]["name"] + dim("  " + t["function"]["description"].split(".")[0]))
    print()

def speak_reply(j, text):
    if j.voice:
        speak_async(text)

def do_listen():
    print(yellow("Listening... speak after the tone."))
    text = listen_once(timeout=45)
    if not text:
        print(red("No speech recognised (or Termux:API speech is unavailable)."))
        return ""
    print(dim("You said: ") + text)
    return text


def repl(j):
    show_banner(j)
    while True:
        try:
            line = input(cyan("You > ")).strip()
        except KeyboardInterrupt:
            print()
            continue
        except EOFError:
            print()
            break
        if not line:
            continue
        low = line.lower()
        if low in ("/quit", "/exit", "quit", "exit"):
            break
        if low == "/help":
            show_help()
            continue
        if low == "/tools":
            show_tools()
            continue
        if low == "/status":
            b = battery_info()
            print(dim(fmt_battery(b)))
            print(dim(f"Model: {j.model}  |  memory keys: {len(j.memory)}  |  history: {len(j.history)//2} turns"))
            print(dim(f"Voice: {'on' if j.voice else 'off'}"))
            continue
        if low == "/doctor":
            doctor()
            continue
        if low in ("/selftest", "/verify", "/check-all"):
            print(dim(j.tool_self_test(True)))
            continue
        if low == "/smoke":
            report = exhaustive_smoke()
            print(dim(smoke_summary(report)))
            continue
        if low == "/bolt":
            print(dim(set_voice_profile("bolt")))
            speak_blocking("Bolt voice online, Anas.")
            continue
        if low == "/voice-profile" or low.startswith("/voice-profile "):
            parts = line.split(None, 1)
            print(dim(set_voice_profile(parts[1] if len(parts) > 1 else "jarvis")))
            continue
        if low == "/autopilot":
            autopilot(j)
            continue
        if low == "/macro" or low.startswith("/macro "):
            parts = line.split(None, 2)
            mode = parts[1].lower() if len(parts) > 1 else "list"
            arg = parts[2].strip() if len(parts) > 2 else ""
            if mode == "list":
                print(dim(macro_list()))
            elif mode in ("run", "delete") and arg:
                print(dim(macro_run(arg, j) if mode == "run" else macro_delete(arg)))
            elif mode in ("save", "add") and arg:
                sub = arg.split(None, 1)
                if len(sub) != 2:
                    print(dim("Usage: /macro save NAME [{tool: get_time, args: {}}]"))
                else:
                    print(dim(macro_add(sub[0], sub[1])))
            else:
                print(dim("Usage: /macro list | /macro run NAME | /macro save NAME JSON | /macro delete NAME"))
            continue
        if low == "/apps" or low.startswith("/apps "):
            refresh = "refresh" in low
            print(dim(app_list(limit=60, refresh=refresh)))
            continue
        if low == "/startup" or low.startswith("/startup "):
            parts = line.split(None, 1)
            print(dim(set_startup_macro(parts[1] if len(parts) > 1 else "")))
            continue
        if low == "/ears":
            ears_loop(j)
            continue
        if low == "/see" or low.startswith("/see "):
            q = line[5:].strip() or "What is on the screen? Read all visible text."
            print(dim(see_screen(q)))
            continue
        if low == "/camera" or low.startswith("/camera "):
            q = line[8:].strip() or "Describe what the camera sees and read any visible text."
            print(dim(see_camera(q)))
            continue
        if low in ("/capabilities", "/caps"):
            print(dim(phone_capabilities()))
            continue
        if low in ("/restart", "/reboot"):
            print(dim(restart_daemon()))
            continue
        if low in ("/reload", "/upgrade"):
            print(dim("Reloading Jarvis with the latest code..."))
            os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
        if low == "/voice":
            j.voice = not j.voice
            print(dim("Voice replies " + ("on." if j.voice else "off.")))
            continue
        if low == "/listen":
            spoken = do_listen()
            if not spoken:
                continue
            line = spoken
            low = line.lower()
        if low == "/voicechat":
            voice_chat_loop(j)
            continue
        if low == "/memory":
            print(dim(j.tool_recall()))
            continue
        if low.startswith("/forget "):
            key = line[8:].strip()
            if key in j.memory:
                del j.memory[key]
                save_json(MEMORY_PATH, j.memory)
                print(dim(f"Forgot {key}."))
            else:
                print(dim(f"No memory key named {key}."))
            continue
        if low == "/reset":
            j.history = []
            save_json(HISTORY_PATH, [])
            print(dim("Conversation cleared."))
            continue
        if low.startswith("/shell "):
            cmd = line[7:].strip()
            print(dim("$ " + cmd))
            rc, out, err = run(["bash", "-lc", cmd], timeout=120)
            if out:
                print(out)
            if err:
                print(dim(err))
            print(dim(f"(exit {rc})"))
            continue
        if low.startswith("/"):
            print(dim("Unknown command. /help for the list."))
            continue

        try:
            print(dim("  thinking..."), flush=True)
            answer = j.ask(line)
        except KeyboardInterrupt:
            print(yellow("\nCancelled."))
            continue
        except Exception as e:
            print(red("Error: " + str(e)[:300]))
            continue
        # erase the thinking line is not possible; just print the answer
        print()
        print(green("Jarvis > ") + answer)
        print()
        speak_reply(j, answer)


def restart_daemon():
    """Restart the local daemon with the currently installed code."""
    pid_path = os.path.join(BASE, "jarvisd.pid")
    old = None
    try:
        with open(pid_path, "r", encoding="utf-8") as f:
            old = int(f.read().strip())
    except Exception:
        pass
    if old:
        try:
            os.kill(old, signal.SIGTERM)
        except Exception:
            pass
        time.sleep(1)
        try:
            os.kill(old, signal.SIGKILL)
        except Exception:
            pass
    log_path = os.path.join(BASE, "logs", "daemon.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as lf:
        p = subprocess.Popen(
            [sys.executable, os.path.join(BASE, "jarvisd.py")],
            stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True)
    with open(pid_path, "w", encoding="utf-8") as f:
        f.write(str(p.pid))
    for _ in range(12):
        try:
            urllib.request.urlopen("http://127.0.0.1:21340/health", timeout=1).read()
            return "Daemon restarted (pid %d) with the current code." % p.pid
        except Exception:
            time.sleep(0.5)
    return "Daemon started (pid %d); health check is still pending." % p.pid


def termux_api_diagnostics():
    """Deep check of the companion app, not just the CLI wrappers."""
    facts = {"data_dir": False, "pm_path": "", "pkg_list": "", "api_ok": False,
             "api_msg": "", "broadcast_ok": False, "direct_ok": False,
             "termux_packages": ""}
    facts["data_dir"] = os.path.isdir("/data/data/com.termux.api")
    for pm in ("/system/bin/pm", "pm"):
        rc, out, _ = run([pm, "path", "com.termux.api"], timeout=10)
        if rc == 0 and out.strip():
            facts["pm_path"] = out.strip().splitlines()[0]
            break
    rc, out, _ = run(["/system/bin/cmd", "package", "list", "packages",
                     "com.termux.api"], timeout=10)
    if rc == 0 and out.strip():
        facts["pkg_list"] = out.strip().splitlines()[0]
    rc, out, _ = run(["/system/bin/pm", "list", "packages", "termux"], timeout=10)
    if rc == 0 and out.strip():
        facts["termux_packages"] = " ".join(x.strip() for x in out.splitlines() if x.strip())
    # Try the real protocol first; this is what matters, not the CLI stub.
    rc, out, err = api_call("BatteryStatus", timeout=8)
    facts["direct_ok"] = rc == 0 and "percentage" in (out or "")
    if rc == 0 and "percentage" in (out or ""):
        facts["broadcast_ok"] = True
        facts["api_ok"] = True
        facts["api_msg"] = out.strip()[:160]
    else:
        prefix = os.environ.get("PREFIX") or "/data/data/com.termux/files/usr"
        am = next((c for c in (os.path.join(prefix, "bin", "am"),
                               "/system/bin/am", "am") if c == "am" or os.path.exists(c)), "am")
        am_rc, am_out, am_err = run([am, "broadcast", "--user", "0",
                                     "-n", "com.termux.api/.TermuxApiReceiver",
                                     "--es", "api_method", "BatteryStatus"], timeout=8)
        facts["broadcast_ok"] = am_rc == 0 and "result=0" in (am_out or "")
        facts["api_ok"] = False
        facts["api_msg"] = ((err or out or am_err or am_out) or "no response").strip()[:160]
    return facts


def doctor():
    """Quick health check: what is really installed and permitted."""
    print(bold("Jarvis doctor"))
    rows = []

    def add(label, ok, note=""):
        rows.append((label, bool(ok), note))

    cfg = load_json(CONFIG_PATH, {}) or {}
    add("config", os.path.exists(CONFIG_PATH), CONFIG_PATH)
    add("package", os.path.isdir("/sdcard/jarvis_pkg"), "/sdcard/jarvis_pkg")
    add("groq key", bool(cfg.get("groq_api_key")), "set" if cfg.get("groq_api_key") else "missing")

    api = ["termux-contact-list", "termux-telephony-call", "termux-sms-send",
           "termux-tts-speak", "termux-battery-status", "termux-notification",
           "termux-open-url", "termux-media-player", "termux-microphone-record",
           "termux-vibrate", "termux-torch"]
    missing = [c for c in api if not shutil.which(c)]
    add("Termux:API commands", not missing,
        ("missing: " + ", ".join(missing)) if missing else "all present")

    diag = termux_api_diagnostics()
    app_ok = bool(diag["pkg_list"] or diag["pm_path"] or diag["data_dir"])
    add("API companion app", app_ok,
        diag["pkg_list"] or diag["pm_path"] or
        ("data dir only" if diag["data_dir"] else "com.termux.api NOT found"))
    add("Termux packages", bool(diag["termux_packages"]),
        diag["termux_packages"] or "none reported by pm")
    add("API broadcast sent", diag["broadcast_ok"],
        "am accepted" if diag["broadcast_ok"] else "am unavailable/rejected")
    add("API live call", diag["api_ok"], diag["api_msg"])

    res = contact_lookup("", limit=1)
    add("contacts read", not res.startswith("ERROR"),
        res.replace("\n", " ")[:110])

    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        net = True
    except Exception:
        net = False
    add("internet", net, "cloudflare DNS" if net else "no route - check mobile data/wifi")

    addr = cfg.get("email_address") or ""
    if addr and cfg.get("email_app_password"):
        mail_result = str(mail_inbox(1))
        mail_ok = not mail_result.startswith("ERROR")
        add("email login", mail_ok,
            (mail_result.replace("\n", " ")[:140] if not mail_ok
             else (addr + " - login OK")))
    else:
        add("email login", False,
            "not set up (anas jarvis mail-setup <address> <app-password>)")

    for label, ok, note in rows:
        mark = green("OK  ") if ok else red("FAIL")
        print("%s %-22s %s" % (mark, label, note))
    print()
    print(dim("If 'API companion app' or 'API live call' FAILs but you already have"))
    print(dim("Termux:API installed: Termux and Termux:API MUST come from the same"))
    print(dim("source (both F-Droid/GitHub, or both Play) so they share a signature."))
    print(dim("Mixing sources breaks the link. Then grant Contacts/Phone/SMS in App info."))
    return 0


def main():
    ap = argparse.ArgumentParser(prog="jarvis", description="Jarvis terminal assistant")
    ap.add_argument("--ask", nargs="+", metavar="TEXT", help="one-shot question, print answer and exit")
    ap.add_argument("--voice", action="store_true", help="speak replies")
    ap.add_argument("--voice-profile", metavar="NAME",
                    help="set voice profile: jarvis, bolt (fast+deep), deep, fast")
    ap.add_argument("--bolt-voice", action="store_true",
                    help="switch to the fast, deep BOLT voice now")
    ap.add_argument("--smoke", action="store_true",
                    help="invoke every tool with stubbed I/O; no real side effects")
    ap.add_argument("--voicechat", action="store_true", help="continuous voice conversation mode")
    ap.add_argument("--ears", action="store_true", help="always-on listening with wake word (Jarvis/Anas)")
    ap.add_argument("--autopilot", action="store_true",
                    help="voice OS: wake lock + spoken briefing + always-on ears")
    ap.add_argument("--omni", action="store_true",
                    help="one command, everything on (default when no args)")
    ap.add_argument("--chat", action="store_true",
                    help="force the original typed chat instead of Jarvis OS")
    ap.add_argument("--headless", action="store_true",
                    help="start Jarvis OS without waiting on a terminal")
    ap.add_argument("--boot-install", action="store_true",
                    help="install a Termux:Boot hook that starts Jarvis OS after reboot")
    ap.add_argument("--no-wake-word", action="store_true", help="with --ears, answer every utterance")
    ap.add_argument("--see-screen", nargs="?", const="What is on the screen? Read all visible text.", metavar="QUESTION",
                    help="screenshot + vision: understand the whole screen")
    ap.add_argument("--camera", nargs="?", const="Describe what the camera sees and read any visible text.", metavar="QUESTION",
                    help="camera photo + vision")
    ap.add_argument("--capabilities", action="store_true", help="report real phone/voice/vision capabilities")
    ap.add_argument("--listen", action="store_true", help="listen once, answer, speak, then exit")
    ap.add_argument("--speak", metavar="TEXT", help="speak the given text and exit")
    ap.add_argument("--play", metavar="SONG", help="resolve a song and start playing it on YouTube")
    ap.add_argument("--media", metavar="ACTION", help="media control: play/pause/next/previous/stop")
    ap.add_argument("--technews", action="store_true", help="latest tech news headlines")
    ap.add_argument("--briefing", nargs="?", const="", metavar="CITY", help="daily briefing")
    ap.add_argument("--mail", action="store_true", help="list recent inbox mail")
    ap.add_argument("--mailsetup", nargs="+", metavar="ADDRESS APP_PASSWORD", help="connect email")
    ap.add_argument("--image", nargs="+", metavar="PATH [QUESTION]", help="analyse an image")
    ap.add_argument("--askfile", nargs="+", metavar="PATH QUESTION", help="ask a question about a file")
    ap.add_argument("--ingest", metavar="PATH", help="add a file/folder to RAG memory")
    ap.add_argument("--remind", nargs="+", metavar="MINUTES TEXT", help="set a reminder")
    ap.add_argument("--set", nargs=2, metavar="KEY VALUE", help="change a setting, e.g. city Mumbai")
    ap.add_argument("--config", action="store_true", help="show settings (secrets hidden)")
    ap.add_argument("--yes", action="store_true", help="auto-confirm phone actions (use with care)")
    ap.add_argument("--status", action="store_true", help="show configuration and daemon status")
    ap.add_argument("--doctor", action="store_true", help="check installed tools and permissions")
    ap.add_argument("--debug", action="store_true", help="print tool calls and results")
    ap.add_argument("--version", action="version", version=f"Jarvis {VERSION}")
    args = ap.parse_args()

    os.makedirs(BASE, exist_ok=True)
    auto_update()
    if args.boot_install:
        print(install_boot_hook())
        return 0
    if args.doctor:
        return doctor()
    if args.status:
        cfg = load_config()
        print(f"Jarvis {VERSION}")
        print(f"model    : {cfg.get('model')}")
        print(f"battery  : {fmt_battery(battery_info())}")
        print(f"memory   : {len(load_json(MEMORY_PATH, {}))} keys")
        print(f"history  : {len(load_json(HISTORY_PATH, [])) // 2} turns")
        print(f"voice    : {'on' if cfg.get('voice') else 'off'} ({current_voice_profile()[0]})")
        print(f"email    : {cfg.get('email_address') or 'not set up'}")
        print(f"tools    : {len(TOOL_SCHEMAS_FULL)} ({len(TOOL_SCHEMAS)} sent to API)")
        try:
            r = urllib.request.urlopen("http://127.0.0.1:21340/health", timeout=2)
            print("daemon   : running  " + r.read().decode("utf-8", "ignore")[:100])
        except Exception:
            print("daemon   : stopped")
        return 0

    if args.voice_profile:
        print(set_voice_profile(args.voice_profile))
        return 0
    if args.bolt_voice:
        print(set_voice_profile("bolt"))
        spoken = speak_blocking("Bolt voice online, Anas.")
        print("Bolt voice confirmed." if spoken else
              "Bolt voice saved; TTS confirmation is unavailable here.")
        return 0
    if args.smoke:
        report = exhaustive_smoke(verbose=True)
        print(smoke_summary(report))
        return 0 if not report["failed"] and not report["blocked"] else 1
    if args.capabilities:
        print(phone_capabilities())
        return 0
    if args.see_screen:
        out = see_screen(args.see_screen)
        print(out)
        return 0 if not out.startswith("ERROR") else 1
    if args.camera:
        out = see_camera(args.camera)
        print(out)
        return 0 if not out.startswith("ERROR") else 1
    if args.technews:
        print(tech_news(12))
        return 0
    if args.briefing is not None:
        print(daily_briefing(args.briefing))
        return 0
    if args.mail:
        print(mail_inbox(10))
        return 0
    if args.mailsetup:
        if len(args.mailsetup) < 2:
            print("Usage: anas jarvis mail-setup <address> <app-password>")
            return 2
        print(mail_setup(args.mailsetup[0], " ".join(args.mailsetup[1:])))
        return 0
    if args.image:
        path = args.image[0]
        q = " ".join(args.image[1:]) or "Describe this image in detail, including any visible text."
        out = analyze_image(path, q)
        print(out)
        return 0 if not out.startswith("ERROR") else 1
    if args.askfile:
        if len(args.askfile) < 2:
            print("Usage: anas jarvis ask-file <path> <question>")
            return 2
        print(ask_file(args.askfile[0], " ".join(args.askfile[1:])))
        return 0
    if args.ingest:
        print(ingest_file(args.ingest) if os.path.isfile(_resolve_upload(args.ingest) or "")
              else ingest_dir(args.ingest))
        return 0
    if args.remind:
        if len(args.remind) < 2:
            print("Usage: anas jarvis remind <minutes> <text>")
            return 2
        print(remind(args.remind[0], " ".join(args.remind[1:])))
        return 0
    if args.set:
        key, value = args.set
        cfg = load_config() or {}
        cfg[key] = value
        save_json(CONFIG_PATH, cfg, private=True)
        print("Set %s = %s" % (key, value))
        return 0
    if args.config:
        cfg = load_config() or {}
        secret = {"groq_api_key", "gemini_api_key", "email_app_password"}
        for k in sorted(cfg):
            v = cfg[k]
            if k in secret:
                v = "set" if v else "empty"
            print("%-20s %s" % (k, v))
        return 0

    j = Jarvis(voice=True if args.voice else None,
               auto_confirm=args.yes,
               interactive=not args.ask)
    j.debug = args.debug

    if args.speak:
        ok = speak_blocking(args.speak)
        print("Spoken." if ok else "ERROR: TTS failed (install Termux:API?)")
        return 0 if ok else 1

    if args.play:
        res = play_song(args.play) or play_on_youtube(args.play)
        if not res:
            res = "Sorry, I could not find that song."
        print(res)
        speak_blocking(res)
        return 0 if "Playing" in res else 1

    if args.media:
        res = media_control(args.media)
        print(res)
        return 0 if not res.startswith("ERROR") else 1

    if args.autopilot:
        try:
            autopilot(j)
        except KeyboardInterrupt:
            speak_blocking("Autopilot offline, Anas.")
        return 0

    if args.ears:
        try:
            ears_loop(j, wake_word=not args.no_wake_word)
        except KeyboardInterrupt:
            speak_blocking("Ears offline, Anas.")
        return 0

    if args.voicechat:
        try:
            voice_chat_loop(j)
        except KeyboardInterrupt:
            speak_blocking("Voice chat stopped.")
        return 0

    if args.listen:
        j.voice_confirm_callback = lambda _prompt: listen_once(timeout=15)
        text = listen_once()
        if not text:
            print("No speech detected.")
            return 1
        print(cyan("You > ") + text)
        try:
            handled, answer = fast_voice_command(text, j)
            if not handled:
                answer = j.ask(text)
        except Exception as e:
            print("Error: " + str(e)[:400])
            return 1
        print(green("Jarvis > ") + answer)
        speak_blocking(answer)
        return 0

    if args.ask:
        text = " ".join(args.ask).strip()
        if not text:
            print("Nothing to ask.")
            return 2
        try:
            answer = j.ask(text)
        except Exception as e:
            print("Error: " + str(e)[:400], file=sys.stderr)
            return 1
        print(answer)
        return 0

    if (args.omni or args.headless
            or (not args.chat and not args.voice and not args.yes
                and sys.stdin.isatty())):
        try:
            omni_mode(j, headless=args.headless)
        except KeyboardInterrupt:
            speak_blocking("Jarvis OS offline, Anas.")
        return 0

    try:
        repl(j)
    except KeyboardInterrupt:
        pass
    print(dim("\nJarvis offline."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
