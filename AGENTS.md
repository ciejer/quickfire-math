# Quickfire Math — Agents Guide

This app is a self-hosted FastAPI + SQLModel web app (Dockerised) that helps kids practise core maths facts via fast drills with friendly audio and clear feedback. It runs as an HTTP server inside the container and persists data to a SQLite file mounted at `/data`.

## What the product does (behavioural contract)

* **Drills** are always **20 questions** of a single type (addition, subtraction, multiplication, division).
* UI shows a **vertical equation layout** (big digits), an **answer field** and **Enter**.
  Wrong answers are **spoken aloud** (TTS) and also **shown in a 3-second overlay**, then **re-queued** to appear again **within 3–5 problems**.
* A **timer** runs during the drill. On **correct** answers: a short **ding**. On **finish**: a brief **win sound**.
* **Digit colouring**: every digit `0–9` is consistently colour-coded across the **equation** and **wrong-answer overlay** only (not in timer/feed/reports).
* **Newsfeed** in the right sidebar shows recent drills immediately after finishing: date/time (local), drill type + level, level label, score, and time. A ⭐ appears on starred drills.
* **Progression** uses **stars**: you earn a star when you meet accuracy and time targets; levelling up requires **3 stars within your last 5 drills** for that operation.
  After level-up, stars reset and bests reset for the new level.
* **Targets**: on level-up, a **new per-level time target** is saved as `min(TMAX, best_previous_level_time * 1.5)`. We don’t show this target unless the player misses the star on time.
* **Dashboard** (“choose a drill”) shows four large cards (2×2 grid), one per operation, each with **Level N**, **last-five star ring**, and **plain language hint** like “Need 2 stars in the next 4 rounds to level up”.
* **Login** is name-only (no passwords). Users can add themselves. **Admin** can delete users and manage admin password.
* **Admin password** is generated on first boot (two words + number) and printed to logs every startup. It’s stored in DB and can be changed; the current value is still printed each boot.

---

## Project structure

All code lives under `app/`.

* **Entry & startup**

  * `app/main.py` – FastAPI app factory, mounts static, includes routers, runs DB init and admin password check on startup.
  * `app/deps.py` – wires Jinja2 templates directory for server-side rendering.

* **Routers** (`app/routers/`)

  * `auth.py` – `/` login screen, POST `/login`, POST `/user/add` (no passwords), cookie `uid`.
  * `dashboard.py` – GET `/dashboard` (formerly `/home`), serves the drill selection page.
  * `drills.py` – POST `/start`, `/next`, `/finish` endpoints.
  * `feeds.py` – GET `/feed` (recent drills + star flags), `/stats` (today counts, localised), `/progress` (per-op level + last-five stars + hint).
  * `reports.py` – GET `/report/multiplication|addition|subtraction` (heatmap data).
  * `admin.py` – GET `/admin`, POST `/admin/login`, POST `/admin/logout`, POST `/admin/delete_user`.

* **Utilities** (`app/utils/`) — routers are intentionally thin; logic lives here.

  * `admin_pwd.py` – generate/ensure admin password; prints on startup.
  * `session.py` – helpers to read `uid` from cookies, etc.
  * `progress.py` – ensure progress rows exist; assemble `/progress` payload; get level/preset info.
  * `next_problem.py` – one-question generation from a level preset; duplicate-avoidance helpers.
  * `feedback.py` – human-friendly “why no star” messages.
  * `feed_builders.py` – feed query/join with stars; “drills finished today” counts; feed item shaping.
  * `stars.py` – star window math (need-hint text for “3 of last 5” with drop-off awareness).

* **Core logic & level definitions**

  * `app/logic.py` – core drill logic:

    * `generate_from_preset(drill_type, preset)` → `(prompt, answer, tts)`
      (e.g. “6 × 12”, `72`, “six times twelve equals seventy-two”)
    * `compute_first_try_metrics(qlog)` – builds `acc`, `items`, etc.
    * `star_decision(metrics, elapsed_ms, target_time_sec)` – returns `(star_bool, explain_dict)`
    * `levelup_decision(stars_recent_before, star_now)` – rolling “3 of 5” gate.
    * `is_commutative_op_key(prompt)` – used to avoid `4×6` immediately followed by `6×4`.
  * `app/levels.py` – levels & presets:

    * granular multiplication ladder (\~15–20 levels), recap levels interleaved.
    * addition/subtraction/division ladders with sensible ranges.
    * `thresholds_for_level(level)` → `(A, CAP, DELTA, HM, TMAX)`; `TMAX` is the fallback time cap.
    * `get_preset(op, level)`, `level_label(op, level)`, `clamp_level(op, level)`.

