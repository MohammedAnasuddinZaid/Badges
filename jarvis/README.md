# Jarvis (Termux, no root)

A local AI assistant for Anas's Samsung Galaxy A15. Runs in Termux, talks to
Groq's free tier for reasoning and Google Gemini for image understanding, and
can search the web, read tech news, open apps/URLs, play music, handle email,
read files/images, set reminders, and remember things long-term. No root.

## Commands

- `anas jarvis` - **ONE command**: Jarvis OS starts everything (daemon restart, app scan, briefing, wake lock, always-on ears)
- `anas jarvis chat` - typed chat only (legacy)
- `anas jarvis ask "..."` - one-shot question, prints the answer
- `anas jarvis ask --debug "..."` - show which tools it called
- `anas jarvis voice` - same as `anas jarvis` (hands-free Jarvis OS)
- `anas jarvis boot-install` - install a Termux:Boot hook so Jarvis OS starts after reboot
- `anas jarvis bolt-voice` - switch to the fast, deep BOLT voice now
- `anas jarvis voice-profile <jarvis|bolt|deep|fast>` - pick a voice profile
- `anas jarvis smoke` - invoke every tool with stubbed I/O (no real actions)
- `anas jarvis voicechat` - hands-free listen -> answer -> speak loop
- `anas jarvis autopilot` - voice OS: wake lock + spoken briefing + always-on ears
- `anas jarvis ears` - always-on listening; wake it with "Jarvis, ..." or "Anas, ..."
- `anas jarvis see [question]` - screenshot + vision: read/understand the whole screen
- `anas jarvis camera [question]` - camera photo + vision
- `anas jarvis capabilities` - report real phone/voice/vision capability
- `anas jarvis listen` - listen once, answer, speak
- `anas jarvis speak "text"` - just speak
- `anas jarvis play "song"` - download + play the song in the background
- `anas jarvis pause | resume | next | previous`
- `anas jarvis news` - latest tech news (TechCrunch, Verge, Ars, HN, Engadget, ...)
- `anas jarvis briefing [city]` - battery + weather + tech news + unread mail
- `anas jarvis mail` - recent inbox
- `anas jarvis mail-setup <address> <app-password>` - connect Gmail (IMAP)
- `anas jarvis image <file> [question]` - look at a photo/screenshot
- `anas jarvis ask-file <file> <question>` - ask about a PDF/text file
- `anas jarvis ingest <file|folder>` - add documents to long-term RAG memory
- `anas jarvis remind 30 "drink water"` - notification + voice reminder
- `anas jarvis set city Mumbai` - change a setting (or any config key)
- `anas jarvis config` - show settings (secrets hidden)
- `anas jarvis doctor` - quick check: tools, permissions, internet, Gmail login
- `anas jarvis selftest` - full verification report; calls/SMS/mail-send are dry-run
- `anas jarvis status` - model, battery, memory, email, daemon state
- `anas jarvis serve` - keep Jarvis alive in the background (24/7)
- `anas jarvis stop` / `restart` / `log`
- `anas help` - help

Inside the chat: `/help`, `/tools`, `/status`, `/doctor`, `/selftest`, `/smoke`,
`/bolt`, `/voice-profile <name>`, `/autopilot`, `/macro list|run|save|delete`,
`/ears`, `/see`, `/camera`, `/capabilities`, `/restart`, `/reload`, `/voice`,
`/listen`, `/voicechat`, `/memory`, `/forget <key>`, `/reset`, `/shell <cmd>`,
`/quit`.

`/restart` reloads the background daemon; `/reload` re-executes the current chat
with the latest installed code after an update.

