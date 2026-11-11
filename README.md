# hermes-shortcuts

**Share to Hermes, ask Hermes with Siri, and photograph a task, all from iOS Shortcuts or Android HTTP Shortcuts.**

`hermes-shortcuts` is a Hermes Agent gateway platform plugin. It adds one small, token-protected HTTP
endpoint that your phone can call:

| You do on the phone | What Hermes does | Where the answer goes |
|---|---|---|
| **Share Sheet**: Share → *Hermes* on a link, article, YouTube video, text, PDF or screenshot, then pick **Summarize / Remember / Remind / Post / Auto** | Runs a normal agent turn with that action preset (web tools, memory, cron, vision) | Shown in Shortcuts **and** sent to your Telegram home channel |
| **"Hey Siri, Ask Hermes"**: dictate a question | Answers it | Siri **speaks** the reply (synchronous). If it takes longer than the timeout, Siri says "working on it" and the answer goes to Telegram |
| **Photo as task**: snap a receipt, whiteboard or document | Extracts the expense line, transcribes it and makes a checklist, or digitizes the document | Shortcuts + Telegram |
| **Event triggers** (Shortcuts Automations): *Arrive home*, *Alarm stopped*, *Charger connected*… | Runs the prompt you mapped to that event (morning briefing, evening recap…) | Telegram |

### Why not the built-in webhook adapter?
Hermes already has a generic webhook adapter (port 8644). It's built for GitHub, Stripe and similar services and
needs **HMAC-signed** bodies, which iOS Shortcuts can't compute. `hermes-shortcuts` is made for phones:

* **simple bearer token** (one header in "Get Contents of URL")
* **multipart file and photo uploads**, plus raw image bodies
* **action presets** (`summarize`, `remember`, `remind`, `post`, `receipt`, `whiteboard`, `document`, `auto`)
* a **synchronous reply** that Siri can read aloud, with a timeout fallback to Telegram
* **ready-made Shortcut recipes** (below)

## Install

```bash
hermes plugins install <OWNER>/hermes-shortcuts
hermes plugins enable hermes-shortcuts

# 1) a strong token, stored through Hermes' own credential route (~/.hermes/.env, never config.yaml)
hermes config set SHORTCUTS_TOKEN "$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
# 2) the gateway allowlist for this platform (requests always arrive as user "owner")
hermes config set SHORTCUTS_ALLOWED_USERS owner

hermes gateway restart        # or: systemctl --user restart hermes-gateway
```

The gateway log then shows `[shortcuts] listening on http://127.0.0.1:8645` and `✓ shortcuts connected`.
Check it from the server:

```bash
curl -s http://127.0.0.1:8645/health
curl -s -H "Authorization: Bearer $YOUR_TOKEN" -d "text=What's 2+2?" http://127.0.0.1:8645/v1/ask
```

To read your token later (to paste it into the Shortcut), run on the server:
`grep ^SHORTCUTS_TOKEN= ~/.hermes/.env | cut -d= -f2-`

Replies are forwarded to the **home channel** of `SHORTCUTS_NOTIFY_TARGET` (default `telegram`). Set your
Telegram home channel once with `/sethome` in your bot chat (or `TELEGRAM_HOME_CHANNEL`).

### Reaching it from your phone (HTTPS)
The listener binds **127.0.0.1 only** by default. Put an HTTPS tunnel or reverse proxy in front of it and point the
Shortcut at that URL:

* **Cloudflare Tunnel** (no root needed): `cloudflared tunnel --url http://127.0.0.1:8645` gives a quick
  `https://<random>.trycloudflare.com` URL. For a stable one, use a named tunnel on your own domain.
* **Tailscale**: keep it private to your tailnet (`tailscale serve`), with the Tailscale app on the phone.
* **Caddy / nginx** reverse proxy with a real certificate (needs root for ports 80/443).

Binding a non-loopback address directly requires `SHORTCUTS_HOST=0.0.0.0` **and**
`SHORTCUTS_ALLOW_PUBLIC_BIND=true`. Plain HTTP over the internet would expose your token, so use a tunnel instead.

## Configuration

All settings are environment entries read through `agent.secret_scope.get_secret`. Set them with `hermes config set NAME value`.
Optional YAML overrides go in `config.yaml → gateway.platforms.shortcuts.extra`.