* **Data layer**

  * `app/models.py` – SQLModel ORM:

    * `User`, `UserSettings`, `UserProgress`
    * `DrillResult` (one per drill), `DrillQuestion` (every asked Q with timing & correctness)
    * `DrillAward` (e.g. `star`, `pb_time`, `pb_acc`, `level_up`)
    * `AdminConfig` (plain admin password), `DrillTypeEnum`
  * `app/storage.py` – DB engine/session helpers; `init_db()` creates tables.
    DB path from `APP_DB_PATH` env (defaults to `/data/quickfiremath.sqlite`).

* **Templates** (`app/templates/`)

  * `base.html` – shared layout and asset includes.
  * `login.html` – “Who’s playing?” + “Add & start”.
  * `dashboard.html` – drill selection cards, collapsible reports, shared sidebar include.
  * `drill.html` – equation view, overlay for wrong answers, end-of-drill actions.
  * `admin.html` – admin login/logout + delete users.
  * `components/_sidebar.html` – right column: “drills finished today” + newsfeed.

* **Static** (`app/static/`)

  * CSS (`app/static/css/`):

    * `base.css` – theme (CSS vars), layout scaffolding, digit palette `.digit.d0…d9`.
    * `components.css` – sidebar, choose-cards, user grid, badges.
    * `drill.css` – big equation layout, answer bar, overlay.
    * `heatmap.css` – reports heatmap grid (brighter red = needs work).
  * JS (`app/static/js/`):

    * `core.js` – shared helpers (time formatting, audio dings, TTS, API calls, feed/stats renderers, digit colouring).
    * `dashboard.js` – choose-card selection, lazy report loading, 2×2 grid logic.
    * `drill.js` – queueing, duplicate avoidance (commutative keys), wrong-answer re-insert, overlay timing, end-of-drill POST & UI updates.

---

## Endpoints (quick reference)

* **Auth & users**

  * `GET /` – login page.
  * `POST /login` – set `uid` cookie and redirect to `/dashboard`.
  * `POST /user/add` – create user by display name, log them in, redirect to `/dashboard`.

* **Dashboard (selection)**

  * `GET /dashboard` – 2×2 operation cards + reports expander + sidebar.

* **Drills**

  * `POST /start` – form posts `drill_type`; returns `drill.html` with first prompt.
  * `POST /next` – JSON: `{prompt, answer, tts}`; accepts `avoid_prompt` and `avoid_pair` to prevent repeats (`4×6` vs `6×4`).
  * `POST /finish` – saves `DrillResult` + `DrillQuestion[]`, computes star, awards, level-up & next target. Returns JSON:

    * `star`, `level_up`, `new_level`, `new_level_label`, `awards[]`, `fail_msg`, `need_hint`.

* **Feed & stats**

  * `GET /feed` – recent drills (per-user) with star flags and time/score.
  * `GET /stats?tz_offset=MINUTES` – “drills finished today” per op, localised via offset.
  * `GET /progress` – per-op: current `level`, `last5` star string, `need_msg`.

* **Reports**

  * `GET /report/multiplication`
  * `GET /report/addition`
  * `GET /report/subtraction`
    Each returns a small structure: heatmap grid of “needs work” intensity (brighter red = needs more practice), considering only that operation’s recent attempts.

* **Admin**

  * `GET /admin` – prompt for password (printed every boot) or show user list with delete actions.
  * `POST /admin/login`, `POST /admin/logout`
  * `POST /admin/delete_user` – delete by id (with confirm).

---

## Front-end behaviour

* **Digit colour-coding** is applied via `QF.setDigits(el, text)` → wraps digits in spans `.digit.d#`.
  Only the **equation** and **wrong-answer overlay** call this (timer/feed/reports remain neutral).
* **Sounds / TTS** are implemented in `core.js` using WebAudio; TTS uses the browser’s voices and prefers en-NZ if available.
* **Duplicate suppression** on `POST /next`:

  * Avoid **exact same prompt** as last question, and avoid same pair with **commutative operator** (`4×6` then `6×4`) using `commKey`.
  * Wrong answers are **inserted** back into the queue randomly 3–5 ahead.
* **Dashboard cards** (2×2) random-preselect one operation. Clicking a card selects it.

---

## Build, run & deploy

