from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from typing import List, Optional
from .simulated_data import generate_traffic
import requests
import logging
import os
import json
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta

app = FastAPI(title="Traffic AI Prototype")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("traffic_ai")

# Auth setup
PWD_CTX = CryptContext(schemes=["bcrypt"], deprecated="auto")
OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="/api/token")
JWT_SECRET = os.environ.get("JWT_SECRET", "devsecret_change_me")
JWT_ALGO = "HS256"
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

def load_users():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump([], f)
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def get_user(username: str):
    users = load_users()
    for u in users:
        if u.get("username") == username:
            return u
    return None

def create_user(username: str, password: str):
    if get_user(username):
        raise HTTPException(status_code=400, detail="User exists")
    pw_hash = PWD_CTX.hash(password)
    users = load_users()
    users.append({"username": username, "password": pw_hash})
    save_users(users)
    return {"username": username}

def verify_password(plain, hashed):
    return PWD_CTX.verify(plain, hashed)

def create_token(data: dict, expires_minutes: int = 60*24):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)

def decode_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(token: str = Depends(OAUTH2_SCHEME)):
    payload = decode_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"username": username}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/traffic")
def traffic(count: int = 30):
    """Return simulated traffic points."""
    points = generate_traffic(count=count)
    return {"items": points}


@app.post('/register')
def register(username: str, password: str):
    """Register a new user (simple)."""
    return create_user(username, password)


@app.post('/token')
def token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user(form_data.username)
    if not user or not verify_password(form_data.password, user.get('password')):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_token({"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get('/me')
def me(user: dict = Depends(get_current_user)):
    return user


def query_osrm_route(start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> Optional[dict]:
    """Query public OSRM demo server for a driving route. Returns dict or None on failure."""
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get("routes"):
            route = data["routes"][0]
            return {
                "distance_m": route.get("distance"),
                "duration_s": route.get("duration"),
                "geometry": route.get("geometry"),
            }
    except Exception as e:
        logger.warning("OSRM route failed: %s", e)
    return None


def query_osrm_routes(start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> Optional[list]:
    """Query OSRM for multiple alternative routes. Returns list of route dicts or None."""
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson&alternatives=true"
        resp = requests.get(url, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        routes = []
        for route in data.get("routes", []):
            routes.append({
                "distance_m": route.get("distance"),
                "duration_s": route.get("duration"),
                "geometry": route.get("geometry"),
            })
        return routes
    except Exception as e:
        logger.warning("OSRM alternatives failed: %s", e)
    return None


def haversine_meters(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c


def point_segment_distance_m(px, py, x1, y1, x2, y2):
    # Convert degrees to meters using local scaling
    # Use equirectangular approximation relative to px
    from math import cos, radians, hypot
    lat_ref = px
    m_per_deg_lat = 111320
    m_per_deg_lon = 111320 * cos(radians(lat_ref))

    # map to meters
    Ax = (x1 - px) * m_per_deg_lon
    Ay = (y1 - py) * m_per_deg_lat
    Bx = (x2 - px) * m_per_deg_lon
    By = (y2 - py) * m_per_deg_lat
    Px = 0.0
    Py = 0.0

    vx = Bx - Ax
    vy = By - Ay
    wx = Px - Ax
    wy = Py - Ay
    c1 = vx*wx + vy*wy
    if c1 <= 0:
        return hypot(Px - Ax, Py - Ay)
    c2 = vx*vx + vy*vy
    if c2 <= c1:
        return hypot(Px - Bx, Py - By)
    t = c1 / c2
    projx = Ax + t*vx
    projy = Ay + t*vy
    return hypot(Px - projx, Py - projy)


def route_slow_score(route_coords, traffic_items, slow_threshold=50, radius_m=50):
    # route_coords: list of [lon, lat]
    score = 0.0
    if not route_coords:
        return float('inf')
    # iterate traffic points with speed below threshold
    for tp in traffic_items:
        sp = tp.get('speed_kmh', 100)
        if sp >= slow_threshold:
            continue
        lat = tp['lat']
        lon = tp['lon']
        # compute min distance to any segment
        min_d = float('inf')
        for i in range(len(route_coords)-1):
            a = route_coords[i]
            b = route_coords[i+1]
            # a,b are [lon, lat]
            d = point_segment_distance_m(lat, lon, b[1], b[0], a[1], a[0])
            if d < min_d:
                min_d = d
            if min_d <= radius_m:
                break
        if min_d <= radius_m:
            score += (slow_threshold - sp)
    return score


@app.get("/speed_limit")
def speed_limit(lat: float, lon: float):
    """Lookup speed limit via Overpass; fallback to default 50 km/h."""
    try:
        # Search for nearby ways with highway tag
        query = f"[out:json];(way(around:50,{lat},{lon})[highway];);out tags 1;"
        url = "https://overpass-api.de/api/interpreter"
        resp = requests.post(url, data={"data": query}, timeout=8)
        resp.raise_for_status()
        js = resp.json()
        elements = js.get("elements", [])
        for el in elements:
            tags = el.get("tags", {})
            maxs = tags.get("maxspeed")
            if maxs:
                try:
                    num = int(''.join(ch for ch in maxs if ch.isdigit()))
                    return {"speed_limit_kmh": num, "source": "overpass"}
                except Exception:
                    continue
    except Exception as e:
        logger.warning("Overpass query failed: %s", e)
    return {"speed_limit_kmh": 50, "source": "default"}


@app.get("/route")
def route(start_lat: float, start_lon: float, end_lat: float, end_lon: float):
    """Return a driving route between two points. Uses OSRM public server as fallback.

    If OSRM is unavailable, returns a simple straight-line 'mock' route.
    """
    res = query_osrm_route(start_lat, start_lon, end_lat, end_lon)
    if res:
        return {"source": "osrm", "route": res}
    # fallback: simple straight-line geometry
    geom = {"type": "LineString", "coordinates": [[start_lon, start_lat], [end_lon, end_lat]]}
    dist = None
    dur = None
    return {"source": "mock", "route": {"distance_m": dist, "duration_s": dur, "geometry": geom}}


@app.get('/route_optimize')
def route_optimize(start_lat: float, start_lon: float, end_lat: float, end_lon: float, avoid_traffic: bool = True):
    """Return the best route among OSRM alternatives minimizing exposure to slow traffic.

    Uses simulated traffic when no real feed is available.
    """
    # fetch candidate routes
    candidates = query_osrm_routes(start_lat, start_lon, end_lat, end_lon)
    if not candidates:
        # fallback to single route
        single = query_osrm_route(start_lat, start_lon, end_lat, end_lon)
        return {"source": "osrm", "route": single, "chosen_index": 0}

    # get traffic snapshot (use simulated generator)
    traffic = generate_traffic(count=60)

    # score candidates
    scored = []
    for idx, c in enumerate(candidates):
        geom = c.get('geometry')
        coords = geom.get('coordinates') if geom else []
        # coords are [lon, lat]
        score = 0.0
        if avoid_traffic:
            score = route_slow_score(coords, traffic, slow_threshold=50, radius_m=50)
        scored.append((score, idx, c))

    scored.sort(key=lambda x: x[0])
    best_score, best_idx, best_route = scored[0]
    return {"source": "osrm_alternatives", "chosen_index": best_idx, "chosen_score": best_score, "routes": [ {"index": s[1], "score": s[0]} for s in scored ], "route": best_route}
