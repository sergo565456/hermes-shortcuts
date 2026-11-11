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

# 1) a strong random token (256 bit), stored through Hermes' own credential route (~/.hermes/.env, never config.yaml).
#    The plugin refuses to listen with a token that is missing, shorter than 32 chars, repetitive or a placeholder.
hermes config set SHORTCUTS_TOKEN "$(openssl rand -hex 32)"
#    (no openssl? python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
# 2) the gateway allowlist for this platform (requests always arrive as user "owner"; see Security)
hermes config set SHORTCUTS_ALLOWED_USERS owner

hermes gateway restart        # or: systemctl --user restart hermes-gateway
```

The gateway log then shows `[shortcuts] listening on http://127.0.0.1:8645` and `✓ shortcuts connected`.
Check it from the server:

```bash
curl -s http://127.0.0.1:8645/health
T="$(grep ^SHORTCUTS_TOKEN= ~/.hermes/.env | cut -d= -f2-)"   # stays in your shell, not in history or logs
curl -s -H "Authorization: Bearer $T" -d "text=What's 2+2?" http://127.0.0.1:8645/v1/ask
```

To read your token later (to paste it into the Shortcut), run on the server:
`grep ^SHORTCUTS_TOKEN= ~/.hermes/.env | cut -d= -f2-`. Don't paste it into chats, issues or screenshots.

Replies are forwarded to the **home channel** of `SHORTCUTS_NOTIFY_TARGET` (default `telegram`). Set your
Telegram home channel once with `/sethome` in your bot chat (or `TELEGRAM_HOME_CHANNEL`).

### Reaching it from your phone (HTTPS)
The listener binds **127.0.0.1 only** by default. Put an HTTPS tunnel or reverse proxy in front of it and point the
Shortcut at that URL:

* **Tailscale** (most private): `tailscale serve --bg 8645` keeps it inside your tailnet; nothing is on the public
  internet. Needs the Tailscale app on the phone.
* **Cloudflare named tunnel + Cloudflare Access** (recommended for a public URL): route a hostname on your domain to
  `http://127.0.0.1:8645` and protect it with an Access application whose policy is *Service Auth* with a
  **service token**. Add the two headers `CF-Access-Client-Id` / `CF-Access-Client-Secret` to every Shortcut next to
  `Authorization`; requests without them never reach your server. Set `SHORTCUTS_CLIENT_IP_HEADER=CF-Connecting-IP`.
* **Cloudflare quick tunnel** (testing only): `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8645` gives a
  random `https://<random>.trycloudflare.com` URL that changes on every restart. There is no access control besides the
  bearer token, and Cloudflare documents quick tunnels as not for production.
* **Caddy / nginx** reverse proxy with a real certificate (needs root for ports 80/443). Proxy to 127.0.0.1 only, and
  make sure the proxy's access log does **not** record the `Authorization` header.

The plugin never trusts `X-Forwarded-For` for anything. If you set `SHORTCUTS_CLIENT_IP_HEADER` (e.g.
`CF-Connecting-IP`), that header is used only to key the auth-failure lockout per client, and only when the TCP peer
is loopback (your local tunnel/proxy), so it cannot be spoofed from outside.

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
| `SHORTCUTS_MAX_UPLOAD_MB` | `15` | Upload cap per request (1–50) |
| `SHORTCUTS_MAX_UPLOAD_MB_PER_HOUR` | `200` | Total upload budget per hour (bounds media-cache disk use) |
| `SHORTCUTS_TOOL_PROFILE` | `safe` | `safe`: each action gets only the toolsets it needs (no terminal/file/code/browser). `full`: the platform's normal toolset |
| `SHORTCUTS_CLIENT_IP_HEADER` | — | e.g. `CF-Connecting-IP` behind cloudflared; only honoured from a loopback peer, only for the lockout |

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

Per-action toolsets in the `safe` profile (override in `config.yaml → gateway.platforms.shortcuts.extra.toolsets`,
keys `ask`, `event`, `remember`, `remind`, `_shared`; values are Hermes toolset names):

| Action | Toolsets |
|---|---|
| `summarize`, `auto`, `post`, `receipt`, `whiteboard`, `document` | `web`, `vision` |
| `remember` | `web`, `vision`, `memory` |
| `remind` | `web`, `vision`, `cronjob` |
| `ask` (Siri) | `web`, `vision`, `memory`, `cronjob`, `todo`, `session_search` |
| events | `web`, `memory`, `cronjob`, `todo`, `session_search` |

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

* **What it runs:** a long-lived HTTP listener (aiohttp) inside the Hermes gateway process on `127.0.0.1:8645`. It does
  nothing until `SHORTCUTS_TOKEN` is set **and** the plugin is enabled, and it refuses to start with a missing, short
  (< 32 chars), repetitive or placeholder token. Binding a non-loopback address needs `SHORTCUTS_HOST` **and**
  `SHORTCUTS_ALLOW_PUBLIC_BIND=true`; don't do that, use a tunnel or proxy with HTTPS (plain HTTP leaks the token).
