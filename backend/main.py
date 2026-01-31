from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Literal, List
from collections import defaultdict
import sys
import os

# Add backend directory to Python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Import Person C's algorithms
try:
    from algorithm_person_c import (
        SettlementCalculator,
        PlaceFetcher,
        CrowdAvoidanceScorer
    )
    ALGORITHMS_AVAILABLE = True
    print("✅ Person C's algorithms loaded successfully!")
except ImportError as e:
    print(f"⚠️  Warning: algorithm_person_c.py not found. Using fallback recommendations.")
    print(f"    Error: {e}")
    print(f"    Current directory: {os.getcwd()}")
    print(f"    Backend directory: {backend_dir}")
    ALGORITHMS_AVAILABLE = False

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory storage, mirrors mockStore ---
trips: Dict[str, dict] = {}

# Initialize PlaceFetcher (Person C's algorithm)
if ALGORITHMS_AVAILABLE:
    place_fetcher = PlaceFetcher()
    print("✅ PlaceFetcher initialized!")

# --- Models ---
class TripCreate(BaseModel):
    title: Optional[str] = "Weekend Trip"

class JoinTrip(BaseModel):
    name: Optional[str] = "Anonymous"

class Vote(BaseModel):
    type: Literal["destination", "dates"]
    option: str
    member_id: str

class ExpenseCreate(BaseModel):
    amount: float
    paid_by: str
    split_between: List[str]
    description: Optional[str] = None

# --- Helpers ---
def ensure_trip(trip_id: str) -> dict:
    if trip_id not in trips:
        trips[trip_id] = {
            "title": "Weekend Trip",
            "members": {},
            "votes": {"destination": {}, "dates": {}},
            "memberVotes": {},  # track individual member votes
            "expenses": [],  # track expenses for settlement
            "options": {
                "destination": ["Lisbon", "Porto", "Barcelona", "Valencia", "Amsterdam"],
                "dates": ["Feb 7–9", "Feb 14–16", "Mar 1–3", "Mar 8–10"],
            },
        }
    return trips[trip_id]

def tally(trip: dict) -> dict:
    dest = [{"option": k, "votes": v} for k, v in trip["votes"]["destination"].items()]
    dates = [{"option": k, "votes": v} for k, v in trip["votes"]["dates"].items()]
    dest.sort(key=lambda x: x["votes"], reverse=True)
    dates.sort(key=lambda x: x["votes"], reverse=True)
    winner = {
        "destination": dest[0]["option"] if dest else None,
        "dates": dates[0]["option"] if dates else None
    }
    return {"destinations": dest, "dates": dates, "winner": winner}

# --- Endpoints ---
@app.post("/trip")
def create_trip(trip: TripCreate):
    import random, string
    trip_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    t = ensure_trip(trip_id)
    t["title"] = trip.title
    return {"trip_id": trip_id}

@app.get("/trip/{trip_id}/options")
def get_options(trip_id: str):
    t = ensure_trip(trip_id)
    return {"title": t["title"], "options": t["options"]}

@app.post("/trip/{trip_id}/join")
def join_trip(trip_id: str, join: JoinTrip):
    t = ensure_trip(trip_id)
    import random, string
    member_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    t["members"][member_id] = join.name
    return {"member_id": member_id}

@app.post("/trip/{trip_id}/vote")
def vote(trip_id: str, vote: Vote):
    t = ensure_trip(trip_id)
    member_id = vote.member_id
    type_ = vote.type
    option = vote.option

    # init memberVotes
    t["memberVotes"].setdefault(member_id, {})

    # remove previous vote if exists
    prev = t["memberVotes"][member_id].get(type_)
    if prev:
        t["votes"][type_][prev] -= 1
        if t["votes"][type_][prev] <= 0:
            del t["votes"][type_][prev]

    # register new vote
    t["memberVotes"][member_id][type_] = option
    t["votes"][type_][option] = t["votes"][type_].get(option, 0) + 1

    return {"ok": True}

@app.get("/trip/{trip_id}/results")
def results(trip_id: str):
    t = ensure_trip(trip_id)
    return tally(t)

