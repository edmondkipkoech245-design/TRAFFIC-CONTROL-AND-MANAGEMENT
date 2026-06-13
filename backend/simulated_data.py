import random
from typing import List, Dict


def generate_traffic(center=(37.7749, -122.4194), count=20) -> List[Dict]:
    """Generate simple simulated traffic points around a center lat/lon.

    Each item: {id, lat, lon, speed_kmh}
    """
    lat0, lon0 = center
    data = []
    for i in range(count):
        lat = lat0 + random.uniform(-0.02, 0.02)
        lon = lon0 + random.uniform(-0.02, 0.02)
        speed = random.uniform(10, 120)  # km/h
        data.append({
            "id": i,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "speed_kmh": round(speed, 1),
        })
    return data
