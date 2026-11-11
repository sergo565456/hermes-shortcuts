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

## Quick start (iPhone, 3 steps)

1. **Server** (once, after [Install](#install) and an HTTPS tunnel, see [Reaching it from your phone](#reaching-it-from-your-phone-https)):
   ```bash
   hermes shortcuts pair
   ```
   A QR code appears in the terminal. It holds your server URL and your token, so don't screenshot or share it.
2. **iPhone:** install **[Hermes Setup](https://www.icloud.com/shortcuts/4846c3cb4ee14f00a7d966b88465d3c9)**, run it, and scan the QR code. It saves the
   pairing to *iCloud Drive → Shortcuts → `hermes.json`* and says "Hermes paired".
3. **iPhone:** install the shortcuts you want. They need no editing because they read `hermes.json`:
   **[Ask Hermes](https://www.icloud.com/shortcuts/84873f84e6d7400d9fc0a6f3b8c011ea)** (Siri), **[Hermes](https://www.icloud.com/shortcuts/f6cb4e1fb6ba40788a0d4555925d9b64)** (Share Sheet: links and text
   from any app). *Hermes Photo* (recipe below) is optional.

Then say *"Hey Siri, Ask Hermes"*, or share a link and choose **Hermes**.

`hermes shortcuts pair` options: `--url https://your-host` (else `SHORTCUTS_PUBLIC_URL`, else the URL of a
cloudflared quick tunnel running on this machine), `--invert` (light terminal background), `--png FILE` (saves a
0600 PNG; delete it after pairing), `--show-token` (also prints the token as text; off by default). If your Hermes
build has no plugin CLI commands, run `python3 ~/.hermes/plugins/hermes-shortcuts/pair.py pair` with
`SHORTCUTS_TOKEN` in the environment instead.

Has the tunnel URL changed, or did you rotate the token? Run `hermes shortcuts pair` again and re-run *Hermes Setup*.
The other shortcuts don't need changes.

> **Maintainers, one-time step:** Apple doesn't let you generate shortcuts as files, and an installable shortcut
> only exists as an iCloud link from a real device. The three links above were built on an iPhone (recipes below,
> step by step in Russian in [`docs/ios-build-guide-ru.md`](docs/ios-build-guide-ru.md)). If you rebuild one, open
> ⋯ → **Share** (⤴) → **Copy iCloud Link** and update its link above. These shortcuts contain **no URL or token**, because both live
> in each user's `hermes.json`. That makes the links safe to publish. Before you share, open each shortcut and check
> that no `Authorization` value contains a literal token.

### Why not the built-in webhook adapter?
Hermes already has a generic webhook adapter (port 8644). It's built for GitHub, Stripe and similar services and
needs **HMAC-signed** bodies, which iOS Shortcuts can't compute. `hermes-shortcuts` is made for phones:

* **simple bearer token** (one header in "Get Contents of URL")
* **multipart file and photo uploads**, plus raw image bodies
* **action presets** (`summarize`, `remember`, `remind`, `post`, `receipt`, `whiteboard`, `document`, `auto`)
* a **synchronous reply** that Siri can read aloud, with a timeout fallback to Telegram
* **one-scan iPhone pairing** (`hermes shortcuts pair` + the *Hermes Setup* shortcut) and ready-made recipes

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
printf 'header = "Authorization: Bearer %s"\n' "$T" | curl -s -K - -d "text=What's 2+2?" http://127.0.0.1:8645/v1/ask
unset T
```
(`-K -` reads the header from stdin, so the token never appears in `ps` output for other local users.)

To pair an iPhone, run `hermes shortcuts pair` (see [Quick start](#quick-start-iphone-3-steps)). For manual or Android
setup you can read the token on the server with `grep ^SHORTCUTS_TOKEN= ~/.hermes/.env | cut -d= -f2-`. Don't paste it
into chats, issues or screenshots.

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
`CF-Connecting-IP`), that header is used only to key the auth-failure lockout per client (IPv6 per /64), and only
when the TCP peer is loopback (your local tunnel/proxy). Cloudflare refuses client-supplied `CF-Connecting-IP`, but
**any local process that can reach 127.0.0.1** can set it, including traffic from a VPN/proxy server on the same
host (e.g. Xray/V2Ray/Hysteria with no rule blocking private destinations) and other local users. The lockout is a
convenience, not the security boundary: the 256-bit token is. A global cap (300 failed attempts / 5 min) still
applies to everyone, and the valid token is never locked out. If you run a proxy/VPN on the same server, block
private/loopback destinations in it.

Binding a non-loopback address directly requires `SHORTCUTS_HOST=0.0.0.0` **and**
`SHORTCUTS_ALLOW_PUBLIC_BIND=true`. Plain HTTP over the internet would expose your token, so use a tunnel instead.

## Configuration

All settings are environment entries read through `agent.secret_scope.get_secret`. Set them with `hermes config set NAME value`.
Optional YAML overrides go in `config.yaml → gateway.platforms.shortcuts.extra`.

| Env | Default | Meaning |
|---|---|---|
| `SHORTCUTS_TOKEN` | — (required, ≥32 random chars) | Bearer token. Without it the plugin doesn't listen |
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
| `SHORTCUTS_PUBLIC_URL` | — | Public HTTPS base URL that `hermes shortcuts pair` puts in the QR (else auto-detected from a local cloudflared quick tunnel) |
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
| `ask` (Siri) | `web`, `vision`, `cronjob`, `todo` |
| events | `cronjob`, `todo` |

Every list also carries `no_mcp`, so your globally enabled MCP servers are **not** added to shortcuts turns.
On top of that, a `pre_tool_call` hook (active only in shortcuts sessions, fail-closed) blocks any tool outside the
action's list (other plugins' tools, MCP tools, terminal/file/code even if a Hermes fallback widened the toolset), lets
`cronjob` only **create** or **list** jobs (no update/remove/run, no `script`, `no_agent`, `monitor`, `workdir`,
`context_from`, skills or model/provider), allows delivery only to your home channel, and forces every job created from
the phone to run with **no tools** (`enabled_toolsets: []`) and **once** (`repeat: 1`; raise the cap with
`SHORTCUTS_MAX_REMINDER_REPEAT`, max 100), at most 3 per request. Without that, a reminder job would run later with your
cron toolset, which includes the terminal by default, and injected text could start an every-minute job you can only
remove from Telegram or the CLI.

Backstop for the unlikely case that the plugin fails to load its hook: pin the platform's default too, so a Hermes
fallback can never be the full toolset:

```yaml
platform_toolsets:
  shortcuts: [web, vision, no_mcp]
```

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

All Hermes shortcuts share one config file written by **Hermes Setup**: `hermes.json` in the **Shortcuts**
folder of iCloud Drive (in the Files app: *iCloud Drive → Shortcuts*). Its content is the QR payload:

```json
{"v": 1, "url": "https://your-host.example", "token": "…"}
```

Action names below are the English iOS 17/18 names, with the Russian UI names in parentheses (*Команды* app).
To add an action, tap **Add Action** / the search field at the bottom (*Поиск действий*) and type its name.
To insert a variable into a field, tap the field and pick it from the bar above the keyboard, or long-press
the field and choose **Select Variable** (*Выбрать переменную*).

### 0. "Hermes Setup" (scan the pairing QR, once per phone)
1. Shortcuts → **+** → rename it **Hermes Setup**.
2. **Scan QR or Barcode** (*Сканировать QR-код или штрихкод*).
3. **Get Dictionary from Input** (*Получить словарь из ввода*). Input: *QR/Barcode*, which is filled in automatically.
4. **Get Dictionary Value** (*Получить значение из словаря*): *Value* for key `token` in *Dictionary*.
5. **If** (*Если*) *Dictionary Value* **has any value** (*имеет любое значение*). Inside **Otherwise**
   (*Иначе*): **Show Alert** (*Показать предупреждение*) "Not a Hermes pairing code", then **Stop This Shortcut**
   (*Остановить эту команду*). Leave the *If* branch empty.
6. After **End If**: **Save File** (*Сохранить файл*). Input: **Dictionary** (the result of step 3; tap the
   input and pick *Dictionary*). Destination: **Shortcuts** (the default folder). Expand the action (›) and set:
   **Ask Where to Save** off (*Спрашивать, куда сохранить*), **Subpath** `hermes.json` (*Подпуть*),
   **Overwrite If File Exists** on (*Перезаписать, если файл существует*).
7. **Show Alert** (*Показать предупреждение*): `Hermes paired`.
8. Run it. When asked, allow camera access, then scan the QR from `hermes shortcuts pair`. Then type `clear`
   in the server terminal.

### 1. "Ask Hermes" (Siri voice)
Steps 1–6 are the **config block**. Every other Hermes shortcut starts with it.
1. **Get File** (*Получить файл*). Tap the folder and choose **Shortcuts**. Turn **Show Document Picker** off
   (*Показать окно выбора документов*), set **File Path** to `hermes.json` (*Путь к файлу*), and turn
   **Error If Not Found** on (*Ошибка, если не найдено*).
2. **Get Dictionary from Input** (*Получить словарь из ввода*). Input: *File*.
3. **Get Dictionary Value** (*Получить значение из словаря*): *Value* for key `url` in *Dictionary*.
4. **Set Variable** (*Задать переменную*) named `HermesURL` to *Dictionary Value*.
5. **Get Dictionary Value**: *Value* for key `token` in **Dictionary** (tap the input and pick the *Dictionary*
   from step 2, not the previous value).
6. **Set Variable** `HermesToken` to *Dictionary Value*.
7. **Dictate Text** (*Диктовать текст*). Expand it and set **Stop Listening** to *After Pause* (*После паузы*).
8. **Get Contents of URL** (*Получить содержимое URL*). In the URL field, insert the variable `HermesURL`, then
   type `/v1/ask?format=text` right after it, with no space. Expand it (›, *Show More*) and set:
   * **Method** (*Метод*): `POST`
   * **Headers** (*Заголовки*) → **Add new header** (*Добавить новый заголовок*): Key `Authorization`,
     Value: type `Bearer` **plus one space**, then insert the variable `HermesToken`.
   * **Request Body** (*Тело запроса*): **JSON** → **Add new field** (*Добавить новое поле*) → **Text**
     (*Текст*): Key `text`, Value: *Dictated Text* (*Продиктованный текст*).
9. **Speak Text** (*Произнести текст*). Input: *Contents of URL* (*Содержимое URL*).
10. Name it **Ask Hermes**. The name is the Siri phrase: *"Hey Siri, Ask Hermes"*. The first run asks for permission
    to read `hermes.json` and to connect to your host. Choose **Always Allow** (*Всегда разрешать*).

Siri waits about 25 s (`SHORTCUTS_SYNC_TIMEOUT`). Longer jobs say "Working on it…" and finish in Telegram.

### 2. "Hermes" (Share Sheet: links and text PDFs, screenshots)
1. New shortcut **Hermes**. Tap ⓘ (*Details*, *Сведения*) → turn on **Show in Share Sheet** (*Показывать в меню
   «Поделиться»*). In the *Receive* block at the top, choose **URLs, Text, Safari web pages, Images, PDFs, Files**.
   If there's no input: **Ask For** → *Text* (*Запросить*).
2. The **config block** (steps 1–6 of *Ask Hermes*).
3. **Choose from Menu** (*Выбрать из меню*), prompt `Hermes:`, with items `Summarize`, `Remember`, `Remind`, `Post`,
   `Auto`. Inside each item add **Text** (*Текст*) with the lowercase action (`summarize`, `remember`, …).
4. After **End Menu**: **Set Variable** `Action` to *Menu Result* (*Результат меню*).
5. (Optional, for Remind) **Ask for Input** (*Запросить ввод*) `When?`, then **Set Variable** `When`.
6. **Get Contents of URL**. URL: `HermesURL` + `/v1/share`. Method **POST**, header `Authorization` =
   `Bearer ` + `HermesToken` (as in *Ask Hermes*). Request Body **Form** (*Форма*) with Text fields
   `action` = `Action`, `text` = *Shortcut Input* (*Входные данные команды*), and optionally `when` = `When`.
7. **Get Dictionary Value** `reply` from *Contents of URL* → **Show Result** (*Показать результат*).

### 3. "Hermes Photo" (photo as task)
1. New shortcut **Hermes Photo** (add it to the Home Screen or the Action Button).
2. The **config block**.
3. **Take Photo** (*Сделать фото*), or **Select Photos** (*Выбрать фото*) → **Convert Image** (*Конвертировать
   изображение*) to **JPEG**, quality ~0.7. HEIC is rejected, and JPEG keeps uploads small.
4. **Choose from Menu**: `Receipt` / `Whiteboard` / `Document` / `Auto`. Inside each item add **Text** with the
   lowercase name, then after the menu **Set Variable** `Action` = *Menu Result*.
5. **Get Contents of URL**. URL: `HermesURL` + `/v1/share`, **POST**, header `Authorization` = `Bearer ` +
   `HermesToken`. Request Body **Form**: `action` (Text) = `Action`, `file` (**File**, *Файл*) = *Converted Image*.
6. **Get Dictionary Value** `reply` → **Show Result**.

### 4. Event triggers (Automations)
Shortcuts → **Automation** (*Автоматизация*) → **+** → *Arrive* (Home), *Alarm* (is stopped), *Charger* (is
connected)… → **Run Immediately** (*Запускать сразу*). Add the **config block**, then **Get Contents of URL**:
`HermesURL` + `/v1/event`, POST, header `Authorization` = `Bearer ` + `HermesToken`, JSON body `event` =
`arrived_home` (or `alarm_off`, `charger_connected`, a custom name). The reply goes to Telegram.

### Troubleshooting
* **"File not found" / "hermes.json"**: run *Hermes Setup* again. In the Files app, check that *iCloud Drive →
  Shortcuts* contains `hermes.json` (not `hermes.json.txt`). If iCloud Drive is off, look under *On My iPhone →
  Shortcuts*.
* **401 / "unauthorized"**: the token changed. Run `hermes shortcuts pair` and *Hermes Setup* again. Also check that
  the header value is `Bearer`, one space, then the token.
* **Can't connect**: the quick-tunnel URL changed. Run `hermes shortcuts pair` again and re-scan.
* **QR won't scan**: run with `--invert`, make the terminal font smaller or the window larger, or use
  `--png FILE` and open the file on your computer (then delete it).

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
  computer-use, delegation, skill writing or MCP tools**, enforced twice (see *Per-action toolsets*). With `full`, a token holder (or a prompt injection in a page you shared)
  gets your gateway's full toolset, including the terminal on your server, and cron jobs it creates run later with
  your cron toolset (terminal included). Only switch to `full` if you need it.
* **Approvals are never bypassed or auto-approved.** This surface has no approval buttons and `/approve` is disabled here,
  so a command that needs approval waits for the approval timeout and is then denied. Note that Hermes only asks for
  approval for commands it considers dangerous; ordinary commands (e.g. `curl`) run without asking, which is why the
  `safe` profile removes the terminal entirely.
* **Untrusted input / prompt injection:** links, PDFs, images and text you share can contain instructions aimed at the
  agent. Shared content is fenced with a random per-request marker, fence-like text inside it is neutralised, control
  characters are stripped, text is capped at 8,000 chars, and slash commands / gateway control are disabled
  (`allow_gateway_control=False`). **@-references are defanged:** Hermes core expands `@file:`, `@folder:`, `@url:`,
  `@git:`, `@diff` in *every* inbound message before the agent runs (no tool call, so no tool policy applies), relative to
  the gateway's working directory; in shared text the plugin turns `@` into `＠` so a shared note cannot pull e.g.
  `~/.hermes/logs/gateway.log` (your Telegram message previews) into the turn. `/v1/share` with `action=ask` is run as a
  fenced `auto` turn. Fencing reduces but cannot eliminate injection; the restricted toolset is what limits
  the damage. Hermes' own web tools block private/internal addresses (SSRF), but in the `full` profile the agent can
  still reach them through the terminal. **Stored injection:** `remember` writes shared content into long-term memory, and memory is part of the
  system prompt of *every* later session, including Telegram/CLI sessions that have the terminal. Use `remember` only
  on content you trust and review `~/.hermes/memories/` now and then. `remind` stores (part of) the shared content as
  the cron prompt; jobs created from the phone run with no tools, so at worst they deliver odd text.
* **Exfiltration:** every turn sees your memory and user profile (as on every platform). A malicious page could try
  to make the agent put that text into a `web_extract`/`web_search` URL. The safe profile keeps `session_search`
  (your whole chat history) out of every action, and events get no web tools.
* **Link previews (zero-click):** Telegram fetches a preview of the first link in a bot message from its servers, so a
  URL in a forwarded reply is fetched without you tapping it. The plugin puts every URL of a forwarded reply in a code
  span (no link, no preview) and shows hidden markdown links as `text (url)`. Also set
  `platforms.telegram.extra.disable_link_previews: true` in `config.yaml` to cover Telegram replies from other sessions.
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
* **Pairing CLI:** `hermes shortcuts pair` (registered with `register_cli_command`) prints the URL and a QR code that
  contains the token. It never logs the token and prints it as text only with `--show-token`. `--png` files are written
  0600 without following symlinks. To find a quick-tunnel URL it queries only cloudflared's local metrics endpoint
  (`127.0.0.1:20241-20245/quicktunnel`, no proxy). The QR is rendered by a vendored copy of Project Nayuki's MIT-licensed
  pure-Python QR generator (`_qrcodegen.py`), so pairing installs nothing.

### Your token on the phone
* **With pairing (recommended):** *Hermes Setup* stores the URL and token in plain text in
  `iCloud Drive/Shortcuts/hermes.json`. The shortcuts themselves contain **no token**, so sharing or publishing a
  shortcut never leaks it. Trade-offs, honestly:
  * The file **syncs to iCloud** and your other Apple devices, like everything in iCloud Drive. Apple holds the keys
    unless you turn on **Advanced Data Protection** (Settings → your name → iCloud), which makes iCloud Drive
    end-to-end encrypted. Shortcuts' Save File / Get File actions work in the Shortcuts folder of iCloud Drive, and
    you can't pick a device-only location for it while iCloud Drive is on (with iCloud Drive off, the folder lives
    *On My iPhone*). The manual alternative, pasting the token into each shortcut, is no better: the shortcuts sync
    through iCloud too (also end-to-end only with ADP), and the token travels with every shortcut you share.
  * Any shortcut on the phone that you allow to read files in the Shortcuts folder can read `hermes.json`. Only
    install shortcuts you trust, and deny file access to ones that don't need it.
  * The QR code shown by `hermes shortcuts pair` holds the token. Don't screenshot or photograph it, clear the
    terminal afterwards, and delete any `--png` file.
* **Manual setup** (no Setup shortcut): **iOS Shortcuts stores header values in plain text inside the shortcut.**
  Sharing such a shortcut (iCloud link, AirDrop, file) shares your token with it.
* **Android HTTP Shortcuts** keeps variables in the app's data, and app exports/backups contain them. Don't share
  export files, and exclude the `token` variable when exporting.
* Never put the token in the URL. The plugin rejects tokens in query strings, and URLs end up in logs.

### Rotating the token (do it if a phone is lost, a shortcut or QR was shared, or the token leaked)
1. On the server: `hermes config set SHORTCUTS_TOKEN "$(openssl rand -hex 32)"`, then `hermes gateway restart`. The
   old token stops working immediately, including any old QR code and any `hermes.json` copy.
2. Run `hermes shortcuts pair` and re-run *Hermes Setup* on each of your phones (it overwrites `hermes.json`).
   With manual setup, update the `Authorization` header in each shortcut or the HTTP Shortcuts variable instead.
3. If you use Cloudflare Access, also rotate the service token in the Zero Trust dashboard.

## Development

```bash
cd tests && python3 -m pytest -q          # unit + adapter tests (auth, lockout, toolsets, uploads, fencing)
hermes plugins validate ./hermes-shortcuts
hermes plugins doctor ./hermes-shortcuts --ci
```

Layout: `plugin.yaml`, `__init__.py` (exports `register`), `adapter.py` (gateway platform adapter and aiohttp listener),
`actions.py` (presets, prompt fencing, token and rate-limit helpers), `pair.py` (`hermes shortcuts pair`),
`_qrcodegen.py` (vendored QR generator, MIT), `docs/ios-build-guide-ru.md` (maintainer build guide, Russian), `tests/`, `plugin-catalog/hermes-shortcuts.yaml` (draft catalog entry).

License: MIT
