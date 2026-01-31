from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Literal
from collections import defaultdict

app = FastAPI()

# --- In-memory storage, mirrors mockStore ---
trips: Dict[str, dict] = {}

# --- Models ---
class TripCreate(BaseModel):
    title: Optional[str] = "Weekend Trip"

class JoinTrip(BaseModel):
    name: Optional[str] = "Anonymous"

class Vote(BaseModel):
    type: Literal["destination", "dates"]
    option: str
    member_id: str

# --- Helpers ---
def ensure_trip(trip_id: str) -> dict:
    if trip_id not in trips:
        trips[trip_id] = {
            "title": f"Weekend Trip",
            "members": {},
            "votes": {"destination": {}, "dates": {}},
            "memberVotes": {},  # track individual member votes
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
def recommendations(trip_id: str):
    t = ensure_trip(trip_id)
    all_dest = t["options"]["destination"]
    picks = [all_dest[1], all_dest[3], all_dest[0]] if len(all_dest) >= 4 else all_dest
    suggestions = [{"destination": d, "reason": "Good weekend value + easy transit"} for d in picks if d]
    return {"suggestions": suggestions}
