from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import time
import requests

from algorithm_person_c import Place, CrowdAvoidanceScorer


@dataclass
class Suggestion:
    destination: str
    reason: str


class Recommender:
    """
    Reliable hybrid recommender:
    - Uses fixed city centers (no geocoding required)
    - Pulls real POIs via Overpass (OSM)
    - Scores "anti-touristy" using CrowdAvoidanceScorer (lowest crowd_score first)
    - Caches results
    - Falls back to curated suggestions if anything fails
    """

    # Demo-safe city centers (lat, lon). Add more if you like.
    CITY_CENTERS: Dict[str, Tuple[float, float]] = {
        "London": (51.5074, -0.1278),
        "Paris": (48.8566, 2.3522),
        "Barcelona": (41.3851, 2.1734),
        "Amsterdam": (52.3676, 4.9041),
        "Rome": (41.9028, 12.4964),
        "Berlin": (52.5200, 13.4050),
        "Lisbon": (38.7223, -9.1393),
        "Vienna": (48.2082, 16.3738),
        "Prague": (50.0755, 14.4378),
        "Zurich": (47.3769, 8.5417),
        "Valencia": (39.4699, -0.3763),
        "Porto": (41.1579, -8.6291),
    }

    # Curated fallback (demo insurance)
    CURATED: Dict[str, List[Suggestion]] = {
        "London": [
            Suggestion("Little Venice canal walk", "✨ Calm waterside walk (less touristy)"),
            Suggestion("Victoria Park", "📍 Big local park with a relaxed vibe"),
            Suggestion("Columbia Road Flower Market (early)", "🌿 Local scene if you go early"),
        ],
        "Paris": [
            Suggestion("Parc des Buttes-Chaumont", "✨ Local hill-park views (less crowded)"),
            Suggestion("Canal Saint-Martin stroll", "📍 Local hangout area"),
            Suggestion("Marché d’Aligre", "🥐 Food market energy (not a mega-attraction)"),
        ],
        "Barcelona": [
            Suggestion("Poblenou Rambla", "✨ Local neighbourhood energy"),
            Suggestion("Parc del Clot", "📍 Chill park away from the main hotspots"),
            Suggestion("Sant Andreu streets", "☕ Small-town feel inside the city"),
        ],
        "Amsterdam": [
            Suggestion("Oosterpark", "✨ More local than the central canal loop"),
            Suggestion("De Pijp cafés (side streets)", "☕ Great vibe, less tourist flow"),
            Suggestion("Noord waterfront", "📍 Different side of the city"),
        ],
    }

    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    def __init__(self, cache_seconds: int = 600):
        self.cache_seconds = cache_seconds
        self._cache: Dict[str, Tuple[float, List[Suggestion]]] = {}

    def recommend(self, city: str, limit: int = 6) -> List[Suggestion]:
        city_clean = (city or "").strip()
        if not city_clean:
            return self._fallback(city_clean, limit)

        # Cache
        cached = self._cache.get(city_clean)
        if cached:
            ts, data = cached
            if time.time() - ts < self.cache_seconds:
                return data[:limit]

        # Use city center coords; if unknown, fallback
        center = self.CITY_CENTERS.get(city_clean)
        if not center:
            return self._fallback(city_clean, limit)

        lat, lon = center

        # Try Overpass (real data)
        try:
            places = self._fetch_overpass_places(lat, lon, radius_m=2500, per_category=25)
            if not places:
                return self._fallback(city_clean, limit)

            # Always anti-touristy: avoid_crowds=True (lowest score first)
            ranked = CrowdAvoidanceScorer.rank_places(places, avoid_crowds=True)

            suggestions: List[Suggestion] = []
            for p in ranked:
                # Skip if name is missing/garbage
                if not p.name or p.name.strip() in ("", "Unnamed"):
                    continue

                if p.crowd_score < 0.3:
                    vibe = "✨ Hidden gem"
                elif p.crowd_score < 0.6:
                    vibe = "📍 Local vibe"
                else:
                    vibe = "↪️ Still decent (but busier)"

                reason = f"{vibe} • {p.category}"
                suggestions.append(Suggestion(p.name, reason))

                if len(suggestions) >= limit:
                    break

            if not suggestions:
                return self._fallback(city_clean, limit)

            self._cache[city_clean] = (time.time(), suggestions)
            return suggestions

        except Exception:
            return self._fallback(city_clean, limit)

    def _fallback(self, city: str, limit: int) -> List[Suggestion]:
        # City-specific curated if available; otherwise generic
        if city in self.CURATED:
            return self.CURATED[city][:limit]
        generic = [
            Suggestion("Local neighbourhood café", "☕ Anti-touristy pick (fallback)"),
            Suggestion("Less central park", "🌿 Quiet, local vibe (fallback)"),
            Suggestion("Independent food market", "🥐 Local scene (fallback)"),
        ]
        return generic[:limit]

    def _fetch_overpass_places(
        self,
        lat: float,
        lon: float,
        radius_m: int = 2000,
        per_category: int = 20,
    ) -> List[Place]:
        """
        Fetch POIs around (lat, lon) with Overpass.
        Returns Place objects for scoring.
        """
        # We request nodes with a name + categories we care about.
        # Out center not needed for nodes.
        query = f"""
        [out:json][timeout:10];
        (
          node(around:{radius_m},{lat},{lon})["amenity"="cafe"]["name"];
          node(around:{radius_m},{lat},{lon})["amenity"="restaurant"]["name"];
          node(around:{radius_m},{lat},{lon})["leisure"="park"]["name"];
          node(around:{radius_m},{lat},{lon})["tourism"="museum"]["name"];
          node(around:{radius_m},{lat},{lon})["tourism"="attraction"]["name"];
        );
        out {per_category};
        """

        res = requests.post(
            self.OVERPASS_URL,
            data=query.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=12,
        )
        res.raise_for_status()
        data = res.json()

        elements = data.get("elements", [])
        places: List[Place] = []

        for el in elements:
            tags = el.get("tags", {}) or {}
            name = (tags.get("name") or "").strip()
            if not name:
                continue

            el_lat = el.get("lat")
            el_lon = el.get("lon")
            if el_lat is None or el_lon is None:
                continue

            category = self._category_from_tags(tags)

            p = Place(
                name=name,
                lat=float(el_lat),
                lon=float(el_lon),
                category=category,
                osm_type=str(el.get("type") or ""),
                is_tourist_attraction=(tags.get("tourism") == "attraction"),
            )

            # Reuse Person C’s chain heuristic if you want; simplest:
            # If brand present, treat as chain-ish
            brand = (tags.get("brand") or "").strip().lower()
            p.is_chain = bool(brand)

            # Distance will be set by scorer if used elsewhere, but Person C scorer uses distance_from_center.
            # We’ll approximate distance using simple haversine in algorithm_person_c.PlaceFetcher,
            # but to keep dependencies minimal, we compute a rough distance here.
            p.distance_from_center = self._haversine_km(lat, lon, p.lat, p.lon)

            places.append(p)

        return places

    @staticmethod
    def _category_from_tags(tags: Dict[str, str]) -> str:
        if tags.get("amenity") == "cafe":
            return "cafe"
        if tags.get("amenity") == "restaurant":
            return "restaurant"
        if tags.get("leisure") == "park":
            return "park"
        if tags.get("tourism") == "museum":
            return "museum"
        if tags.get("tourism") == "attraction":
            return "attraction"
        return "place"

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        from math import radians, cos, sin, asin, sqrt
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        return 6371 * c