Real-world examples that now work:
- "find gourav anas friend's number" -> fuzzy/phonetic contact matching handles misspellings and filler words
- "call Gaurav" -> places the call if Phone permission is granted, otherwise opens the dialer
- "search the web for the best budget phone under 15000" -> live multi-engine results
- "deep search rapidfuzz" -> web + GitHub repos + Wikipedia in one answer
- "find github repos for offline speech recognition" -> GitHub's free public search API
- "read my unread mail" -> real Gmail inbox once an App Password is set up
- "translate good morning to Hindi" -> real translation, not just a link
- "what is my public IP and internet speed?" -> live IP/ISP and speed test
- "time in Tokyo" -> world clock
- "summarize this article: <url>" -> extractive page summary
- "share this text" -> Android share sheet without sending anything itself
- "show recent calls / last SMS / active notifications" -> read-only phone data
- "run focus mode" or "goodnight" -> multi-action routines
- type `/selftest` in chat -> redacted verification report
- say "Jarvis, what's my battery?" while `anas jarvis ears` is running -> spoken answer
- say "Jarvis, see my screen" -> screenshot + vision reads the whole display
- say "Jarvis, look through the camera" -> camera photo + vision describes the room
- say "Jarvis, switch to bolt voice" -> fast, deep speech profile
- type `/smoke` -> every tool handler exercised with stubbed I/O, zero real actions
- say "Jarvis, phone status" -> battery, time, Wi-Fi and notifications in one answer
- say "Jarvis, turn Wi-Fi on" / "Wi-Fi off" -> real Wi-Fi switch through Termux:API
- say "Jarvis, list sensors" / "read the light sensor" -> real phone sensor access
- say "Jarvis, network quality" -> DNS and latency check before a speed test
- say "Jarvis, run macro focus" -> saved multi-step voice routine

## Autopilot and instant voice commands

`anas jarvis autopilot` is the closest thing to a voice-only phone layer. It takes
a Termux wake lock, speaks a short briefing, then starts always-on ears. Wake it
with **Jarvis**, **Anas**, or **computer**. Dangerous actions still require a
spoken **yes** before they run; say **no**, **cancel**, or **stop** to refuse.

Common commands are matched locally before the LLM, so they feel instant and
still work if Groq is rate-limited:

- battery / phone status / time / weather / briefing / news
- search, deep search, GitHub, Wikipedia, read a URL
- open apps, navigate, play/pause/next/previous music
- calls, SMS and WhatsApp with spoken confirmation
- brightness, volume, torch, vibrate, Wi-Fi on/off
- clipboard, screenshots, camera, sensors, TTS engines, network quality
- timers, reminders, alarms, memory, todo/shopping lists, expenses
- run saved macros

`quick_command` is also available as a tool, so the LLM can use the same instant
command parser when your phrasing is unusual.

## Voice macros

Save a sequence of tools and run the whole sequence with one phrase:

```sh
You > /macro save focus [{"tool":"wifi_switch","args":{"enable":false}},{"tool":"volume","args":{"stream":"music","level":4}}]
You > /macro run focus
You > Jarvis, run macro focus
```

`macro_add`, `macro_list`, `macro_run` and `macro_delete` are also exposed as
tools. Dangerous steps still hit their own confirmation gate.

## Voice profiles

The active profile is **bolt** by default: `en-GB`, pitch `0.82`, rate `1.35`
(deep and fast). Change it any time:

```sh
anas jarvis bolt-voice              # fast + deep BOLT
anas jarvis voice-profile jarvis    # calm original Jarvis
anas jarvis voice-profile deep      # deeper, slightly slower
anas jarvis voice-profile fast      # fastest, neutral pitch
```

Inside chat use `/bolt` or `/voice-profile <name>`. You can also say
"switch to bolt voice" and Jarvis calls the `voice_profile` tool. TTS uses the
same values through both the direct Termux:API `TextToSpeech` method and the
`termux-tts-speak -p/-r` CLI fallback.

## Voice and phone vision

`anas jarvis ears` is the always-on mode. It uses direct Termux:API
`SpeechToText` first, then `termux-speech-to-text`. It ignores background talk
until it hears **Jarvis**, **Anas**, or **computer**, then speaks the answer
with TextToSpeech. Say `stop listening` to end. Use `/ears` inside chat too.

`anas jarvis see "question"` captures the real screen and sends it to Gemini
vision. `anas jarvis camera "question"` does the same with the camera. The
screenshot path uses Termux:API `Screenshot`/MediaProjection when available,
`termux-screenshot` as CLI fallback, and `screencap` only if the shell permits
it. Run `anas jarvis capabilities` to see exactly what is available.

## Super mode tools

