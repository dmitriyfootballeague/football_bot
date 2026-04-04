# Manual QA Checklist

This checklist is for end-to-end manual verification of the bot against `tech_task.pdf`, with emphasis on registration, transfers, ratings, admin actions, and recent regressions.

## Preconditions

- `.env` is configured with a valid `BOT_TOKEN`.
- `ADMIN_IDS` and `LEAGUE_ADMIN_IDS` contain real Telegram user IDs for test admins.
- Database is up and migrations are applied, including:
  - `005_rename_divisions_to_tournaments`
  - `006_prev_rating_updated_at`
- Bot is running.
- Scraper service is running if rating/scraper checks are part of the session.

## Suggested Local Startup

```bash
docker compose up --build
```

If containers are already built:

```bash
make up
make migrate
```

## Test Accounts

Prepare at least these Telegram accounts:

- `Admin`
- `LeagueAdmin` (optional but useful)
- `Captain A`
- `Player A1`
- `Player A2`
- `Captain B`
- `Player B1`
- `Free Agent 1`
- `Free Agent 2`
- `Rejected User`

## Seed Expectations

Before transfer QA, ensure:

- at least 2 clubs exist in different or same tournaments;
- `Captain A` is approved and assigned to Club A;
- `Captain B` is approved and assigned to Club B;
- `Player A1` and `Player A2` are approved in Club A;
- `Player B1` is approved in Club B;
- `Free Agent 1` and `Free Agent 2` are approved with role `free_agent`.

## 1. Registration

### 1.1 New user sees correct start screen

Steps:
- Open bot from a fresh Telegram account.
- Send `/start`.

Expected:
- Welcome text is shown.
- Inline buttons `Регистрация` and `Инструкция` are shown.

### 1.2 Registration happy path: free agent

Steps:
- Click `Регистрация`.
- Fill valid first name, last name, position, description or skip, birth date, photo.
- Choose `Свободный агент`.

Expected:
- Registration is submitted.
- User sees pending message.
- Admin receives registration card with approve/reject buttons.

### 1.3 Registration happy path: club player

Steps:
- Register another user.
- Choose club path, then tournament, club, role `Игрок`.

Expected:
- Admin receives registration card showing chosen club and role.

### 1.4 Registration happy path: captain

Steps:
- Register another user.
- Choose club path, then role `Капитан`.

Expected:
- Admin receives registration card showing captain role.

### 1.5 Validation

Steps:
- Enter invalid first name.
- Enter invalid surname.
- Enter invalid birth date.
- Send non-photo content at photo step.

Expected:
- Bot rejects each invalid input with the relevant validation message.

### 1.6 Approve registration

Steps:
- Admin clicks approve on a pending registration.

Expected:
- User receives approval notification.
- User gets role-specific reply keyboard:
  - player: `Рейтинг`, `Трансфер`
  - captain: `Рейтинг`, `Трансфер`
  - free agent: `Рейтинг за прошлый сезон`, `Трансфер`

### 1.7 Reject registration and reapply regression

Steps:
- Reject a pending registration as admin.
- User sends `/start`.
- User clicks `Подать заявку`.
- Complete registration again.

Expected:
- `/start` shows `Подать заявку` and `Инструкция`, not `Регистрация`.
- User can submit a new application successfully.
- No duplicate-key crash on existing `telegram_id`.

### 1.8 Pending user cannot submit again

Steps:
- Submit registration.
- Before admin decision, send `/start`.
- Try to click `Регистрация` or `Подать заявку` from old message if still visible.

Expected:
- User is blocked with pending alert.

## 2. Instructions

### 2.1 Unregistered user sees all instructions

Steps:
- Fresh user clicks `Инструкция`.

Expected:
- Captain, player, and free-agent instruction blocks are sent.

### 2.2 Approved user sees only role-specific instruction

Steps:
- Approved captain clicks `Инструкция`.
- Approved player clicks `Инструкция`.
- Approved free agent clicks `Инструкция`.

Expected:
- Each user sees only their own instruction block.

## 3. Ratings

### 3.1 Current rating for club player/captain

Steps:
- From approved player or captain account, press `Рейтинг`.

Expected:
- Current rating message includes:
  - name
  - position
  - age
  - club
  - tournament
  - description
  - current rating
  - division rank and total
  - position rank and total
  - average points
  - last update date

### 3.2 Previous-season rating for free agent

Steps:
- From approved free-agent account, press `Рейтинг за прошлый сезон`.

Expected:
- Message includes previous-season rating fields and last update date.

### 3.3 Admin panel rating edits

Steps:
- Admin sends `/panel`.
- Change current rating for a player.
- Change previous-season rating for a free agent or player.

Expected:
- Bot confirms the update.
- Corresponding rating screen reflects the new value and date.

## 4. Transfer: Player Exit Club

### 4.1 Happy path

Steps:
- `Player A1` presses `Трансфер` -> `Стать свободным агентом`.
- `Captain A` approves.
- Admin approves.

Expected:
- Player sees submission message.
- Captain receives exit request.
- Player receives captain approval message.
- Admin receives approval request.
- After admin approval, player becomes free agent and gets free-agent menu.
- Captain receives admin decision notification.

### 4.2 Captain rejects exit

Steps:
- `Player A1` submits exit request.
- `Captain A` rejects.

Expected:
- Player receives rejection message.
- Request becomes terminal.

### 4.3 Admin rejects exit

Steps:
- Repeat happy path until admin stage.
- Admin rejects.

Expected:
- Player receives admin rejection message.
- Captain receives admin rejection notification.
- Player remains in original club.

