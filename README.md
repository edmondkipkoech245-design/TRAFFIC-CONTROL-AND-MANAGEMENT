Traffic AI — Prototype

Overview
- Simple prototype that simulates traffic, warns about speed limits, and shows live markers on a map.

Run backend (Python 3.10+)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Open the frontend

```bash
# open frontend/index.html in a browser (or serve with a static server)
start frontend/index.html
```

What's included
- `backend/` — FastAPI app that serves simulated traffic data.
- `frontend/` — static Leaflet-based map showing traffic markers.

Next steps
- Add real traffic ingestion (camera / feeds), routing integration, mobile app scaffolding.

Deploy to Vercel (all-in-one)

1. Install the Vercel CLI and log in:

```bash
npm i -g vercel
vercel login
```

2. From the `traffic_ai` project root run:

```bash
vercel
```

Vercel will detect the Python ASGI entry at `api/app.py`, install dependencies from `requirements.txt`, and serve the static frontend from the `frontend/` folder.
