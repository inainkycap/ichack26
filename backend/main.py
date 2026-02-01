from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Literal, List

# Import Person C algorithms
try:
    from algorithm_person_c import SettlementCalculator, PlaceFetcher, CrowdAvoidanceScorer
    ALGORITHMS_AVAILABLE = True
except Exception:
    ALGORITHMS_AVAILABLE = False

app = FastAPI(title="Collie API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Extra safety: respond to any preflight OPTIONS
@app.options("/{path:path}")
def preflight_handler(path: str):
    return {}

# In-memory store
trips: Dict[str, dict] = {}

if ALGORITHMS_AVAILABLE:
    place_fetcher = PlaceFetcher()

# -------------------------
# Models
# -------------------------
class TripCreate(BaseModel):
    title: Optional[str] = "Weekend Trip"

class TripUpdate(BaseModel):
    title: str

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

class OptionCreate(BaseModel):
    type: Literal["destination", "dates"]
    label: str

# -------------------------
# Helpers
# -------------------------
def ensure_trip(trip_id: str) -> dict:
    if trip_id not in trips:
        trips[trip_id] = {
            "title": "Weekend Trip",
            "members": {},  # member_id -> name
            "votes": {"destination": {}, "dates": {}},
            "memberVotes": {},  # member_id -> {destination: "...", dates: "..."}
            "expenses": [],
            "options": {
                "destination": ["Lisbon", "Porto", "Barcelona", "Valencia", "Amsterdam"],
                "dates": ["Feb 7 - Feb 9", "Feb 14 - Feb 16", "Mar 1 - Mar 3", "Mar 8 - Mar 10"],
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
        "dates": dates[0]["option"] if dates else None,
    }
    return {"destinations": dest, "dates": dates, "winner": winner}

def total_spent(trip: dict) -> float:
    return round(sum(e["amount"] for e in trip["expenses"]), 2)

def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        k = x.strip()
        if not k:
            continue
        low = k.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(k)
    return out

# -------------------------
# Core trip endpoints
# -------------------------
@app.post("/trip")
def create_trip(trip: TripCreate):
    import random, string
    trip_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    t = ensure_trip(trip_id)
    t["title"] = (trip.title or "Weekend Trip").strip() or "Weekend Trip"
    return {"trip_id": trip_id}

@app.get("/trip/{trip_id}")
def get_trip(trip_id: str):
    t = ensure_trip(trip_id)
    return {
        "trip_id": trip_id,
        "title": t["title"],
        "member_count": len(t["members"]),
        "total_spent": total_spent(t),
        "winner": tally(t)["winner"],
    }

@app.put("/trip/{trip_id}")
def update_trip(trip_id: str, update: TripUpdate):
    t = ensure_trip(trip_id)
    new_title = (update.title or "").strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    t["title"] = new_title
    return {"ok": True, "title": t["title"]}

@app.get("/trip/{trip_id}/members")
def get_members(trip_id: str):
    t = ensure_trip(trip_id)
    members = [{"member_id": mid, "name": name} for mid, name in t["members"].items()]
    members.sort(key=lambda m: m["name"].lower())
    return {"members": members}

@app.get("/trip/{trip_id}/options")
def get_options(trip_id: str):
    t = ensure_trip(trip_id)
    # Keep options clean (dedupe) in case of repeated adds
    t["options"]["destination"] = _dedupe_keep_order(t["options"].get("destination", []))
    t["options"]["dates"] = _dedupe_keep_order(t["options"].get("dates", []))
    return {"title": t["title"], "options": t["options"]}

@app.post("/trip/{trip_id}/options")
def add_option(trip_id: str, option: OptionCreate):
    """
    Add a new option to destination/dates list (used by frontend Add buttons).
    """
    t = ensure_trip(trip_id)
    label = (option.label or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="label cannot be empty")

    t["options"].setdefault(option.type, [])
    current = t["options"][option.type]

    # Case-insensitive uniqueness
    existing = {x.lower() for x in current}
    if label.lower() not in existing:
        current.insert(0, label)

    # Return updated options
    t["options"][option.type] = _dedupe_keep_order(current)
    return {"ok": True, "options": t["options"]}

@app.post("/trip/{trip_id}/join")
def join_trip(trip_id: str, join: JoinTrip):
    t = ensure_trip(trip_id)
    import random, string
    member_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    t["members"][member_id] = (join.name or "Anonymous").strip() or "Anonymous"
    return {"member_id": member_id}

@app.post("/trip/{trip_id}/vote")
def vote(trip_id: str, vote: Vote):
    t = ensure_trip(trip_id)
    member_id = vote.member_id
    type_ = vote.type
    option = vote.option

    t["memberVotes"].setdefault(member_id, {})
    prev = t["memberVotes"][member_id].get(type_)

    if prev:
        t["votes"][type_][prev] -= 1
        if t["votes"][type_][prev] <= 0:
            del t["votes"][type_][prev]

    t["memberVotes"][member_id][type_] = option
    t["votes"][type_][option] = t["votes"][type_].get(option, 0) + 1
    return {"ok": True}

@app.get("/trip/{trip_id}/results")
def results(trip_id: str):
    t = ensure_trip(trip_id)
    return tally(t)

# -------------------------
# Recommendations / Itinerary (anti-touristy default)
# -------------------------
@app.get("/trip/{trip_id}/recommendations")
def recommendations(trip_id: str):
    t = ensure_trip(trip_id)
    winning_dest = tally(t)["winner"]["destination"]

    if not winning_dest:
        all_dest = t["options"]["destination"]
        picks = [d for d in all_dest[:3] if d]
        return {"suggestions": [{"destination": d, "reason": "Vote first — here are starter ideas"} for d in picks]}

    # Anti-touristy default: rank less crowded first
    if ALGORITHMS_AVAILABLE:
        try:
            coords = place_fetcher.geocode_destination(winning_dest)
            if not coords:
                return {"suggestions": [{"destination": winning_dest, "reason": "Winner of vote"}]}

            lat, lon = coords
            places = place_fetcher.fetch_nearby_places(
                lat, lon, radius_km=3.0, categories=["cafe", "restaurant", "museum", "park", "attraction"]
            )
            if not places:
                return {"suggestions": [{"destination": winning_dest, "reason": "Winner of vote"}]}

            ranked = CrowdAvoidanceScorer.rank_places(places, avoid_crowds=True)  # always true for Collie
            out = []
            for p in ranked[:6]:
                if p.crowd_score < 0.3:
                    reason = f"✨ Hidden gem • {p.category}"
                elif p.crowd_score < 0.6:
                    reason = f"📍 Local vibe • {p.category}"
                else:
                    reason = f"🔥 Busier • {p.category}"
                out.append({"destination": p.name, "reason": reason})
            return {"suggestions": out}
        except Exception:
            return {"suggestions": [{"destination": winning_dest, "reason": "Winner of vote"}]}

    return {"suggestions": [{"destination": winning_dest, "reason": "Winner of vote"}]}

@app.get("/trip/{trip_id}/itinerary")
def itinerary(trip_id: str):
    t = ensure_trip(trip_id)
    winning_dest = tally(t)["winner"]["destination"]
    if not winning_dest:
        raise HTTPException(status_code=400, detail="No destination selected yet. Vote first!")

    days = {
        "day_1": {"morning": f"Explore {winning_dest} (slow start)", "afternoon": "Local lunch + walk", "evening": "Dinner in a neighbourhood"},
        "day_2": {"morning": "Museum / park", "afternoon": "Markets / bookshops", "evening": "Low-key bars / sunset spot"},
        "day_3": {"morning": "Brunch", "afternoon": "Last sights", "evening": "Pack + depart"},
    }

    recommendations = []
    if ALGORITHMS_AVAILABLE:
        try:
            coords = place_fetcher.geocode_destination(winning_dest)
            if coords:
                lat, lon = coords
                places = place_fetcher.fetch_nearby_places(lat, lon, radius_km=3.0)
                if places:
                    ranked = CrowdAvoidanceScorer.rank_places(places, avoid_crowds=True)
                    for p in ranked[:10]:
                        recommendations.append({
                            "name": p.name,
                            "category": p.category,
                            "crowd_score": round(p.crowd_score, 2),
                            "distance_km": round(p.distance_from_center, 2),
                            "is_hidden_gem": p.crowd_score < 0.3
                        })
                    if len(ranked) >= 1:
                        days["day_1"]["morning"] = f"Coffee / start at {ranked[0].name}"
                    if len(ranked) >= 2:
                        days["day_1"]["afternoon"] = f"Wander around {ranked[1].name}"
                    if len(ranked) >= 3:
                        days["day_2"]["morning"] = f"Go to {ranked[2].name}"
        except Exception:
            pass

    return {
        "trip_id": trip_id,
        "destination": winning_dest,
        "days": days,
        "recommendations": recommendations,
    }

# -------------------------
# Expenses / Settlement
# -------------------------
@app.post("/trip/{trip_id}/expense")
def add_expense(trip_id: str, expense: ExpenseCreate):
    t = ensure_trip(trip_id)

    data = {
        "amount": float(expense.amount),
        "paid_by": (expense.paid_by or "").strip(),
        "split_between": [s.strip() for s in expense.split_between if s.strip()],
        "description": (expense.description or "Expense").strip(),
    }

    if data["amount"] <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    if not data["paid_by"]:
        raise HTTPException(status_code=400, detail="paid_by is required")
    if not data["split_between"]:
        raise HTTPException(status_code=400, detail="split_between must contain at least one name")

    t["expenses"].append(data)
    return {"ok": True, "expense": data, "total_spent": total_spent(t)}

@app.get("/trip/{trip_id}/expenses")
def get_expenses(trip_id: str):
    t = ensure_trip(trip_id)
    return {"expenses": t["expenses"], "total_spent": total_spent(t)}

@app.get("/trip/{trip_id}/settle")
def settle(trip_id: str):
    t = ensure_trip(trip_id)
    expenses = t["expenses"]
    if not expenses:
        return {"trip_id": trip_id, "transfers": [], "total_expenses": 0.0, "summary": "No expenses to settle"}

    if ALGORITHMS_AVAILABLE:
        transfers = SettlementCalculator.calculate_settlements(expenses)
        transfer_dicts = [{"from_person": tr.from_person, "to_person": tr.to_person, "amount": round(tr.amount, 2)} for tr in transfers]
        summary = SettlementCalculator.format_settlement_summary(transfers)
        total = sum(e["amount"] for e in expenses)
        return {"trip_id": trip_id, "transfers": transfer_dicts, "total_expenses": round(total, 2), "summary": summary}

    return {"trip_id": trip_id, "transfers": [], "total_expenses": sum(e["amount"] for e in expenses), "summary": "Settlement algorithm unavailable"}

@app.get("/")
def root():
    return {"status": "ok", "message": "Collie API", "algorithms_available": ALGORITHMS_AVAILABLE}