* **Local dev**

  * `pip install -r requirements.txt`
  * `uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload`

* **Docker**

  * `docker build -t quickfire-math .`
  * `docker run -p 8080:8080 -v $(pwd)/data:/data quickfire-math`
  * The app listens on **port 8080** inside the container. Map host port to taste.

* **Persistence**

  * SQLite at `/data/quickfiremath.sqlite` (configure with `APP_DB_PATH`).
    Mount a volume to `/data` to persist.

* **CI / images**

  * If a GH Action exists for GHCR, it builds/pushes on main. Image name usually matches the repo; adjust `docker-compose`/unRAID mapping accordingly.

---

## Data model highlights

* **User** has `UserSettings` (per-op enable & ranges; users can tweak their own) and `UserProgress` per operation:

  * `level`, `stars_recent` (string like `"01010"`), `best_time_ms`, `best_acc`, `target_time_sec`, `last_levelup_at`.
* **DrillResult** records each drill (time, snapshot label, type, question\_count).
* **DrillQuestion** stores each asked Q with timestamps, answer given, correct flag, and per-question `elapsed_ms`.
* **DrillAward** logs stars and personal-best moments (`pb_time`, `pb_acc`), plus `level_up`.
* **AdminConfig** stores the current plain admin password; printed every boot.

---

## Star + level rules (succinct)

* **Star gate**: must meet **accuracy** and **time** for the level.

  * Accuracy threshold scales with `question_count` (e.g. around 19/20 for 20Q drills; concrete values in `logic.py` thresholds).
  * Time gate uses **per-level `target_time_sec`**; on level-up it becomes `min(TMAX, best_previous * 1.5)` (where `TMAX` is the level’s cap).
* **Level-up**: need **≥3 stars in the last 5 drills** for that operation. After level-up, the star history resets and “best” metrics reset for the new level.
* **Hints** surfaced on dashboard cards come from `utils/stars.need_hint_text`, which accounts for **drop-off** (oldest star falling out of the 5-window).

---

## Contributing guidelines

* **Style**: Python 3.12, PEP 8, type hints required for new code. Prefer thin routers and fat utils.
  If adding tools, put shared logic in `app/utils/` and keep router functions short and readable.
* **Naming**: files in `snake_case.py`; classes in `PascalCase`; functions/vars in `snake_case`.
* **Lint/format**: if you add tooling, prefer Black (line length 88) + Ruff.
* **Tests**: use `pytest`; aim to cover utils (`logic`, `levels`, `stars`) and router happy-paths.

---

## Known pitfalls & runbook notes

* **Commutative duplicates**: always pass both `avoid_prompt` and `avoid_pair` to `/next` and check `is_commutative_op_key`. The front-end already does this.
* **Session/DB scoping**: don’t hold on to ORM instances across requests; always re-query if needed. Utilities handle their own sessions.
* **Local time in feed/stats**: `/stats` expects `tz_offset` (minutes from `Date().getTimezoneOffset()`); feed items display ISO timestamps as local via the browser.
* **Number input spinners**: CSS removes them for WebKit/Firefox; the answer input expects typed digits.

---

## Where to put new work

* **New rules / levels** → `app/levels.py` (presets + thresholds) and possibly `logic.py` if adding metrics.
* **New drill types** → add enum value, level presets, generation logic, router acceptance, and front-end card.
* **UI components** → templates under `app/templates/` and styles in `static/css/`.
  Shared right-hand sidebar stays in `components/_sidebar.html`.
* **Reports** → add a route in `reports.py` and a new JS render function; prefer small JSON payloads and client-side rendering.

---

## Security notes

* No login for players; **admin** only protects deletion. Password is stored plain in DB by design (home LAN use) and printed to the logs each boot. Don’t expose logs publicly.
* Cookies are simple (no JWT). This is intentional for a local home/classroom deployment.

---

## Quick checklist before you ship changes

* Can you start a drill, get a wrong answer, see the 3-second overlay, and then see it reappear within the next 3–5?
* On finish: are feed + stats updated on both **drill** and **dashboard** without reload?
* Do duplicate `A×B` then `B×A` pairs get avoided?
* Does a star correctly show in the feed item, and does `/progress` reflect the star ring?
* After level-up: are stars cleared, bests cleared, and a new `target_time_sec` saved?
* Are heatmaps operation-specific (no cross-contamination) and “brighter red = needs work”?

---

If anything here diverges from the repo as you find it, assume **this document is the source of truth** for intended behaviour and structure, and update code accordingly.