@app.get("/trip/{trip_id}/recommendations")
def recommendations(trip_id: str, avoid_crowds: bool = False):
    """
    Get place recommendations using Person C's crowd-avoidance algorithm.
    
    Query params:
        avoid_crowds: bool - If True, prioritize less-crowded places
    
    Returns:
        {"suggestions": [{"destination": str, "reason": str}, ...]}
    """
    t = ensure_trip(trip_id)
    
    # Get the winning destination from votes
    results_data = tally(t)
    winning_dest = results_data["winner"]["destination"]
    
    if not winning_dest:
        # No destination voted yet, return mock suggestions
        all_dest = t["options"]["destination"]
        picks = [all_dest[1], all_dest[3], all_dest[0]] if len(all_dest) >= 4 else all_dest
        suggestions = [{"destination": d, "reason": "Good weekend value + easy transit"} for d in picks if d]
        return {"suggestions": suggestions}
    
    # Use Person C's algorithm if available
    if ALGORITHMS_AVAILABLE:
        try:
            print(f"🔍 Fetching recommendations for {winning_dest} (avoid_crowds={avoid_crowds})")
            
            # Step 1: Geocode the destination
            coords = place_fetcher.geocode_destination(winning_dest)
            
            if not coords:
                # Fallback if geocoding fails
                print(f"⚠️  Geocoding failed for {winning_dest}")
                return {
                    "suggestions": [{
                        "destination": winning_dest,
                        "reason": "Winner of group vote - couldn't fetch detailed recommendations"
                    }]
                }
            
            lat, lon = coords
            print(f"✅ Geocoded to: {lat}, {lon}")
            
            # Step 2: Fetch nearby places
            places = place_fetcher.fetch_nearby_places(
                lat, lon,
                radius_km=3.0,
                categories=['cafe', 'restaurant', 'museum', 'park', 'attraction']
            )
            
            print(f"✅ Found {len(places)} places")
            
            if not places:
                # No places found
                return {
                    "suggestions": [{
                        "destination": winning_dest,
                        "reason": "Winner of group vote - explore the area!"
                    }]
                }
            
            # Step 3: Rank places using Person C's crowd-avoidance scorer
            ranked_places = CrowdAvoidanceScorer.rank_places(places, avoid_crowds=avoid_crowds)
            
            # Step 4: Format top 5-6 suggestions
            suggestions = []
            for place in ranked_places[:6]:
                # Create reason based on crowd score
                if place.crowd_score < 0.3:
                    reason = f"✨ Hidden gem - {place.category}"
                elif place.crowd_score < 0.6:
                    reason = f"📍 Local favorite - {place.category}"
                else:
                    reason = f"🔥 Popular spot - {place.category}"
                
                # Add distance info
                if place.distance_from_center < 1.0:
                    reason += " (central)"
                elif place.distance_from_center < 2.0:
                    reason += " (nearby)"
                else:
                    reason += f" ({place.distance_from_center:.1f}km away)"
                
                suggestions.append({
                    "destination": place.name,
                    "reason": reason
                })
            
            print(f"✅ Returning {len(suggestions)} suggestions")
            return {"suggestions": suggestions}
            
        except Exception as e:
            print(f"⚠️  Error in recommendations: {e}")
            import traceback
            traceback.print_exc()
            # Fallback on error
            return {
                "suggestions": [{
                    "destination": winning_dest,
                    "reason": "Winner of group vote"
                }]
            }
    else:
        # Fallback when algorithm not available
        print("⚠️  Using fallback recommendations (algorithms not loaded)")
        all_dest = t["options"]["destination"]
        picks = [all_dest[1], all_dest[3], all_dest[0]] if len(all_dest) >= 4 else all_dest
        suggestions = [{"destination": d, "reason": "Good weekend value + easy transit"} for d in picks if d]
        return {"suggestions": suggestions}


@app.get("/trip/{trip_id}/itinerary")
def generate_itinerary(trip_id: str, avoid_crowds: bool = False):
    """
    Generate a basic itinerary using Person C's algorithms.
    
    Query params:
        avoid_crowds: bool - If True, prioritize less-crowded places
    
    Returns:
        {
            "trip_id": str,
            "destination": str,
            "avoid_crowds_mode": bool,
            "days": {...},
            "recommendations": [...]
        }
    """
    t = ensure_trip(trip_id)
    
    # Get winning destination
    results_data = tally(t)
    winning_dest = results_data["winner"]["destination"]
    
    if not winning_dest:
        raise HTTPException(status_code=400, detail="No destination selected yet. Vote first!")
    
    # Default 3-day itinerary skeleton
    days = {
        "day_1": {
            "morning": f"Explore central {winning_dest}",
            "afternoon": "Local lunch + main attraction",
            "evening": "Dinner at recommended restaurant"
        },
        "day_2": {
            "morning": "Day trip or museum visit",
            "afternoon": "Shopping or local markets",
            "evening": "Evening stroll + nightlife"
        },
        "day_3": {
            "morning": "Leisurely breakfast",
            "afternoon": "Last-minute sightseeing",
            "evening": "Departure prep"
        }
    }
    
    recommendations = []
    
    # Use Person C's algorithm if available
    if ALGORITHMS_AVAILABLE:
        try:
            coords = place_fetcher.geocode_destination(winning_dest)
            
            if coords:
                lat, lon = coords
                places = place_fetcher.fetch_nearby_places(lat, lon, radius_km=3.0)
                
                if places:
                    ranked_places = CrowdAvoidanceScorer.rank_places(places, avoid_crowds=avoid_crowds)
                    
                    # Create recommendations list
                    for place in ranked_places[:10]:
                        recommendations.append({
                            "name": place.name,
                            "category": place.category,
                            "crowd_score": round(place.crowd_score, 2),
                            "distance_km": round(place.distance_from_center, 2),
                            "is_hidden_gem": place.crowd_score < 0.3
                        })
                    
                    # Customize itinerary with top recommendations
                    if len(ranked_places) >= 1:
                        days["day_1"]["morning"] = f"Visit {ranked_places[0].name}"
                    if len(ranked_places) >= 2:
                        days["day_1"]["afternoon"] = f"Explore {ranked_places[1].name}"
                    if len(ranked_places) >= 3:
                        days["day_2"]["morning"] = f"Day at {ranked_places[2].name}"
                    if len(ranked_places) >= 4:
                        days["day_2"]["afternoon"] = f"Visit {ranked_places[3].name}"
        
        except Exception as e:
            print(f"⚠️  Error generating itinerary: {e}")
    
    return {
        "trip_id": trip_id,
        "destination": winning_dest,
        "avoid_crowds_mode": avoid_crowds,
        "days": days,
        "recommendations": recommendations
    }


