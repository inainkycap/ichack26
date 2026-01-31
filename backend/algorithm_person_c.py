"""
Person C - Smart Bits Implementation
Hackathon Trip Coordination Project

This module handles:
1. Settlement algorithm (minimal transfers)
2. Crowd-avoidance heuristic for place recommendations
3. Place fetching and scoring from OpenStreetMap
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
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
        """
        Calculate minimal transfers to settle all expenses.
        
        Args:
            expenses: List of expense dicts with structure:
                {
                    'amount': float,
                    'paid_by': str,
                    'split_between': List[str]
                }
        
        Returns:
            List of Transfer objects showing who owes whom
        
        Example:
            >>> expenses = [
            ...     {'amount': 100, 'paid_by': 'Alice', 'split_between': ['Alice', 'Bob', 'Charlie']},
            ...     {'amount': 60, 'paid_by': 'Bob', 'split_between': ['Alice', 'Bob']},
            ... ]
            >>> transfers = SettlementCalculator.calculate_settlements(expenses)
        """
        # Step 1: Calculate net balance for each person
        balances = defaultdict(float)
        
        for expense in expenses:
            amount = expense['amount']
            paid_by = expense['paid_by']
            split_between = expense['split_between']
            
            # Share per person
            share = amount / len(split_between)
            
            # Person who paid gets credited
            balances[paid_by] += amount
            
            # Everyone splits the cost (debited)
            for person in split_between:
                balances[person] -= share
        
        # Step 2: Separate creditors and debtors
        creditors = []  # (person, amount_owed_to_them)
        debtors = []    # (person, amount_they_owe)
        
        for person, balance in balances.items():
            if balance > 0.01:  # Small threshold to handle floating point
                creditors.append([person, balance])
            elif balance < -0.01:
                debtors.append([person, -balance])  # Store as positive
        
        # Sort by amount (largest first)
        creditors.sort(key=lambda x: x[1], reverse=True)
        debtors.sort(key=lambda x: x[1], reverse=True)
        
        # Step 3: Match creditors with debtors (greedy)
        transfers = []
        
        while creditors and debtors:
            creditor, credit_amount = creditors[0]
            debtor, debt_amount = debtors[0]
            
            # Transfer the minimum of what's owed and what's due
            transfer_amount = min(credit_amount, debt_amount)
            
            transfers.append(Transfer(
                from_person=debtor,
                to_person=creditor,
                amount=transfer_amount
            ))
            
            # Update balances
            creditors[0][1] -= transfer_amount
            debtors[0][1] -= transfer_amount
            
            # Remove settled accounts
            if creditors[0][1] < 0.01:
                creditors.pop(0)
            if debtors[0][1] < 0.01:
                debtors.pop(0)
        
        return transfers
    
    @staticmethod
    def format_settlement_summary(transfers: List[Transfer]) -> str:
        """Format transfers into a readable summary"""
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
    """
    
    # Common chain indicators (simple heuristic)
    CHAIN_KEYWORDS = [
        'starbucks', 'mcdonalds', "mcdonald's", 'subway', 'costa', 'pret',
        'wagamama', 'nando', 'pizza express', 'prezzo', 'zizzi', 'pizza hut',
        'kfc', 'burger king', 'five guys', 'chipotle', 'shake shack'
    ]
    
    def __init__(self, cache_seconds: int = 300):
        """
        Initialize the place fetcher.
        
        Args:
            cache_seconds: How long to cache results (to avoid hammering OSM)
        """
        self.cache = {}
        self.cache_timeout = cache_seconds
        self.base_url = "https://nominatim.openstreetmap.org"
        self.headers = {
            'User-Agent': 'TripCoordinator-Hackathon/1.0'
        }
    
    def geocode_destination(self, destination: str) -> Optional[Tuple[float, float]]:
        """
        Convert destination name to coordinates.
        
        Args:
            destination: City/place name (e.g., "Paris, France")
        
        Returns:
            (latitude, longitude) tuple or None if not found
        """
        cache_key = f"geocode:{destination}"
        
        # Check cache
        if cache_key in self.cache:
            cached_time, result = self.cache[cache_key]
            if time.time() - cached_time < self.cache_timeout:
                return result
        
        # Make API call
        try:
            url = f"{self.base_url}/search"
            params = {
                'q': destination,
                'format': 'json',
                'limit': 1
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            if data:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                result = (lat, lon)
                
                # Cache result
                self.cache[cache_key] = (time.time(), result)
                
                # Be nice to OSM - rate limit
                time.sleep(1)
                
                return result
        except Exception as e:
            print(f"⚠️  Geocoding error: {e}")
        
        return None
    
    def fetch_nearby_places(
        self, 
        lat: float, 
        lon: float, 
        radius_km: float = 2.0,
        categories: List[str] = None
    ) -> List[Place]:
        """
        Fetch nearby places around a location.
        
        Args:
            lat: Center latitude
            lon: Center longitude
            radius_km: Search radius in kilometers
            categories: List of categories to search (e.g., ['cafe', 'restaurant'])
        
        Returns:
            List of Place objects
        """
        if categories is None:
            categories = ['cafe', 'restaurant', 'museum', 'park', 'attraction']
        
        cache_key = f"places:{lat:.4f},{lon:.4f}:{radius_km}"
        
        # Check cache
        if cache_key in self.cache:
            cached_time, result = self.cache[cache_key]
            if time.time() - cached_time < self.cache_timeout:
                return result
        
        places = []
        
        # Use Overpass API (more flexible than Nominatim for nearby search)
        # For hackathon simplicity, we'll use a simpler approach with Nominatim
        
        for category in categories:
            try:
                url = f"{self.base_url}/search"
                params = {
                    'format': 'json',
                    'limit': 10,
                    'lat': lat,
                    'lon': lon,
                    'addressdetails': 1
                }
                
                # Add category-specific search
                if category == 'cafe':
                    params['amenity'] = 'cafe'
                elif category == 'restaurant':
                    params['amenity'] = 'restaurant'
                elif category == 'museum':
                    params['tourism'] = 'museum'
                elif category == 'park':
                    params['leisure'] = 'park'
                elif category == 'attraction':
                    params['tourism'] = 'attraction'
                
                response = requests.get(url, params=params, headers=self.headers, timeout=5)
                response.raise_for_status()
                
                data = response.json()
                
                for item in data:
                    place = Place(
                        name=item.get('display_name', '').split(',')[0],
                        lat=float(item['lat']),
                        lon=float(item['lon']),
                        category=category,
                        osm_type=item.get('type', ''),
                        is_tourist_attraction=(item.get('tourism') == 'attraction')
                    )
                    
                    # Check if it's a chain
                    place.is_chain = any(
                        chain in place.name.lower() 
                        for chain in self.CHAIN_KEYWORDS
                    )
                    
                    places.append(place)
                
                # Be nice to OSM
                time.sleep(1)
                
            except Exception as e:
                print(f"⚠️  Error fetching {category}: {e}")
                continue
        
        # Calculate distances from center
        for place in places:
            place.distance_from_center = self._haversine_distance(
                lat, lon, place.lat, place.lon
            )
        
        # Cache result
        self.cache[cache_key] = (time.time(), places)
        
        return places
    
    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points in kilometers using Haversine formula.
        """
        from math import radians, cos, sin, asin, sqrt
        
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        # Earth radius in km
        r = 6371
        
        return c * r


class CrowdAvoidanceScorer:
    """
    Scores places based on crowd-avoidance heuristics.
    Lower score = less crowded (better for avoiding crowds)
    """
    
    @staticmethod
    def score_place(place: Place, normalize_distance: float = 5.0) -> float:
        """
        Calculate crowd score for a place.
        
        Score components:
        - Distance from center (40% weight): farther = less crowded
        - Tourist attraction penalty (30% weight)
        - Chain brand penalty (30% weight)
        
        Args:
            place: Place object to score
            normalize_distance: Max distance for normalization (km)
        
        Returns:
            Score from 0.0 (least crowded) to 1.0 (most crowded)
        """
        # Distance score (normalized, inverted so farther = lower score)
        distance_score = 1.0 - min(place.distance_from_center / normalize_distance, 1.0)
        
        # Tourist attraction penalty
        attraction_penalty = 0.8 if place.is_tourist_attraction else 0.0
        
        # Chain penalty
        chain_penalty = 0.7 if place.is_chain else 0.0
        
        # Weighted combination
        crowd_score = (
            distance_score * 0.4 +
            attraction_penalty * 0.3 +
            chain_penalty * 0.3
        )
        
        place.crowd_score = crowd_score
        return crowd_score
    
    @staticmethod
    def rank_places(
        places: List[Place], 
        avoid_crowds: bool = False
    ) -> List[Place]:
        """
        Rank places based on crowd-avoidance preference.
        
        Args:
            places: List of Place objects
            avoid_crowds: If True, prioritize less crowded places
        
        Returns:
            Sorted list of places
        """
        # Score all places
        for place in places:
            CrowdAvoidanceScorer.score_place(place)
        
        # Sort by crowd score
        if avoid_crowds:
            # Lower score first (less crowded)
            places.sort(key=lambda p: p.crowd_score)
        else:
            # Higher score first (popular/central)
            places.sort(key=lambda p: p.crowd_score, reverse=True)
        
        return places


# ============================================================================
# DEMO & TESTING
# ============================================================================

def demo_settlement():
    """Demo the settlement algorithm"""
    print("=" * 70)
    print("DEMO 1: SETTLEMENT ALGORITHM")
    print("=" * 70)
    print()
    
    # Example scenario: Trip to Paris
    expenses = [
        {
            'amount': 150.00,
            'paid_by': 'Alice',
            'split_between': ['Alice', 'Bob', 'Charlie', 'Diana']
        },
        {
            'amount': 80.00,
            'paid_by': 'Bob',
            'split_between': ['Alice', 'Bob', 'Charlie']
        },
        {
            'amount': 200.00,
            'paid_by': 'Charlie',
            'split_between': ['Alice', 'Bob', 'Charlie', 'Diana']
        },
        {
            'amount': 45.00,
            'paid_by': 'Diana',
            'split_between': ['Bob', 'Diana']
        }
    ]
    
    print("📝 Expenses:")
    for i, exp in enumerate(expenses, 1):
        print(f"  {i}. {exp['paid_by']} paid £{exp['amount']:.2f} for {', '.join(exp['split_between'])}")
    print()
    
    # Calculate settlements
    transfers = SettlementCalculator.calculate_settlements(expenses)
    
    print(SettlementCalculator.format_settlement_summary(transfers))
    print()
    
    # Verify total
    total_paid = sum(e['amount'] for e in expenses)
    total_transferred = sum(t.amount for t in transfers)
    print(f"✓ Total expenses: £{total_paid:.2f}")
    print(f"✓ Total transferred: £{total_transferred:.2f}")
    print()


def demo_crowd_avoidance():
    """Demo the crowd-avoidance system"""
    print("=" * 70)
    print("DEMO 2: CROWD-AVOIDANCE HEURISTIC")
    print("=" * 70)
    print()
    
    # Create mock places (simulating OSM data)
    mock_places = [
        Place(
            name="The Louvre Museum",
            lat=48.8606,
            lon=2.3376,
            category="museum",
            is_tourist_attraction=True,
            is_chain=False,
            distance_from_center=0.5
        ),
        Place(
            name="Starbucks Champs-Élysées",
            lat=48.8698,
            lon=2.3078,
            category="cafe",
            is_tourist_attraction=False,
            is_chain=True,
            distance_from_center=0.3
        ),
        Place(
            name="Café de Flore",
            lat=48.8542,
            lon=2.3320,
            category="cafe",
            is_tourist_attraction=False,
            is_chain=False,
            distance_from_center=1.2
        ),
        Place(
            name="Hidden Garden Cafe",
            lat=48.8789,
            lon=2.3456,
            category="cafe",
            is_tourist_attraction=False,
            is_chain=False,
            distance_from_center=2.5
        ),
        Place(
            name="Eiffel Tower",
            lat=48.8584,
            lon=2.2945,
            category="attraction",
            is_tourist_attraction=True,
            is_chain=False,
            distance_from_center=0.2
        ),
    ]
    
    print("🗺️  Sample places in Paris:")
    print()
    
    # Regular ranking (popular first)
    print("📍 REGULAR RANKING (Popular spots first):")
    regular_ranking = CrowdAvoidanceScorer.rank_places(mock_places.copy(), avoid_crowds=False)
    for i, place in enumerate(regular_ranking, 1):
        print(f"  {i}. {place} (Score: {place.crowd_score:.2f})")
    print()
    
    # Crowd-avoidance ranking
    print("✨ CROWD-AVOIDANCE MODE (Hidden gems first):")
    crowd_avoid_ranking = CrowdAvoidanceScorer.rank_places(mock_places.copy(), avoid_crowds=True)
    for i, place in enumerate(crowd_avoid_ranking, 1):
        print(f"  {i}. {place} (Score: {place.crowd_score:.2f})")
    print()


def demo_real_osm_fetch():
    """Demo fetching real data from OSM (optional - requires internet)"""
    print("=" * 70)
    print("DEMO 3: REAL OSM DATA FETCH (Optional)")
    print("=" * 70)
    print()
    print("⚠️  This requires internet connection and will make real API calls to OSM.")
    print("    Press Enter to continue, or Ctrl+C to skip...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\nSkipped.")
        return
    
    fetcher = PlaceFetcher()
    
    # Geocode a destination
    print("🔍 Geocoding 'Barcelona, Spain'...")
    coords = fetcher.geocode_destination("Barcelona, Spain")
    
    if coords:
        lat, lon = coords
        print(f"✓ Found: {lat:.4f}, {lon:.4f}")
        print()
        
        # Fetch nearby cafes
        print("☕ Fetching nearby cafes...")
        places = fetcher.fetch_nearby_places(lat, lon, radius_km=2.0, categories=['cafe'])
        
        if places:
            print(f"✓ Found {len(places)} cafes")
            print()
            
            # Show with crowd avoidance
            ranked = CrowdAvoidanceScorer.rank_places(places, avoid_crowds=True)
            print("Top 5 less-crowded recommendations:")
            for i, place in enumerate(ranked[:5], 1):
                print(f"  {i}. {place}")
        else:
            print("⚠️  No cafes found")
    else:
        print("⚠️  Geocoding failed")
    
    print()


if __name__ == "__main__":
    # Run demos
    demo_settlement()
    demo_crowd_avoidance()
    
    # Optionally run real OSM fetch
    print("Would you like to test real OSM data fetching? (requires internet)")
    print("This will be useful for testing your integration.")
    print()
    demo_real_osm_fetch()
    
    print("=" * 70)
    print("✅ DEMOS COMPLETE!")
    print("=" * 70)
    print()
    print("Next steps for Person C:")
    print("  1. Integrate SettlementCalculator into Person A's /trip/{id}/settle endpoint")
    print("  2. Integrate PlaceFetcher into Person A's /trip/{id}/itinerary endpoint")
    print("  3. Work with Person B to add 'Less crowded' toggle in frontend")
    print("  4. Cache OSM responses to avoid rate limiting")
    print()