| Env | Default | Meaning |
|---|---|---|
| `SHORTCUTS_TOKEN` | — (required, ≥24 chars) | Bearer token. Without it the plugin doesn't listen |
| `SHORTCUTS_ALLOWED_USERS` | — | Set to `owner` (gateway allowlist) |
| `SHORTCUTS_HOST` | `127.0.0.1` | Bind address |
| `SHORTCUTS_PORT` | `8645` | Port |
| `SHORTCUTS_ALLOW_PUBLIC_BIND` | `false` | Required to bind a non-loopback address |
| `SHORTCUTS_SYNC_TIMEOUT` | `25` | Seconds to wait for a reply before answering "working on it" (3–120) |
| `SHORTCUTS_NOTIFY_TARGET` | `telegram` | Where replies are forwarded (any connected platform's home channel; `none` turns it off) |
| `SHORTCUTS_RATE_LIMIT` | `20` | Accepted requests per minute |
| `SHORTCUTS_MAX_UPLOAD_MB` | `15` | Upload cap (1–50) |

Custom event prompts (`config.yaml`):

```yaml
gateway:
  platforms:
    shortcuts:
      extra:
        events:
          arrived_home: "I'm home. What's left on my list for today?"
          gym: "I'm at the gym. Give me today's workout."
```
Built-in events: `arrived_home`, `arrived_office`, `alarm_off`, `charger_connected`.

## HTTP API

Auth: `Authorization: Bearer <token>` (or `X-Hermes-Token: <token>`). Tokens in the URL are not accepted.

| Endpoint | Body | Notes |
|---|---|---|
| `POST /v1/ask` | `text` (JSON, form, or a `text/plain` body) | Plain question. Not forwarded to Telegram unless `notify=true` or it times out |
| `POST /v1/share` | `action`, `text`, `url`, `file` (multipart, up to 4), `when` (for remind), `note` | Also accepts a raw `image/*` or `application/pdf` body with `?action=` |
| `POST /v1/event` | `event` | Runs the mapped event prompt |
| `GET /health` | — | Liveness only (no data) |

Common fields: `notify` (`auto`/`true`/`false`), `sync` (default `true`), `timeout` (seconds), `format=text`
(returns the bare reply text, which is handy for *Speak Text*).

Response (JSON):
```json
{"ok": true, "status": "done", "action": "summarize", "reply": "TL;DR: …", "forwarded_to": "telegram"}
```
`status: "accepted"` (HTTP 202) means the sync wait timed out, and the result will arrive in Telegram.

Actions: `ask`, `auto` (Hermes decides), `summarize`, `remember` (saves to memory), `remind` (creates a cron
reminder delivered to Telegram; `when` is free text, default "tomorrow 09:00"), `post` (drafts a post and never
publishes it), `receipt`, `whiteboard`, `document`.

## iOS Shortcuts recipes

Replace `https://YOUR-HOST` with your tunnel URL and `YOUR_TOKEN` with your token. Every recipe uses the
**Get Contents of URL** action: tap *Show More*, set **Method: POST**, add the header
`Authorization` = `Bearer YOUR_TOKEN`, then set the **Request Body** as described.

### 1. "Hermes" Share Sheet shortcut (links, text, PDFs, screenshots)
1. New Shortcut → name it **Hermes**. Tap the ⓘ (Details) → turn on **Show in Share Sheet**. In the
   *Receive* block choose **URLs, Text, Images, PDFs, Safari web pages, Files**. If there's no input:
   **Ask For** Text.
2. **Choose from Menu** (prompt "Hermes:") with items `Summarize`, `Remember`, `Remind`, `Post`, `Auto`.
   Inside each item, add **Text** containing the lowercase action (`summarize`, …). After the menu, add
   **Set Variable** `Action` = *Menu Result*.
3. (Optional, Remind only) **Ask for Input** "When?" → `When`.
4. **Get Contents of URL** `https://YOUR-HOST/v1/share`, Method **POST**, header `Authorization`, Request Body
   **Form** with the fields:
   * `action` (Text) = `Action`
   * `text` (Text) = *Shortcut Input* (for links, Shortcuts passes the URL text, which is fine)
   * `when` (Text) = `When` (optional)
   * For images or PDFs, add a field `file` of type **File** = *Shortcut Input*. For photos, put
     **Convert Image** (Format: JPEG) before this step, because HEIC is rejected.
5. **Get Dictionary Value** `reply` from *Contents of URL* → **Show Result** (or **Show Notification**).

Tip: keep two copies. *Hermes* (text/URL, Form without `file`) and *Hermes Photo* (Images, with `file`) keep
each one simple.

### 2. "Ask Hermes" (Siri voice)
1. New Shortcut named **Ask Hermes**. The name is the Siri phrase: *"Hey Siri, Ask Hermes"*.
2. **Dictate Text** (Stop Listening: *After Pause*) → `Dictated Text`.
3. **Get Contents of URL** `https://YOUR-HOST/v1/ask?format=text`, Method **POST**, header `Authorization`,
   Request Body **JSON** with `text` (Text) = *Dictated Text*.
4. **Speak Text** *Contents of URL*. Or skip `format=text`, use JSON, add **Get Dictionary Value** `reply`, then **Speak Text**.

Siri waits about 25 s (`SHORTCUTS_SYNC_TIMEOUT`). Longer jobs say "Working on it…" and finish in Telegram.

### 3. "Hermes Photo" (photo as task)
1. New Shortcut **Hermes Photo** (add it to the Home Screen or the Action Button).
2. **Take Photo** (or *Select Photos*) → **Convert Image** to **JPEG**, quality 0.7 (smaller uploads).
3. **Choose from Menu**: `Receipt` / `Whiteboard` / `Document` / `Auto` → Text with the lowercase name → `Action`.
4. **Get Contents of URL** `https://YOUR-HOST/v1/share`, POST, header `Authorization`, Request Body **Form**:
   `action` (Text) = `Action`, `file` (File) = *Converted Image*.
5. **Get Dictionary Value** `reply` → **Show Result**.

### 4. Event triggers (Automations)
Shortcuts → **Automation** → **+** → *Arrive* (Home), *Alarm* (is stopped), *Charger* (is connected)… →
**Run Immediately** → action **Get Contents of URL** `https://YOUR-HOST/v1/event`, POST, header
`Authorization`, JSON body `event` = `arrived_home` (or `alarm_off`, `charger_connected`, a custom name).
The reply goes to Telegram.

## Android (HTTP Shortcuts app)
1. Install **HTTP Shortcuts** (F-Droid / Play). Create a **Variable** `token` (type *Constant*, value your token)
   and a variable `shared` (type *Text*, check *Allow receiving value from Share dialog*).
2. New shortcut **Hermes: summarize**: Method **POST**, URL `https://YOUR-HOST/v1/share`, header
   `Authorization: Bearer {{token}}`, Request Body **Form data**: `action=summarize`, `text={{shared}}`.
   Response handling: *Show in dialog*. Under *Trigger & Execution*, enable **Show in share menu**.
   Duplicate it for `remember`, `remind`, `post`.
3. **Photo**: Request Body *File* (*Form data* with a file parameter `file`, "Pick file / take photo").
4. **Voice**: add a *Text input* variable `q` (the keyboard mic does dictation) → POST `/v1/ask?format=text`
   with body `text={{q}}`, and display the response. In Tasker, *HTTP Request* + *Say* gives spoken replies.

## Security and disclosure

**Read this before installing.**

* **Runs a long-lived HTTP listener** inside the Hermes gateway process (aiohttp) on `127.0.0.1:8645` by default.
  It does nothing until `SHORTCUTS_TOKEN` is set **and** the plugin is enabled. Binding a non-loopback address
  needs an explicit `SHORTCUTS_ALLOW_PUBLIC_BIND=true`.
* **Authentication is a single bearer token.** It's compared in constant time and must be at least 24 characters.
  Anyone with the token can run agent turns **with your gateway's tools** (web, memory, cron, terminal, per your
  toolset config), the same as messaging your bot. Treat it like a password. Rotate it with `hermes config set SHORTCUTS_TOKEN …`.
