#!/usr/bin/env python3
"""Jarvis full verification. Never places a real call, sends a real SMS or email.

Writes a redacted report to selftest_report.json in the live Jarvis directory.
Run from Termux with:  anas jarvis selftest
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import time
import traceback
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = "/home/termux/.jarvis"
spec = importlib.util.spec_from_file_location("jarvis", os.path.join(HERE, "jarvis.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Proot can see the real home bind mount but not Termux's own $HOME. Redirect
# every state path to the live install so config/token/memory reads are real.
if os.path.isdir(LIVE) and os.path.abspath(m.BASE) != os.path.abspath(LIVE):
    old_base = m.BASE
    for key, val in list(vars(m).items()):
        if key.endswith("_PATH") and isinstance(val, str) and val.startswith(old_base):
            setattr(m, key, val.replace(old_base, LIVE, 1))
    m.BASE = LIVE

REPORT = os.path.join(LIVE if os.path.isdir(LIVE) else HERE, "selftest_report.json")
SMOKE_REPORT = None
results = []


def _has_am():
    prefix = os.environ.get("PREFIX") or "/data/data/com.termux/files/usr"
    return (os.path.exists(os.path.join(prefix, "bin", "am"))
            or os.path.exists("/system/bin/am") or shutil.which("am") is not None)


def _no_android():
    return None if _has_am() else (
        "Android runtime not visible here; run 'anas jarvis selftest' in Termux")


def _has_ui_bridge():
    return bool(shutil.which("rish") or shutil.which("adb") or shutil.which("input"))


def _no_ui_bridge():
    return None if _has_ui_bridge() else (
        "No rish/adb/input bridge in this container; UI tap dry-run runs in Termux")


def check(name, fn, category="general", skip_if=None):
    started = time.time()
    if skip_if:
        reason = skip_if()
        if reason:
            results.append({"category": category, "name": name, "ok": True,
                            "skipped": True, "detail": "SKIP: " + reason, "ms": 0})
            return
    try:
        value = fn()
        if isinstance(value, tuple):
            ok, detail = value
        elif isinstance(value, bool):
            ok, detail = value, str(value)
        else:
            ok, detail = True, str(value)
        results.append({"category": category, "name": name, "ok": bool(ok),
                        "detail": str(detail)[:500],
                        "ms": int((time.time() - started) * 1000)})
    except Exception as exc:
        results.append({"category": category, "name": name, "ok": False,
                        "detail": "EXCEPTION: %s: %s" % (type(exc).__name__, exc),
                        "tb": traceback.format_exc()[-700:],
                        "ms": int((time.time() - started) * 1000)})


# ---------------------------------------------------------------- environment
check("python", lambda: (sys.version_info >= (3, 8), sys.version.split()[0]))
check("live_config", lambda: (os.path.exists(m.CONFIG_PATH), m.CONFIG_PATH))


def _cfg():
    d = m.load_json(m.CONFIG_PATH, {}) or {}
    return (bool(d.get("groq_api_key")),
            "groq=%s email=%s app_password=%s" % (
                bool(d.get("groq_api_key")), bool(d.get("email_address")),
                bool(d.get("email_app_password"))))
check("credentials", _cfg)
check("android_runtime", _has_am, "phone", skip_if=_no_android)


def _daemon():
    try:
        raw = urllib.request.urlopen("http://127.0.0.1:21340/health",
                                     timeout=4).read().decode("utf-8", "ignore")
        return ("ok" in raw, raw[:120])
    except Exception as exc:
        return False, str(exc)
check("daemon_health", _daemon)


def _chat():
    tok_path = os.path.join(m.BASE, "token")
    if not os.path.exists(tok_path):
        return False, "token file missing"
    token = open(tok_path, encoding="utf-8").read().strip()
    body = json.dumps({"q": "Reply with exactly: READY"}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:21340/ask", data=body,
        headers={"Content-Type": "application/json", "X-Jarvis-Token": token})
    try:
        raw = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "ignore")
        ans = (json.loads(raw).get("answer") or "")
        return "READY" in ans.upper(), repr(ans)[:160]
    except Exception as exc:
        return False, str(exc)
check("chat_end_to_end", _chat, "chat")


def _schemas():
    names = [t["function"]["name"] for t in m.TOOL_SCHEMAS_FULL]
    comp = [t["function"]["name"] for t in m.TOOL_SCHEMAS]
    missing = [n for n in names if not hasattr(m.Jarvis, "tool_" + n)]
    return (len(names) > 50 and len(names) == len(set(names))
            and not missing and "call_tool" in comp,
            "full=%d compact=%d missing_handlers=%s" % (
                len(names), len(comp), missing or "none"))
check("all_tool_handlers", _schemas)

j = m.Jarvis(interactive=False)


# ---------------------------------------------------------------- local tools
check("calculate", lambda: ("14" in j.tool_calculate("2+3*4"),
                            j.tool_calculate("2+3*4")))
check("convert", lambda: ("1000" in str(j.tool_convert(1, "km", "m")),
                          j.tool_convert(1, "km", "m")))
check("tip", lambda: ("ERROR" not in j.tool_tip(100, 10, 1),
                      j.tool_tip(100, 10, 1)))
check("roll_dice", lambda: ("ERROR" not in j.tool_roll_dice(6, 2),
                            j.tool_roll_dice(6, 2)))
check("flip_coin", lambda: ("ERROR" not in j.tool_flip_coin(), j.tool_flip_coin()))
check("get_time", lambda: ("ERROR" not in j.tool_get_time(), j.tool_get_time()))


def _memory():
    key = "selftest_%d" % int(time.time())
    before = dict(j.memory)
    j.tool_remember(key, "ok")
    got = j.tool_recall(key)
    j.memory = before
    m.save_json(m.MEMORY_PATH, before)
    return "ok" in str(got).lower(), str(got)[:120]
check("memory_roundtrip", _memory, "local")


def _lists():
    paths = [m.NOTES_PATH, m.TODOS_PATH, m.SHOPPING_PATH, m.EXPENSES_PATH]
    before = [m._load_items(p) for p in paths]
    try:
        a = j.tool_note_add("selftest note")
        b = j.tool_todo_add("selftest todo")
        c = j.tool_shopping_add("selftest item")
        d = j.tool_expense_add(1, "selftest")
        ok = all("ERROR" not in str(x) for x in (a, b, c, d))
        return ok, " | ".join(str(x)[:60] for x in (a, b, c, d))
    finally:
        for path, items in zip(paths, before):
            m._save_items(path, items)
check("notes_todos_shopping_expenses", _lists, "local")


def _fuzzy():
    contacts = [
        {"name": "Gaurav Anas", "numbers": ["9876543210"]},
        {"name": "Gaurav Sharma", "numbers": ["9123456780"]},
        {"name": "Anas Mohammed", "numbers": ["9988776655"]},
    ]
    original = m._fetch_contacts
    m._fetch_contacts = lambda: (contacts, None)
    try:
        a = m.contact_lookup("gourav anas friend", limit=3)
        b = m.resolve_contact("anash mohammed")
        return ("Gaurav Anas" in a and b[0] == "9988776655",
                a.replace("\n", " ")[:140] + " | resolve=" + str(b))
    finally:
        m._fetch_contacts = original
check("fuzzy_contact_matching", _fuzzy, "contacts")


# ---------------------------------------------------------------- web / search
def _web():
    r = m.web_search("capital of India", 3)
    return ("Delhi" in r or "result" in r.lower()), r.replace("\n", " ")[:200]
check("web_search", _web, "web")


def _deep():
    r = j.tool_deep_search("site:github.com termux api", limit=2)
    return ("github" in r.lower() or "result" in r.lower()), r.replace("\n", " ")[:200]
check("deep_search", _deep, "web")


def _github():
    r = j.tool_github_search("rapidfuzz", limit=2)
    return ("github.com" in r or "stars" in r), r.replace("\n", " ")[:200]
check("github_search", _github, "web")


def _wiki():
    r = j.tool_wiki_search("Delhi", limit=2)
    return "Delhi" in r, r.replace("\n", " ")[:200]
check("wiki_search", _wiki, "web")


def _wiki_summary():
    r = j.tool_wiki("Delhi")
    return ("Delhi" in r and "ERROR" not in r), r.replace("\n", " ")[:200]
check("wiki_summary", _wiki_summary, "web")


def _read_page():
    r = j.tool_read_page("https://example.com")
    return ("Example Domain" in r or "ERROR" not in r), r.replace("\n", " ")[:200]
check("read_page", _read_page, "web")


def _weather():
    r = j.tool_weather("Delhi")
    return ("ERROR" not in r and bool(r)), r.replace("\n", " ")[:200]
check("weather", _weather, "web")


def _crypto():
    r = j.tool_crypto("bitcoin")
    return ("ERROR" not in r and bool(r)), r.replace("\n", " ")[:200]
check("crypto", _crypto, "web")


def _currency():
    r = j.tool_currency(1, "USD", "INR")
    return ("ERROR" not in r and bool(r)), str(r).replace("\n", " ")[:200]
check("currency", _currency, "web")


def _joke():
    r = j.tool_joke()
    return ("ERROR" not in r and bool(r)), r.replace("\n", " ")[:160]
check("joke_api", _joke, "web")


def _fact():
    r = j.tool_fact()
    return ("ERROR" not in r and bool(r)), r.replace("\n", " ")[:160]
check("fact_api", _fact, "web")


def _quote():
    r = j.tool_quote()
    return ("ERROR" not in r and bool(r)), r.replace("\n", " ")[:160]
check("quote_api", _quote, "web")


def _advice():
    r = j.tool_advice()
    return ("ERROR" not in r and bool(r)), r.replace("\n", " ")[:160]
check("advice_api", _advice, "web")


def _define():
    r = j.tool_define("robot")
    return ("ERROR" not in r and bool(r)), r.replace("\n", " ")[:160]
check("define", _define, "web")


def _book():
    r = j.tool_book_search("python")
    return ("ERROR" not in r and bool(r)), r.replace("\n", " ")[:160]
check("book_search", _book, "web")


def _news():
    r = j.tool_news(limit=2)
    return ("ERROR" not in r and bool(r)), r.replace("\n", " ")[:180]
check("news", _news, "web")


def _tech_news():
    r = j.tool_tech_news(limit=2)
    return ("ERROR" not in r and bool(r)), r.replace("\n", " ")[:180]
check("tech_news", _tech_news, "web")


def _translate():
    r = j.tool_translate("hello", "hi")
    return ("translate" in r.lower() or "http" in r), str(r)[:160]
check("translate_link", _translate, "web")


# ---------------------------------------------------------------- phone / API
def _diag():
    d = m.termux_api_diagnostics()
    return (d["api_ok"],
            "direct=%s am=%s pkg=%s pkgs=%s msg=%s" % (
                d["direct_ok"], d["broadcast_ok"],
                d["pkg_list"] or "none", d["termux_packages"] or "none",
                d["api_msg"][:120]))
check("api_diagnostics", _diag, "phone", skip_if=_no_android)


def _contacts_real():
    r = m.contact_lookup("", limit=3)
    return (not str(r).startswith("ERROR"), str(r).replace("\n", " ")[:220])
check("contacts_real", _contacts_real, "phone", skip_if=_no_android)


def _battery():
    r = j.tool_battery()
    return ("ERROR" not in str(r) and bool(r)), str(r).replace("\n", " ")[:160]
check("battery", _battery, "phone")


def _api_status():
    r = j.tool_api_status()
    return ("DIAGNOSIS:" in r and "live battery call:" in r), r.replace("\n", " ")[:300]
check("api_status", _api_status, "phone")


def _call_routing():
    seen = []
    original = m.termux_api
    m.termux_api = lambda method, extras=None, stdin_text="", cli=None, timeout=20: (
        seen.append((method, extras, stdin_text)) or (0, "ok", ""))
    try:
        r = m.call_number("9876543210", "Selftest")
        method = seen[0][0] if seen else ""
        extras = seen[0][1] if seen else []
        ok = ("Calling" in r and method == "TelephonyCall"
              and any(x[1] == "number" and x[2] == "9876543210" for x in extras))
        return ok, str(r)[:100] + " | " + str(seen)[:180]
    finally:
        m.termux_api = original
check("call_routing_dryrun", _call_routing, "phone")


def _sms_routing():
    seen = []
    original = m.termux_api
    m.termux_api = lambda method, extras=None, stdin_text="", cli=None, timeout=20: (
        seen.append((method, extras, stdin_text)) or (0, "ok", ""))
    try:
        r = m.send_sms_real("9876543210", "Jarvis selftest")
        method = seen[0][0] if seen else ""
        extras = seen[0][1] if seen else []
        body = seen[0][2] if seen else ""
        ok = ("SMS sent" in r and method == "SmsSend"
              and any(x[1] == "recipients" and x[2] == "9876543210" for x in extras)
              and body == "Jarvis selftest")
        return ok, str(r)[:100] + " | " + str(seen)[:180]
    finally:
        m.termux_api = original
check("sms_routing_dryrun", _sms_routing, "phone")


def _phone_controls():
    seen = []
    original = m.termux_api
    m.termux_api = lambda method, extras=None, stdin_text="", cli=None, timeout=20: (
        seen.append((method, extras, stdin_text)) or (0, "ok", ""))
    try:
        n = j.tool_notify("Jarvis selftest", "Verification")
        t = j.tool_torch("on")
        v = j.tool_vibrate(100)
        s = m.speak_blocking("selftest")
        methods = [x[0] for x in seen]
        ok = (all("ERROR" not in str(r) for r in (n, t, v))
              and s and methods == ["Notification", "Torch", "Vibrate", "TextToSpeech"])
        return ok, "methods=%s results=%s" % (methods, [str(x)[:40] for x in (n, t, v, s)])
    finally:
        m.termux_api = original
check("phone_control_routing_dryrun", _phone_controls, "phone")


# ---------------------------------------------------------------- mail
def _mail_config():
    cfg = m.load_json(m.CONFIG_PATH, {}) or {}
    ok = bool(cfg.get("email_address") and cfg.get("email_app_password"))
    return ok, ("configured" if ok else
                "missing email_address or email_app_password (16-char App Password required)")
check("mail_credentials", _mail_config, "mail")


def _mail_inbox():
    r = j.tool_mail_inbox(count=1)
    if str(r).startswith("ERROR"):
        return False, str(r)[:250]
    return True, str(r).replace("\n", " ")[:180]
check("mail_inbox_readonly", _mail_inbox, "mail")


def _mail_routing():
    seen = []
    original = m.mail_send
    old_confirm = j.auto_confirm
    m.mail_send = lambda to, subject, body: (
        seen.append((to, subject, body)) or "Email sent.")
    j.auto_confirm = True
    try:
        r = j.tool_mail_send("test@example.com", "selftest", "body")
        ok = seen and seen[0][0] == "test@example.com" and "sent" in r.lower()
        return ok, str(seen)[:160]
    finally:
        m.mail_send = original
        j.auto_confirm = old_confirm
check("mail_send_routing_dryrun", _mail_routing, "mail")


# ---------------------------------------------------------------- super mode
def _real_translate():
    r = j.tool_translate_text("hello", "hi")
    ok = ("ERROR" not in str(r) and ("Translation" in str(r) or "http" in str(r)
                                     or any("\u0900" <= ch <= "\u097f" for ch in str(r))))
    return ok, str(r).replace("\n", " ")[:160]
check("real_translate", _real_translate, "super")


def _ip_info():
    r = j.tool_ip_info()
    return ("Public IP:" in str(r), "ip_info returned" if "Public IP:" in str(r)
            else str(r).replace("\n", " ")[:180])
check("ip_info", _ip_info, "super")


def _net_speed():
    r = j.tool_net_speed()
    return ("Download:" in str(r), str(r).replace("\n", " ")[:180])
check("net_speed", _net_speed, "super")


def _world_time():
    r = j.tool_world_time("London")
    return ("ERROR" not in str(r) and ("London" in str(r) or "Europe/" in str(r)),
            str(r).replace("\n", " ")[:160])
check("world_time", _world_time, "super")


def _summarize_url():
    r = j.tool_summarize_url("https://example.com")
    return ("ERROR" not in str(r) and "Summary" in str(r),
            str(r).replace("\n", " ")[:180])
check("summarize_url", _summarize_url, "super")


def _share_routing():
    seen = []
    original = m.termux_api
    m.termux_api = lambda method, extras=None, stdin_text="", cli=None, timeout=20: (
        seen.append((method, extras, stdin_text)) or (0, "ok", ""))
    try:
        r = m.share_content("selftest share", title="Jarvis")
        method = seen[0][0] if seen else ""
        extras = seen[0][1] if seen else []
        body = seen[0][2] if seen else ""
        ok = ("share" in str(r).lower() and method == "Share" and body == "selftest share"
              and any(x[1] == "action" and x[2] == "view" for x in extras))
        return ok, str(r)[:100] + " | " + str(seen)[:180]
    finally:
        m.termux_api = original
check("share_routing_dryrun", _share_routing, "super")


def _phone_read_routing():
    responses = {
        "TelephonyDeviceInfo": '{"device":"Pixel","brand":"Google","android_version":"14"}',
        "CallLog": '[{"name":"A","number":"123","type":"incoming","date":"today","duration":3}]',
        "SmsInbox": '[{"address":"123","body":"hello","date":"today"}]',
        "NotificationList": '[{"id":"1","title":"T","content":"C"}]',
        "NotificationRemove": "ok",
        "Brightness": "ok",
        "Location": '{"latitude":28.6,"longitude":77.2,"accuracy":10}',
        "WifiConnectionInfo": '{"ssid":"TestNet","ip":"192.168.1.2","signal":-50}',
        "WifiScanInfo": '[{"ssid":"TestNet","level":-50}]',
    }
    seen = []
    original = m.termux_api

    def fake(method, extras=None, stdin_text="", cli=None, timeout=20):
        seen.append(method)
        return 0, responses.get(method, "ok"), ""

    m.termux_api = fake
    try:
        out = [
            j.tool_device_info(), j.tool_call_log(2), j.tool_sms_recent(2),
            j.tool_notification_list(), j.tool_notification_remove("42"),
            j.tool_brightness(120), j.tool_location("gps", "last"),
            j.tool_wifi_info(), j.tool_wifi_scan(),
        ]
        expected = ["TelephonyDeviceInfo", "CallLog", "SmsInbox", "NotificationList",
                    "NotificationRemove", "Brightness", "Location",
                    "WifiConnectionInfo", "WifiScanInfo"]
        ok = (seen == expected and all("ERROR" not in str(x) for x in out)
              and "Pixel" in str(out[0]) and "Recent calls" in str(out[1])
              and "SMS" in str(out[2]) and "Active notifications" in str(out[3])
              and "removed" in str(out[4]) and "Location:" in str(out[6])
              and "Wi-Fi" in str(out[7]) and "Wi-Fi networks" in str(out[8]))
        return ok, "methods=%s | %s" % (",".join(seen),
                                        " | ".join(str(x)[:45] for x in out))
    finally:
        m.termux_api = original
check("phone_read_routing_dryrun", _phone_read_routing, "super")


def _routine_routing():
    seen = []
    original = m.termux_api
    m.termux_api = lambda method, extras=None, stdin_text="", cli=None, timeout=20: (
        seen.append(method) or (0, "ok", ""))
    try:
        r = j.tool_call_tool("routine", {"name": "quiet"})
        ok = ("ERROR" not in str(r) and seen == ["Volume", "Volume"])
        return ok, str(r).replace("\n", " ")[:180] + " | methods=" + str(seen)
    finally:
        m.termux_api = original
check("routine_routing_dryrun", _routine_routing, "super")


def _schema_budget():
    compact = json.dumps(m.TOOL_SCHEMAS, separators=(",", ":"))
    names = [t["function"]["name"] for t in m.TOOL_SCHEMAS]
    wanted = {"call_tool", "self_test", "translate_text", "world_time", "routine",
              "see_screen", "ui_action", "phone_capabilities", "voice_profile",
              "quick_command", "macro_run", "macro_list", "wifi_switch",
              "sensor_read", "network_quality", "phone_status"}
    ok = (len(names) == len(set(names)) and wanted.issubset(set(names))
          and len(compact) < 18000)
    return ok, "compact=%d chars=%d approx_tokens=%d" % (
        len(names), len(compact), len(compact) // 4)
check("super_schema_budget", _schema_budget, "super")


# ---------------------------------------------------------------- voice / vision
def _voice_wake_words():
    a = m.has_wake_word("hey Jarvis, what's the battery?")
    b = m.strip_wake_word("Jarvis, what's the battery?")
    ok = a and "battery" in b.lower() and "jarvis" not in b.lower()
    return ok, "wake=%s stripped=%r" % (a, b)
check("voice_wake_words", _voice_wake_words, "voice")


def _stt_direct():
    original = m.api_call
    m.api_call = lambda method, extras=None, stdin_text="", timeout=20: (
        0, "Listening...\nhello anas\nhello anas.", "")
    try:
        r = m.listen_once(timeout=5)
        return (r == "hello anas", "heard=%r" % r)
    finally:
        m.api_call = original
check("stt_direct_routing", _stt_direct, "voice")


def _bolt_voice():
    original = m.current_voice_profile
    m.current_voice_profile = lambda: ("bolt", m.VOICE_PROFILES["bolt"])
    try:
        extras = m._tts_extras()
        cli = m._tts_cli("bolt voice online")
        values = {x[1]: x[2] for x in extras}
        joined = " ".join(cli)
        ok = (float(values.get("rate", 0)) >= 1.3
              and float(values.get("pitch", 9)) < 0.9
              and "-r 1.35" in joined and "-p 0.82" in joined)
        return ok, "extras=%s cli=%s" % (values, joined[:140])
    finally:
        m.current_voice_profile = original
check("bolt_voice_profile", _bolt_voice, "voice")


def _instant_voice_commands():
    original = m.battery_info

    class Stub:
        def tool_media_control(self, action):
            return "media " + str(action)

    m.battery_info = lambda: {"percentage": 77, "status": "DISCHARGING",
                              "plugged": "UNPLUGGED", "temperature": 30.0,
                              "health": "GOOD"}
    try:
        h1, a = m.fast_voice_command("what's the battery?", Stub())
        h2, b = m.fast_voice_command("pause", Stub())
        ok = h1 and h2 and "77%" in a and "pause" in b
        return ok, "battery=%r media=%r" % (a[:60], b[:60])
    finally:
        m.battery_info = original
check("instant_voice_commands", _instant_voice_commands, "voice")


def _spoken_confirmation():
    original = m.speak_async
    m.speak_async = lambda *_a, **_k: True
    try:
        jj = m.Jarvis(interactive=False)
        jj.voice_confirm_callback = lambda _prompt: "yeah, do it"
        yes = jj.confirm("dry-run call")
        jj.voice_confirm_callback = lambda _prompt: "no"
        no = jj.confirm("dry-run call")
        return (yes is True and no is False, "voice_yes=%s voice_no=%s" % (yes, no))
    finally:
        m.speak_async = original
check("spoken_confirmation", _spoken_confirmation, "voice")


def _voice_automation_tools_dryrun():
    originals = {
        "api": m.termux_api, "battery": m.battery_info,
        "wifi": m.wifi_info, "notes": m.notification_list,
        "dns": m.socket.gethostbyname, "urlopen": m.urllib.request.urlopen,
    }

    class Resp:
        def read(self):
            return b"loc=IN"

    m.termux_api = lambda method, extras=None, stdin_text="", cli=None, timeout=20: (
        0, "fake " + str(method), "")
    m.battery_info = lambda: {"percentage": 77, "status": "DISCHARGING",
                              "plugged": "UNPLUGGED", "temperature": 30.0,
                              "health": "GOOD"}
    m.wifi_info = lambda: "Wi-Fi: fake network"
    m.notification_list = lambda: "No new notifications"
    m.socket.gethostbyname = lambda _host: "1.1.1.1"
    m.urllib.request.urlopen = lambda *_a, **_k: Resp()
    try:
        results = {
            "wifi": m.wifi_switch(False),
            "sensor": m.sensor_read("light", 1, 200),
            "tts": m.tts_engines(),
            "network": m.network_quality(),
            "status": m.phone_status(),
        }
        ok = (all("ERROR" not in str(v) for v in results.values())
              and "Wi-Fi turned off" in results["wifi"]
              and "Network quality:" in results["network"]
              and "Phone status:" in results["status"])
        return ok, " | ".join(str(v).replace("\n", " ")[:45] for v in results.values())
    finally:
        m.termux_api = originals["api"]
        m.battery_info = originals["battery"]
        m.wifi_info = originals["wifi"]
        m.notification_list = originals["notes"]
        m.socket.gethostbyname = originals["dns"]
        m.urllib.request.urlopen = originals["urlopen"]
check("voice_automation_tools_dryrun", _voice_automation_tools_dryrun, "voice")


def _macro_routing_dryrun():
    originals = {"load": m.load_macros, "save": m.save_macros}
    store = {}

    def save(data):
        store.clear()
        store.update(data)
        return True

    m.load_macros = lambda: dict(store)
    m.save_macros = save
    try:
        a = m.macro_add("focus test", [{"tool": "get_time", "args": {}}], "dry")
        b = m.macro_run("focus test")
        c = m.macro_delete("focus test")
        rest = m.macro_list()
        ok = ("saved" in a and "get_time" in b and "ERROR" not in b
              and "deleted" in c and "focus test" not in rest)
        return ok, "add=%r run=%r delete=%r" % (
            a[:40], b.replace("\n", " ")[:60], c[:40])
    finally:
        m.load_macros = originals["load"]
        m.save_macros = originals["save"]
check("macro_routing_dryrun", _macro_routing_dryrun, "voice")


def _screenshot_routing():
    path = os.path.join(m.BASE, "captures", "selftest_shot.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(b"fake png")
    seen = []
    original = m.termux_api
    m.termux_api = lambda method, extras=None, stdin_text="", cli=None, timeout=20: (
        seen.append(method) or (0, path, ""))
    try:
        r = m.take_screenshot(path=path)
        ok = ("Screenshot saved" in r and seen == ["Screenshot"])
        return ok, str(r)[:120] + " | methods=" + str(seen)
    finally:
        m.termux_api = original
        try:
            os.remove(path)
        except Exception:
            pass
check("screenshot_routing_dryrun", _screenshot_routing, "vision")


def _camera_routing():
    path = os.path.join(m.BASE, "captures", "selftest_photo.jpg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(b"fake jpg")
    seen = []
    original = m.termux_api
    m.termux_api = lambda method, extras=None, stdin_text="", cli=None, timeout=20: (
        seen.append(method) or (0, path, ""))
    try:
        r = m.camera_photo(path=path)
        ok = ("Photo saved" in r and seen == ["CameraPhoto"])
        return ok, str(r)[:120] + " | methods=" + str(seen)
    finally:
        m.termux_api = original
        try:
            os.remove(path)
        except Exception:
            pass
check("camera_routing_dryrun", _camera_routing, "vision")


def _screen_vision():
    old_shot, old_analyze = m.take_screenshot, m.analyze_image
    m.take_screenshot = lambda *a, **k: "Screenshot saved: /fake.png"
    m.analyze_image = lambda path, question="": "FAKE VISION RESULT"
    try:
        r = m.see_screen("what is this?")
        return ("Screen understood" in r and "FAKE VISION RESULT" in r,
                str(r).replace("\n", " ")[:160])
    finally:
        m.take_screenshot, m.analyze_image = old_shot, old_analyze
check("screen_vision_dryrun", _screen_vision, "vision")


def _ui_routing():
    seen = []
    original = m.run
    m.run = lambda cmd, timeout=25, stdin_text=None: (
        seen.append(cmd) or (0, "ok", ""))
    try:
        denied = m.ui_action("tap", 5, 6, confirmed=False)
        done = m.ui_action("tap", 10, 20, confirmed=True)
        joined = " ".join(str(x) for x in seen[0]) if seen else ""
        ok = ("ERROR" in denied and "UI tap done" in done
              and "input tap 10 20" in joined)
        return ok, str(done)[:80] + " | cmd=" + joined[:120]
    finally:
        m.run = original
def _ui_gate():
    r = m.ui_action("tap", 5, 6, confirmed=False)
    return ("ERROR" in r and "confirmed=true" in r, str(r)[:160])
check("ui_confirmation_gate", _ui_gate, "vision")
check("ui_action_dryrun", _ui_routing, "vision", skip_if=_no_ui_bridge)


def _capabilities():
    r = j.tool_phone_capabilities()
    return ("Phone capabilities:" in r and "Speech-to-text CLI:" in r
            and "Vision backend:" in r, r.replace("\n", " | ")[:220])
check("phone_capabilities", _capabilities, "vision")


# ---------------------------------------------------------------- exhaustive
def _exhaustive_smoke():
    global SMOKE_REPORT
    SMOKE_REPORT = m.exhaustive_smoke()
    rep = SMOKE_REPORT
    ok = (rep["failed"] == 0 and not rep["blocked"]
          and rep["total"] == len(m.TOOL_SCHEMAS_FULL)
          and rep["passed"] == rep["total"])
    return ok, ("tools=%d/%d failed=%d safety=%d blocked=%s failures=%s" % (
        rep["passed"], rep["total"], rep["failed"], rep["safety_gates"],
        rep["blocked"], rep["failure_names"][:8]))
check("exhaustive_tool_smoke", _exhaustive_smoke, "smoke")


# ---------------------------------------------------------------- report
by_cat = {}
for r in results:
    slot = by_cat.setdefault(r["category"], [0, 0, 0])
    slot[0] += 1
    slot[1] += 1 if r["ok"] else 0
    slot[2] += 1 if r.get("skipped") else 0

payload = {
    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    "python": sys.version.split()[0],
    "summary": {
        "total": len(results),
        "passed": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "skipped": sum(1 for r in results if r.get("skipped")),
        "by_category": {k: {"total": v[0], "passed": v[1], "skipped": v[2]}
                        for k, v in by_cat.items()},
    },
    "note": "Calls/SMS/mail-send are dry-run routing checks; no real action is taken.",
    "smoke": SMOKE_REPORT,
    "results": results,
}
with open(REPORT, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, ensure_ascii=False)

print("Jarvis verification: %d/%d passed" % (payload["summary"]["passed"],
                                             payload["summary"]["total"]))
for r in results:
    mark = "SKIP" if r.get("skipped") else ("OK  " if r["ok"] else "FAIL")
    print("  %s [%s] %s: %s" % (mark, r["category"], r["name"], r["detail"][:110]))
print("Report: " + REPORT)
