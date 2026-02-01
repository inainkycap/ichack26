"""
Person C - Smart Bits Implementation
Hackathon Trip Coordination Project

This module handles:
1. Settlement algorithm (minimal transfers)
2. Crowd-avoidance heuristic for place recommendations
3. Place fetching and scoring from OpenStreetMap

✅ Uses:
- Nominatim (geocode city -> lat/lon)
- Overpass API (fetch nearby POIs around lat/lon)
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import requests
import time
from collections import defaultdict


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Transfer:
    """Represents a money transfer from one person to another"""
    from_person: str
    to_person: str
    amount: float

    def __str__(self):
        return f"{self.from_person} → {self.to_person}: £{self.amount:.2f}"


@dataclass
class Place:
    """Represents a place/location recommendation"""
    name: str
    lat: float
    lon: float
    category: str
    osm_type: str = ""
    is_chain: bool = False
    is_tourist_attraction: bool = False
    distance_from_center: float = 0.0
    crowd_score: float = 0.0  # Lower = less crowded

    def __str__(self):
        crowded = "🔥 Popular" if self.crowd_score > 0.7 else "✨ Hidden gem" if self.crowd_score < 0.3 else "📍 Moderate"
        return f"{self.name} ({self.category}) - {crowded}"


# ============================================================================
# SETTLEMENT ALGORITHM
# ============================================================================

class SettlementCalculator:
    """
    Calculates minimal transfers to settle debts in a group.

    Uses a greedy algorithm:
    1. Calculate net balance for each person (what they paid - what they owe)
    2. Match largest creditor with largest debtor
    3. Repeat until all debts settled
    """

    @staticmethod
    def calculate_settlements(expenses: List[Dict]) -> List[Transfer]:
        balances = defaultdict(float)

        for expense in expenses:
            amount = expense["amount"]
            paid_by = expense["paid_by"]
            split_between = expense["split_between"]

            share = amount / len(split_between)

            balances[paid_by] += amount
            for person in split_between:
                balances[person] -= share

        creditors = []
        debtors = []

        for person, balance in balances.items():
            if balance > 0.01:
                creditors.append([person, balance])
            elif balance < -0.01:
                debtors.append([person, -balance])

        creditors.sort(key=lambda x: x[1], reverse=True)
        debtors.sort(key=lambda x: x[1], reverse=True)

        transfers = []
        while creditors and debtors:
            creditor, credit_amount = creditors[0]
            debtor, debt_amount = debtors[0]

            transfer_amount = min(credit_amount, debt_amount)

            transfers.append(Transfer(
                from_person=debtor,
                to_person=creditor,
                amount=transfer_amount
            ))

            creditors[0][1] -= transfer_amount
            debtors[0][1] -= transfer_amount

            if creditors[0][1] < 0.01:
                creditors.pop(0)
            if debtors[0][1] < 0.01:
                debtors.pop(0)

        return transfers

    @staticmethod
    def format_settlement_summary(transfers: List[Transfer]) -> str:
        if not transfers:
            return "✅ All settled! No transfers needed."

        summary = ["💰 Settlement Summary:", ""]
        for transfer in transfers:
            summary.append(f"  {transfer}")

        return "\n".join(summary)


# ============================================================================
# CROWD-AVOIDANCE & PLACE RECOMMENDATION
# ============================================================================

class PlaceFetcher:
    """
    Fetches places from OpenStreetMap and scores them for crowd-avoidance.

    ✅ Nominatim: geocode city -> (lat, lon)
    ✅ Overpass: fetch POIs near (lat, lon)
    """

    CHAIN_KEYWORDS = [
        "starbucks", "mcdonalds", "mcdonald's", "subway", "costa", "pret",
        "wagamama", "nando", "pizza express", "prezzo", "zizzi", "pizza hut",
        "kfc", "burger king", "five guys", "chipotle", "shake shack"
    ]

    # Map our app categories to OSM tags
    CATEGORY_TAGS = {
        "cafe": ("amenity", "cafe"),
        "restaurant": ("amenity", "restaurant"),
        "museum": ("tourism", "museum"),
        "park": ("leisure", "park"),
        "attraction": ("tourism", "attraction"),
    }

    def __init__(self, cache_seconds: int = 300):
        self.cache = {}
        self.cache_timeout = cache_seconds

        self.nominatim_url = "https://nominatim.openstreetmap.org"
        self.overpass_url = "https://overpass-api.de/api/interpreter"

        # IMPORTANT: Use a descriptive UA; ideally include contact email in real deployments.
        self.headers = {
            "User-Agent": "collie-herding-next-destination/1.0 (hackathon demo)"
        }

    def geocode_destination(self, destination: str) -> Optional[Tuple[float, float]]:
        cache_key = f"geocode:{destination}"

        if cache_key in self.cache:
            cached_time, result = self.cache[cache_key]
            if time.time() - cached_time < self.cache_timeout:
                return result

        try:
            url = f"{self.nominatim_url}/search"
            params = {"q": destination, "format": "json", "limit": 1}

            response = requests.get(url, params=params, headers=self.headers, timeout=8)
            response.raise_for_status()

            data = response.json()
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                result = (lat, lon)

                self.cache[cache_key] = (time.time(), result)
                time.sleep(1)  # be polite
                return result
        except Exception as e:
            print(f"⚠️  Geocoding error: {e}")

        return None

    def fetch_nearby_places(
        self,
        lat: float,
        lon: float,
        radius_km: float = 2.0,
        categories: List[str] = None,
        limit_per_category: int = 20,
    ) -> List[Place]:
        """
        Real nearby POI fetch using Overpass around().

        Overpass QL "around" radius query. :contentReference[oaicite:2]{index=2}
        """
        if categories is None:
            categories = ["cafe", "restaurant", "museum", "park", "attraction"]

        radius_m = int(radius_km * 1000)
        cache_key = f"overpass:{lat:.4f},{lon:.4f}:{radius_m}:{','.join(categories)}:{limit_per_category}"

        if cache_key in self.cache:
            cached_time, result = self.cache[cache_key]
            if time.time() - cached_time < self.cache_timeout:
                return result

        # Build one combined Overpass query for all categories
        parts = []
        for cat in categories:
            tag = self.CATEGORY_TAGS.get(cat)
            if not tag:
                continue
            k, v = tag
            # nodes/ways/relations within radius
            parts.append(f'node(around:{radius_m},{lat},{lon})["{k}"="{v}"];')
            parts.append(f'way(around:{radius_m},{lat},{lon})["{k}"="{v}"];')
            parts.append(f'relation(around:{radius_m},{lat},{lon})["{k}"="{v}"];')

        if not parts:
            return []

        query = f"""
        [out:json][timeout:25];
        (
          {' '.join(parts)}
        );
        out center {limit_per_category};
        """

        places: List[Place] = []
        try:
            r = requests.post(self.overpass_url, data=query.encode("utf-8"), headers=self.headers, timeout=25)
            r.raise_for_status()
            data = r.json()

            # Overpass returns a mix of nodes/ways/relations
            for el in data.get("elements", []):
                tags = el.get("tags", {}) or {}
                name = (tags.get("name") or tags.get("brand") or "").strip()
                if not name:
                    continue

                # Coordinates:
                if el.get("type") == "node":
                    plat = el.get("lat")
                    plon = el.get("lon")
                else:
                    center = el.get("center") or {}
                    plat = center.get("lat")
                    plon = center.get("lon")

                if plat is None or plon is None:
                    continue

                # Determine category from tags (reverse map)
                category = "other"
                for cat, (k, v) in self.CATEGORY_TAGS.items():
                    if tags.get(k) == v:
                        category = cat
                        break

                place = Place(
                    name=name,
                    lat=float(plat),
                    lon=float(plon),
                    category=category,
                    osm_type=str(el.get("type", "")),
                    is_tourist_attraction=(tags.get("tourism") in {"attraction", "museum"} or tags.get("historic") is not None),
                )

                # Chain heuristic
                lower_name = place.name.lower()
                brand = (tags.get("brand") or "").lower()
                place.is_chain = any(k in lower_name for k in self.CHAIN_KEYWORDS) or any(k in brand for k in self.CHAIN_KEYWORDS)

                places.append(place)

            # Dedupe by (name, rounded coords)
            seen = set()
            deduped = []
            for p in places:
                key = (p.name.lower(), round(p.lat, 5), round(p.lon, 5))
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(p)

            places = deduped

            # Distance from center
            for p in places:
                p.distance_from_center = self._haversine_distance(lat, lon, p.lat, p.lon)

            # Cache
            self.cache[cache_key] = (time.time(), places)

            # be polite to public Overpass
            time.sleep(1)

            return places

        except Exception as e:
            print(f"⚠️  Overpass fetch failed: {e}")
            return []

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        from math import radians, cos, sin, asin, sqrt
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        r = 6371
        return c * r


class CrowdAvoidanceScorer:
    """
    Scores places based on crowd-avoidance heuristics.
    Lower score = less crowded (better)
    """

    @staticmethod
    def score_place(place: Place, normalize_distance: float = 5.0) -> float:
        distance_score = 1.0 - min(place.distance_from_center / normalize_distance, 1.0)
        attraction_penalty = 0.8 if place.is_tourist_attraction else 0.0
        chain_penalty = 0.7 if place.is_chain else 0.0

        crowd_score = (
            distance_score * 0.4 +
            attraction_penalty * 0.3 +
            chain_penalty * 0.3
        )

        place.crowd_score = crowd_score
        return crowd_score

    @staticmethod
    def rank_places(places: List[Place], avoid_crowds: bool = True) -> List[Place]:
        for place in places:
            CrowdAvoidanceScorer.score_place(place)

        # Default for Collie: anti-touristy
        if avoid_crowds:
            places.sort(key=lambda p: p.crowd_score)  # lower first
        else:
            places.sort(key=lambda p: p.crowd_score, reverse=True)

        return places