* **The token is the only identity.** Every request arrives as the single user `owner`; `SHORTCUTS_ALLOWED_USERS=owner`
  just satisfies the gateway allowlist. There are no per-person accounts: anyone holding the token acts as you, so never
  give it to anyone, and use one Hermes install per person.
* **What a request can do:** it runs a normal agent turn. With the default `SHORTCUTS_TOOL_PROFILE=safe`, shortcuts
  turns only get the toolsets their action needs (table above): **no terminal, file, code execution, browser,
  computer-use, delegation or skill writing**. With `full`, a token holder (or a prompt injection in a page you shared)
  gets your gateway's full toolset, including the terminal on your server. Only switch to `full` if you need it.
* **Approvals are never bypassed or auto-approved.** This surface has no approval buttons and `/approve` is disabled here,
  so a command that needs approval waits for the approval timeout and is then denied. Note that Hermes only asks for
  approval for commands it considers dangerous; ordinary commands (e.g. `curl`) run without asking, which is why the
  `safe` profile removes the terminal entirely.
* **Untrusted input / prompt injection:** links, PDFs, images and text you share can contain instructions aimed at the
  agent. Shared content is fenced with a random per-request marker, fence-like text inside it is neutralised, control
  characters are stripped, text is capped at 8,000 chars, and slash commands / gateway control are disabled
  (`allow_gateway_control=False`). Fencing reduces but cannot eliminate injection; the restricted toolset is what limits
  the damage. Hermes' own web tools block private/internal addresses (SSRF), but in the `full` profile the agent can
  still reach them through the terminal. `remember` writes to long-term memory and `remind` creates cron jobs, so only
  use them on content you trust; cron jobs run later with Hermes' cron toolset.
* **Limits:** uploads ≤ 15 MB per request and 200 MB per hour (configurable), ≤ 4 files, 20 requests/min, 3 concurrent,
  auth-failure lockout (10 failures / 5 min per client, which never locks out the valid token). Images are
  type-sniffed by magic bytes; HEIC is rejected; document names are reduced to a safe basename. Files from a rejected
  request are deleted.
* **Privacy / data:** shared content goes to your LLM provider like any message. Uploaded files are written to Hermes'
  media cache (`~/.hermes/cache/…`, pruned after ~24 h). Every request is a fresh gateway session
  (`agent:main:shortcuts:dm:sc-…`) kept in Hermes' session database (`state.db`) like your other chats. The plugin never
  logs the token or request bodies, but Hermes core logs a short preview (~80 chars) of every inbound message and the
  URLs its web tools fetch, as on every platform. Replies are forwarded to your home channel unless `notify=false`.
* **Outbound:** replies go only to your own home channel on `SHORTCUTS_NOTIFY_TARGET` (Telegram by default) through the
  live gateway adapter; anything Hermes delivers to the `shortcuts` home channel (e.g. cron output) is forwarded there
  too. The plugin makes no other network calls, has no telemetry and no self-update.
* **Credentials** are read only through `agent.secret_scope.get_secret`. The plugin never reads `.env` or credential files.

### Your token on the phone
* **iOS Shortcuts stores header values in plain text inside the shortcut.** Sharing a shortcut (iCloud link, AirDrop,
  file) shares your token with it. Before sharing a recipe, replace the token with `YOUR_TOKEN`, or keep the token in
  an *Import Question* so each person enters their own. Shortcuts also syncs through iCloud to your other devices.
* **Android HTTP Shortcuts** keeps variables in the app's data; app exports/backups contain them. Don't share export
  files, and exclude the `token` variable when exporting.
* Never put the token in the URL; the plugin rejects tokens in query strings, and URLs end up in logs.

### Rotating the token (do it if a phone is lost, a shortcut was shared, or the token leaked)
1. On the server: `hermes config set SHORTCUTS_TOKEN "$(openssl rand -hex 32)"` then `hermes gateway restart`.
2. The old token stops working immediately. Update the `Authorization` header in each Shortcut / HTTP Shortcuts variable.
3. If you use Cloudflare Access, also rotate the service token in the Zero Trust dashboard.

## Development

```bash
cd tests && python3 -m pytest -q          # unit + adapter tests (auth, lockout, toolsets, uploads, fencing)
hermes plugins validate ./hermes-shortcuts
hermes plugins doctor ./hermes-shortcuts --ci
```

Layout: `plugin.yaml`, `__init__.py` (exports `register`), `adapter.py` (gateway platform adapter and aiohttp listener),
`actions.py` (presets, prompt fencing, token and rate-limit helpers), `tests/`, `plugin-catalog/hermes-shortcuts.yaml` (draft catalog entry).

License: MIT