## 5. Transfer: Player Join Another Club

### 5.1 Happy path

Steps:
- `Player A1` presses `Трансфер` -> `Выбор дивизиона и клуба`.
- Select tournament and Club B.
- `Captain B` approves.
- `Player A1` confirms.
- Admin approves.

Expected:
- `Captain B` receives join request with player profile.
- `Player A1` receives captain approval and confirm button.
- Admin receives final request.
- After admin approval, player joins Club B and has player menu.
- `Captain B` receives admin decision notification.

### 5.2 Captain rejects join request

Steps:
- `Player A1` submits join request to Club B.
- `Captain B` rejects.

Expected:
- Player receives rejection message.
- No admin request is created.

### 5.3 Admin rejects join request

Steps:
- Submit join request and confirm it through player stage.
- Admin rejects.

Expected:
- Player receives admin rejection.
- `Captain B` receives admin rejection notification.
- Player remains in original club.

### 5.4 Same-club protection

Steps:
- `Player A1` tries to select Club A, the club they already belong to.

Expected:
- Bot blocks the action with an alert.
- No transfer request is created.

## 6. Transfer: Free Agent Self-Join

### 6.1 Happy path

Steps:
- `Free Agent 1` presses `Трансфер` -> `Самостоятельный выбор клуба`.
- Select Club A.
- `Captain A` approves.
- `Free Agent 1` confirms.
- Admin approves.

Expected:
- Flow behaves like player join.
- Final role becomes player in Club A.

## 7. Transfer: Captain Invites Free Agent

### 7.1 Happy path

Steps:
- `Captain A` opens `Трансфер` -> `Свободные агенты`.
- Invite `Free Agent 1`.
- `Free Agent 1` accepts.
- `Captain A` confirms.
- Admin approves.

Expected:
- Free agent receives invite.
- Captain receives accepted-invite notification.
- Admin receives final request.
- Free agent joins Club A as player.
- Captain receives admin decision notification.

### 7.2 Free agent rejects invite

Steps:
- `Captain A` invites `Free Agent 1`.
- `Free Agent 1` rejects.

Expected:
- Captain receives rejection notification.
- Request becomes terminal.

### 7.3 Admin rejects accepted invite

Steps:
- Run invite flow through captain confirmation.
- Admin rejects.

Expected:
- Player receives admin rejection.
- Captain receives admin rejection notification.

## 8. Transfer: Captain Kick Player

### 8.1 Happy path

Steps:
- `Captain A` opens `Трансфер` -> `Удалить игрока из команды`.
- Select `Player A2`.
- Admin approves.

Expected:
- Admin receives kick request.
- Player is removed from Club A and becomes free agent after admin approval.
- Player receives kick notification.
- Captain receives admin decision notification.

### 8.2 Admin rejects kick

Steps:
- Start kick flow.
- Admin rejects.

Expected:
- Player stays in Club A.
- Player receives rejection notification.
- Captain receives rejection notification.

### 8.3 Cross-club protection

Steps:
- Attempt to kick a player not in captain’s club by reusing callback or stale button.

Expected:
- Action is blocked.

## 9. Transfer Authorization and Concurrency

### 9.1 Wrong user cannot act on чужой request

Steps:
- Create a pending join request for Club B.
- Have `Captain A` try to approve/reject it.
- Have unrelated player try to press confirm button.
- Have unrelated free agent try to accept/reject another user’s invite.

Expected:
- All such actions are blocked.

### 9.2 Only one active transfer per player

Steps:
- Create an active transfer request for a player.
- Before resolving it, try to start another transfer.

Expected:
- Bot shows active-request alert.

### 9.3 Terminal request cannot continue

Steps:
- Reject a request.
- Try to interact with old buttons if still present.

Expected:
- No further state transition should happen.

## 10. Admin Panel

### 10.1 Access control

Steps:
- Non-admin sends `/panel`.
- Admin sends `/panel`.

Expected:
- Non-admin cannot use the panel.
- Admin sees the panel.

### 10.2 Edit club name

Steps:
- Admin edits a club name.

Expected:
- Update succeeds.
- New club name appears in subsequent flows and notifications.

### 10.3 Edit current and previous ratings

Steps:
- Admin changes current rating.
- Admin changes previous-season rating.

Expected:
- Both updates succeed.
- Date fields update accordingly.

## 11. Scraper

### 11.1 Current-season sync

Steps:
- Run scraper.
- Inspect player data in DB or via bot rating output.

Expected:
- Current rating, division rank, position rank, avg points, and update date are populated for matched players.

### 11.2 Previous-season sync

Steps:
- Run scraper.
- Inspect previous-season fields for matched players.

Expected:
- Previous-season rating, division rank, position rank, avg points, and previous update date are populated.

Note:
- This part depends on live `olesports.ru` DOM behavior and should be validated carefully after deployment.

## 12. Smoke Pass Table

Mark each item `PASS` or `FAIL` during a release check:

- New registration as free agent
- New registration as club player
- Registration rejection and reapply
- Captain instruction only for captain
- Player current rating opens
- Free-agent previous-season rating opens
- Player exit flow approved
- Player join flow approved
- Free-agent self-join approved
- Captain invite flow approved
- Captain kick flow approved
- Admin panel club edit
- Admin panel current rating edit
- Admin panel previous-season rating edit
- Scraper current-season sync
- Scraper previous-season sync

## 13. Known High-Risk Areas

- Transfer callbacks with stale inline buttons after the request is already resolved.
- Previous-season scraping selectors on live `olesports.ru`.
- Matching scraped players to registered players by `external_id` and fallback name match.