@app.post("/trip/{trip_id}/expense")
def add_expense(trip_id: str, expense: ExpenseCreate):
    """
    Add an expense to the trip.
    
    Body:
        {
            "amount": 100.0,
            "paid_by": "Alice",
            "split_between": ["Alice", "Bob", "Charlie"],
            "description": "Dinner"
        }
    """
    t = ensure_trip(trip_id)
    
    expense_data = {
        "amount": expense.amount,
        "paid_by": expense.paid_by,
        "split_between": expense.split_between,
        "description": expense.description or "Expense"
    }
    
    t["expenses"].append(expense_data)
    
    return {
        "ok": True,
        "expense": expense_data
    }


@app.get("/trip/{trip_id}/settle")
def settle_expenses(trip_id: str):
    """
    Calculate minimal transfers to settle all expenses using Person C's algorithm.
    
    Returns:
        {
            "trip_id": str,
            "transfers": [{"from_person": str, "to_person": str, "amount": float}, ...],
            "total_expenses": float,
            "summary": str
        }
    """
    t = ensure_trip(trip_id)
    
    expenses = t["expenses"]
    
    if not expenses:
        return {
            "trip_id": trip_id,
            "transfers": [],
            "total_expenses": 0.0,
            "summary": "No expenses to settle"
        }
    
    # Use Person C's SettlementCalculator if available
    if ALGORITHMS_AVAILABLE:
        try:
            print(f"💰 Calculating settlement for {len(expenses)} expenses")
            
            # Calculate settlements using Person C's algorithm
            transfers = SettlementCalculator.calculate_settlements(expenses)
            
            # Convert Transfer objects to dicts
            transfer_dicts = [
                {
                    "from_person": t.from_person,
                    "to_person": t.to_person,
                    "amount": round(t.amount, 2)
                }
                for t in transfers
            ]
            
            total = sum(exp["amount"] for exp in expenses)
            summary = SettlementCalculator.format_settlement_summary(transfers)
            
            print(f"✅ Settlement complete: {len(transfer_dicts)} transfers")
            
            return {
                "trip_id": trip_id,
                "transfers": transfer_dicts,
                "total_expenses": round(total, 2),
                "summary": summary
            }
        
        except Exception as e:
            print(f"⚠️  Error calculating settlement: {e}")
            import traceback
            traceback.print_exc()
            return {
                "trip_id": trip_id,
                "transfers": [],
                "total_expenses": sum(exp["amount"] for exp in expenses),
                "summary": f"Error calculating settlement: {e}"
            }
    else:
        # Fallback: simple balance calculation without optimization
        print("⚠️  Using fallback settlement (algorithms not loaded)")
        balances = defaultdict(float)
        
        for expense in expenses:
            amount = expense["amount"]
            paid_by = expense["paid_by"]
            split_between = expense["split_between"]
            share = amount / len(split_between)
            
            balances[paid_by] += amount
            for person in split_between:
                balances[person] -= share
        
        # Simple transfer list (not optimized)
        transfers = []
        for person, balance in balances.items():
            if balance < -0.01:
                transfers.append({
                    "from_person": person,
                    "to_person": "Others",
                    "amount": round(abs(balance), 2)
                })
        
        return {
            "trip_id": trip_id,
            "transfers": transfers,
            "total_expenses": sum(exp["amount"] for exp in expenses),
            "summary": "Settlement calculated (algorithm not available)"
        }


@app.get("/")
def root():
    """Health check"""
    return {
        "status": "ok",
        "message": "Trip Coordinator API",
        "algorithms_available": ALGORITHMS_AVAILABLE
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