* Only expose it through **HTTPS** (tunnel or reverse proxy). Plain HTTP leaks the token.
* **Approvals are never bypassed.** Dangerous commands still go through Hermes' approval system. This surface has no
  approval buttons, so such requests are not auto-approved and fail or time out safely. Use Telegram for those tasks.
* **Untrusted input:** shared content is fenced as untrusted data in the prompt, slash commands and gateway control are
  disabled for these messages (`allow_gateway_control=False`), control characters are stripped, and text is capped at 8,000 chars.
* **Limits:** uploads ≤ 15 MB (configurable), ≤ 4 files, 20 requests/min, 3 concurrent, auth-failure lockout
  (10 failures / 5 min). Images are type-sniffed by magic bytes. HEIC is rejected.
* **Data:** uploaded files are written to Hermes' standard media cache (`~/.hermes/cache/…`) so the agent can see them.
  Every request is a fresh gateway session (`agent:main:shortcuts:dm:sc-…`) stored in Hermes' normal session database.
* **Outbound:** replies are sent to your own home channel on the platform in `SHORTCUTS_NOTIFY_TARGET` (Telegram by default)
  through the live gateway adapter. The plugin makes no other network calls, has no telemetry and no self-update.
* Credentials are read only through `agent.secret_scope.get_secret`. The plugin never reads `.env` or credential files itself.
  Tokens and request bodies are never logged.

## Development

```bash
cd tests && python3 -m pytest -q          # pure unit tests (actions, auth, rate limit)
hermes plugins validate ./hermes-shortcuts
hermes plugins doctor ./hermes-shortcuts --ci
```

Layout: `plugin.yaml`, `__init__.py` (exports `register`), `adapter.py` (gateway platform adapter and aiohttp listener),
`actions.py` (presets, prompt fencing, token and rate-limit helpers), `tests/`, `plugin-catalog/hermes-shortcuts.yaml` (draft catalog entry).

License: MIT
