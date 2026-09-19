# Dream AI Math Tutor

The repository is split by application surface:

- `backend/` — FastAPI, model generation, Manim rendering, narration, evaluation data, and tests.
- `frontend/` — React and Vite lesson interface.
- `docs/` — local design and research material; only `.gitkeep` is tracked.

See [`backend/README.md`](backend/README.md) for API setup, narration behavior, rendering,
and backend verification.

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
