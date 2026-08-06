# WhoYaGot

Two players, one call. Pick a side, over and over, and a ranked list builds
itself — yours, and everyone's.

Starts with the NFL and is built to take on MLB, NHL, NBA, soccer and golf by
adding a source adapter, not a schema migration.

```
frontend/          React + TypeScript + Vite + Tailwind, wrapped for Android by Capacitor
  android/         Generated Capacitor project
backend/           FastAPI + SQLAlchemy + Postgres
  app/api/         Routers: leagues, matchups, rankings, players, auth, admin
  app/services/    Elo, matchmaking, Google auth, league sources, sync
```

Player data comes from the existing [NFL-API](https://nfl-api.nickknows.net)
service. WhoYaGot owns the votes, the ratings, and the users.

## How it works

**Matchmaking** pairs players at the same position with similar current
ratings, because closely-matched pairs move ratings fastest. Half the time the
first player is drawn from the least-voted end of the pool instead, so coverage
stays even rather than a few stars soaking up every matchup. Pairs the voter has
already judged are avoided until they've seen most of the position.

**Elo** runs on two independent ladders. The global one aggregates every user's
votes; a per-user one produces "your list". K falls from 40 to 12 as a player
accumulates votes, so early results move fast and settled ratings stay put.

Against a simulated ranking with a 10% upset rate, 4,000 votes across 64
quarterbacks recovered the true order at Spearman 0.986, with vote counts
between 119 and 134 per player.

**Anonymous first.** Votes work with no account, keyed to a device-local session
ID. Signing in with Google claims those votes onto the account — the personal
ladder is replayed in chronological order, since Elo is path dependent, while
the global ladder is left alone because it already counted them.

## Running it

Local dev needs the backend and the frontend, in two terminals.

```bash
# Backend — SQLite by default, no Postgres needed
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd app && ../.venv/bin/python scripts/sync_players.py --league nfl   # 400-900 players
../.venv/bin/uvicorn main:app --reload --port 8000
```

```bash
# Frontend
cd frontend
npm install
npm run dev            # http://localhost:5173, proxies /api to :8000
```

Everything works without any Google setup — you vote anonymously, and only
"My list" asks you to sign in.

With Docker instead — this brings up Postgres, the API, and nginx serving the
built site on <http://localhost:8080>:

```bash
docker compose up --build
docker compose exec api python scripts/sync_players.py --league nfl
```

## Containers

Two images, both built and published by CI:

| Image | |
|---|---|
| `ncging/whoyagot-api` | FastAPI — votes, ratings, users |
| `ncging/whoyagot-web` | nginx serving the SPA, proxying `/api` to the API |

The web image holds nothing environment-specific. On start-up it reads three
variables and writes them into `config.js`, which the app reads at load — so one
tag runs in every environment and a new API hostname does not mean a rebuild.

| Variable | Default | |
|---|---|---|
| `API_UPSTREAM` | `http://whoyagot-api:8000` | Where nginx forwards `/api` |
| `PUBLIC_API_URL` | `/api` | What the browser calls; same-origin by default, so CORS never applies to the web build |
| `GOOGLE_CLIENT_ID` | empty | Enables the sign-in button |

## CI

| Workflow | |
|---|---|
| `ci.yaml` | Backend pytest, frontend type-check and build. No secrets, so it runs on forks |
| `containers.yaml` | Builds both images on `main`, starts them and checks the site serves, then pushes and writes the new tags into the Helm chart |
| `android.yaml` | Debug APK on every run; a signed AAB and APK on `v*` tags |

Secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`. Variables: `PUBLIC_API_URL`
(absolute API URL, required for Android release builds), `GOOGLE_CLIENT_ID`.

## Deploying

`helm/whoyagot` is one chart covering the whole app, so it is one ArgoCD
Application. It renders the API and web Deployments and Services, an Ingress, a
CloudNativePG cluster, the External Secrets wiring, and a nightly player-sync
CronJob per league.

```bash
helm template whoyagot helm/whoyagot -n whoyagot   # inspect
helm upgrade --install whoyagot helm/whoyagot -n whoyagot --create-namespace
```

**One hostname.** The web pod serves the site and proxies `/api` to the API
service, so nothing needs a second host or certificate — and the API is public
at `https://<fqdn>/api`, which is what the Android build should point at.

Sync waves order the rollout: secrets first (`-1`), the database (`0`), then the
workloads (`1`) and the sync CronJob (`2`).

Set in OpenBao under the `whoyagot` path before the first sync:

| Property | |
|---|---|
| `jwt_secret` | Signs session tokens — `openssl rand -hex 32` |
| `admin_token` | Guards `POST /admin/sync` |
| `dbuser`, `dbpassw` | Application database user |
| `dbsu`, `dbsupassw` | Database superuser |

`googleClientId` lives in `values.yaml`, not OpenBao — it ships to every browser,
so it is not a secret. Leaving it empty disables the sign-in button; anonymous
voting still works. Any additional OAuth client the API should accept tokens
from — an Android build with its own — goes in `extraGoogleClientIds`, which the
API receives and the browser does not.

Once images are published, CI writes each new tag into `helm/whoyagot/values.yaml`
and commits it, so ArgoCD picks up the deploy on its own. That commit touches
only `helm/`, which is outside the workflow's path filter, so it cannot trigger
another build.

Signed Android releases additionally need `ANDROID_KEYSTORE_BASE64`,
`ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD`. The
release job fails with a clear message listing whichever are missing rather than
producing something unsignable. Without them, debug APKs still build.

### Keeping the player pool current

`sync_players.py` is idempotent and worth running nightly in-season. Players who
fall off a roster are deactivated rather than deleted, so old votes still
resolve and a returning player keeps their rating.

**Which season it pulls.** The sync works the season out from the date — the
league year turns over in March — rather than letting upstream decide. Asked
without a season, NFL-API answers with the last *completed* one, which through
an entire offseason means every team label is a year stale. `NFL_SEASON`
(`api.nflSeason` in the chart) pins it when you want a specific one.

Expect the pool to roughly double from March to the end of August: those are
90-man camp rosters, and the nightly sync deactivates the cuts on its own once
teams get down to 53.

An empty answer from a source aborts the sync rather than deactivating
everyone — a season past the end of the data returns `200` with no rows, and
taken at face value that would empty the pool.

There is also `POST /admin/sync?league=nfl`, guarded by an `X-Admin-Token`
header, for driving the same thing from a Kubernetes CronJob.

## Google sign-in

1. In Google Cloud Console, create an **OAuth 2.0 Web client**. Add your web
   origin to *Authorized JavaScript origins* (`http://localhost:5173` for dev).
2. Backend: `GOOGLE_CLIENT_IDS=<web-client-id>`, plus a real `JWT_SECRET`
   (`openssl rand -hex 32`).
3. Frontend: `VITE_GOOGLE_CLIENT_ID=<web-client-id>`.

The client runs the Google flow and posts the resulting ID token; the backend
verifies it against Google's keys, checks `aud` against `GOOGLE_CLIENT_IDS`, and
issues its own JWT. Every later request is one local signature check.

`GOOGLE_CLIENT_IDS` is a list because an Android build using its own OAuth
client gets that client stamped into the token's `aud` — add the Android client
ID there too. In Kubernetes that list is assembled from `googleClientId` plus
`extraGoogleClientIds`; the two are kept apart because the web pod's
`GOOGLE_CLIENT_ID` must stay a single value, and a comma-joined one would reach
the browser as a malformed `client_id`.

## Android

CI builds a debug APK on every run — grab it from the workflow artifacts. To
build locally:

```bash
cd frontend
echo "VITE_API_URL=https://your-api-host" >> .env   # required: no dev proxy in a webview
export VITE_GOOGLE_CLIENT_ID=your-web-client-id.apps.googleusercontent.com
npm run android:sync
npm run android:open        # needs Android Studio
```

`VITE_GOOGLE_CLIENT_ID` has to be exported, not just written to `.env`: Vite
reads `.env` for the web build, but `capacitor.config.ts` is a separate Node
process that only sees the real environment.

Unlike the web image, the Android build compiles its API URL in, because there
is no server in front of a webview to inject one.

The webview origin is `https://localhost`, which must be in the API's
`CORS_ORIGINS` (it is by default).

### Sign-in on Android

Google blocks its web sign-in flow inside a webview, so Android goes through
Play Services natively — `@codetrix-studio/capacitor-google-auth`, picked
because it is the only maintained build that peers to Capacitor 6. `auth.tsx`
branches on `Capacitor.isNativePlatform()`; both paths end at the same
`POST /auth/google` with an ID token, and the backend cannot tell them apart.

**Android signs in against the *web* client, not its own.** `requestIdToken`
takes a server client ID, and Google puts that in the token's `aud` — the
Android OAuth client goes in `azp`. So `GOOGLE_CLIENT_IDS` needs only the web
ID, and `extraGoogleClientIds` stays empty. An Android OAuth client must still
exist in the same project, or Play Services refuses the request with a bare
`DEVELOPER_ERROR`:

| Field | |
|---|---|
| Type | Android |
| Package name | `net.nickknows.whoyagot` |
| SHA-1 | the fingerprint of every keystore you sign with |

That last row is the one that bites. Each signing key needs its own registered
fingerprint, and CI generates a throwaway debug keystore on each run — so
**native sign-in never works in a CI debug APK**, only in a signed release
build. `keytool -list -v -keystore <ks>` prints the fingerprint.

The client ID reaches the app through `capacitor.config.ts`, which reads
`VITE_GOOGLE_CLIENT_ID` at build time and `cap sync` bakes into
`capacitor.config.json`. Unset, the plugin block is omitted entirely and the
sign-in button hides itself rather than failing on tap.

## API

| Method | Path | |
|---|---|---|
| `GET` | `/leagues` | Leagues, positions, pool sizes |
| `GET` | `/matchups/next?league=nfl&position=QB` | Deal a pair (omit position to rotate) |
| `POST` | `/matchups/vote` | Record a pick; returns rating deltas and the next pair |
| `POST` | `/matchups/skip` | Pass, get another |
| `GET` | `/rankings?league=nfl&position=QB` | Everyone's board |
| `GET` | `/rankings/me` | Your board (auth required) |
| `GET` | `/rankings/head-to-head?player_a=&player_b=` | One pairing's split |
| `GET` | `/players`, `/players/{id}` | Browse and look up |
| `POST` | `/auth/google` | Exchange a Google ID token for a session |
| `POST` | `/admin/sync?league=nfl` | Refresh the pool (`X-Admin-Token`) |

Interactive docs at `/docs`.

## Adding a league

Implement `PlayerSource` in `backend/app/services/sources/`, returning
`SourceTeam` and `SourcePlayer` records, and register it:

```python
class MLBSource(PlayerSource):
    league = "mlb"
    display_name = "MLB"
    positions = ["SP", "RP", "C", "1B", "2B", "3B", "SS", "OF"]

    def fetch_teams(self) -> list[SourceTeam]: ...
    def fetch_players(self, season=None) -> list[SourcePlayer]: ...

register(MLBSource())
```

Import it in `sources/__init__.py`, run the sync, and the league tab appears.
Nothing in the schema, the matchmaking, the Elo, or the frontend needs to know
which sport it is looking at.