New tools are available directly or through `call_tool` (compact schema keeps
Groq's token limit safe):

- `translate_text`, `ip_info`, `net_speed`, `world_time`, `summarize_url`
- `share`, `device_info`, `call_log`, `sms_recent`
- `notification_list`, `notification_remove`, `brightness`
- `location`, `wifi_info`, `wifi_scan`
- `take_screenshot`, `see_screen`, `camera_photo`, `see_camera`, `camera_info`
- `ui_action`, `phone_capabilities`, `wifi_switch`
- `sensor_list`, `sensor_read`, `tts_engines`, `network_quality`, `phone_status`
- `quick_command`, `macro_add`, `macro_list`, `macro_run`, `macro_delete`
- `routine` (goodnight, focus, drive, morning, quiet), `self_test`

Routines never place calls, send SMS, or send email. `share` opens the Android
share chooser; you still choose the recipient. Call log, SMS, notifications,
location and Wi-Fi reads need the matching Termux:API permissions.

`ui_action` can tap, swipe, type and press keys only when a real input bridge
(`rish`, `adb`, or shell `input`) exists. It refuses to run unless the model
passes `confirmed=true` after your explicit approval in the same turn. No UI
action is faked by the self-test.

## Exhaustive smoke test

`anas jarvis smoke` (or `/smoke` in chat) calls **every registered tool handler**
once with safe representative arguments. All outside effects are stubbed first:
network, Termux:API, subprocess, TTS, mail, file writes, screenshots, camera,
UI input, and real call/SMS routes. It reports every handler result and writes a
redacted `~/.jarvis/smoke_report.json`. The full `anas jarvis selftest` now
includes this as one check, so a normal verification proves all 131 tools are
reachable without placing a call, sending an SMS/email, or moving the screen.

## Email setup (Gmail)

Gmail blocks plain passwords. Create a 16-character **App Password**:

1. Google Account -> Security -> 2-Step Verification -> App passwords
2. Generate one for "Mail / Other (Termux)"
3. In Termux run:
   `anas jarvis mail-setup yourname@gmail.com xxxx xxxx xxxx xxxx`

The password is verified with a real Gmail IMAP login **before** it is saved. Your normal Google password is rejected; only a 16-character App Password works. Spaces are stripped automatically, so `xxxx xxxx xxxx xxxx` and `xxxxxxxxxxxxxxxx` both work.

If `doctor` or `selftest` says **"Application-specific password required"**, the value currently saved in `config.json` is not a valid App Password. Generate a fresh 16-character App Password and re-run `anas jarvis mail-setup <address> <app-password>`. Do not paste the password into chat.

This stores it only in `~/.jarvis/config.json` (mode 600). Then:
`anas jarvis mail`, or ask "summarise my unread mail".

## Files and images (RAG)

- Put files in Downloads, Documents, or Pictures.
- `anas jarvis ingest /sdcard/Download/report.pdf` stores its text in memory.
- Ask "what did the report say about the budget?" and it retrieves the chunks.
- `anas jarvis image /sdcard/Download/shot.png "what is this error?"` uses Gemini
  vision.
- PDF text extraction needs `pip install pypdf` (otherwise install `pdftotext`).

## Music

`anas jarvis play "song"` uses `yt-dlp` + `termux-media-player`, so it plays in
the background without opening an app. Spotify cannot autoplay without its paid
API, so "play X on Spotify" opens Spotify's search results instead.

## Important limits

- Calls and SMS are real when Termux:API is installed and its Phone/SMS permissions are granted. Without those permissions Jarvis opens the dialer or a Messages draft and you tap call/send. WhatsApp drafts still need a tap.
- `find_contact` / `call_contact` read your real contacts through the direct Termux:API protocol, with `termux-contact-list` as fallback; grant **Contacts** permission to Termux:API.
- Web search uses a Bing -> DuckDuckGo -> DuckDuckGo Lite fallback chain, so one blocked search site no longer kills it.
- Email sending asks for confirmation in the same turn. Never give Jarvis your normal Gmail password - use an App Password.
- Android blocks apps launched from Termux from coming to the foreground, so
  `open_app` works when you run it yourself, but background launches may stay
  behind Termux. `play` avoids this entirely by playing audio inside Termux.
- 24/7 needs Termux:Boot (installed) plus the battery whitelist. The daemon
  binds only to 127.0.0.1 and uses a local token. It also posts a tech-news
  notification each morning around 08:00.
- No root access is required and none is used. Banking apps are untouched.

## Files

- `~/.jarvis/jarvis.py` main assistant
- `~/.jarvis/jarvisd.py` background daemon
- `~/.jarvis/config.json` API keys + email (mode 600)
- `~/.jarvis/token` daemon token (mode 600)
- `~/.jarvis/memory.json` saved facts
- `~/.jarvis/knowledge.jsonl` RAG knowledge base
- `~/.jarvis/conversations.jsonl` conversation memory
- `~/.jarvis/tech_news.json` cached tech headlines
- `~/.termux/boot/00-jarvis.sh` boot autostart