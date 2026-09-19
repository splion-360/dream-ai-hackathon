# Dream AI Math Tutor

The repository is split by application surface:

- `backend/` — FastAPI, model generation, Manim rendering, narration, evaluation data, and tests.
- `frontend/` — React and Vite lesson interface.
- `docs/` — local design and research material; only `.gitkeep` is tracked.

See [`backend/README.md`](backend/README.md) for API setup, narration behavior, rendering,
and backend verification.

## Run the complete local stack

Docker Compose 2.24 or newer is required so the optional secrets file can be omitted. Copy
`backend/.env.example` to `backend/.env`, add the provider credentials you want to use, and
pre-pull the pinned renderer image before the first lesson:

```bash
docker pull manimcommunity/manim@sha256:ab5ad56cf685d89da96e5d459e0cde3743fbdf2141be4dcff6c26566b5ca3191
```

Then start both applications from the repository root. The command relies on `PWD` so the
backend and host Docker daemon see identical artifact paths:

```bash
docker compose up --build
```

Open the frontend at <http://localhost:5173>. FastAPI is available at
<http://localhost:8000>, and generated artifacts remain under `backend/artifacts/`.
Stop the stack with `docker compose down`.

If frontend dependencies change and the existing `node_modules` volume becomes stale, recreate
the development volumes with `docker compose down --volumes`, then start the stack again.

The backend uses the host Docker daemon to create one short-lived, network-isolated Manim
container per valid uncached render. Consequently, local Compose mounts the Docker socket and
the repository at the same absolute path inside the backend container. This is appropriate for
local development and a controlled single-host demo, but not for an untrusted multi-tenant
deployment. The backend runs as root so it can reach the host socket across Docker Desktop and
Linux installations; on native Linux, rendered bind-mount files may therefore be root-owned. A
production deployment should isolate rendering behind a dedicated non-root worker rather than
mounting the control-plane Docker socket into the API container.

Both application Dockerfiles include production build targets. The frontend production target
serves its static build through Nginx and proxies API routes to a service named `backend`; the
backend production target disables source reload. Deployment orchestration and a dedicated
render worker remain part of the deployment ticket rather than the local Compose contract.
Build those targets independently with `docker build --target production backend` and
`docker build --target production frontend`.

## Run the frontend

Start FastAPI on port 8000, then install and run the frontend:

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies `/lessons` to FastAPI. The browser talks only to the lesson API and never
receives Nebius or ElevenLabs credentials. The current submission transport uses the bundled
Pythagorean fixture until arbitrary prompt generation is connected.

Verify the frontend with:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```
