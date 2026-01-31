const API_BASE = "http://127.0.0.1:8000";

function uid() {
    return Math.random().toString(36).slice(2, 10);
}

function lsSet(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}
function lsGet(key, fallback = null) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}


const mockStore = { trips: {} };

function ensureTrip(tripId) {
    if (!mockStore.trips[tripId]) {
      const savedTitle = lsGet(`trip_title_${tripId}`, null);

        mockStore.trips[tripId] = {
        title: savedTitle || "Weekend Trip",
        members: {},
        votes: { destination: {}, dates: {} },
        options: {
            destination: ["Lisbon", "Porto", "Barcelona", "Valencia", "Amsterdam"],
            dates: ["Feb 7–9", "Feb 14–16", "Mar 1–3", "Mar 8–10"],
        },
      };
    }
    return mockStore.trips[tripId];
}


function tally(trip) {
    const dest = Object.entries(trip.votes.destination).map(([option, votes]) => ({ option, votes }));
    const dates = Object.entries(trip.votes.dates).map(([option, votes]) => ({ option, votes }));
    dest.sort((a, b) => b.votes - a.votes);
    dates.sort((a, b) => b.votes - a.votes);
    return {
        destinations: dest,
        dates,
        winner: { destination: dest[0]?.option ?? null, dates: dates[0]?.option ?? null },
    };
}

async function mock(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const body = options.body ? JSON.parse(options.body) : null;

    if (method === "POST" && path === "/trip") {
        const tripId = uid();
        const trip = ensureTrip(tripId);
        trip.title = body?.title || "Weekend Trip";

        lsSet(`trip_title_${tripId}`, trip.title); // ✅ persist title
        return { trip_id: tripId };
    }   


    const optMatch = path.match(/^\/trip\/([^/]+)\/options$/);
    if (method === "GET" && optMatch) {
        const trip = ensureTrip(optMatch[1]);
        return { title: trip.title, options: trip.options };
    }

    const joinMatch = path.match(/^\/trip\/([^/]+)\/join$/);
    if (method === "POST" && joinMatch) {
        const trip = ensureTrip(joinMatch[1]);
        const memberId = uid();
        trip.members[memberId] = body?.name || "Anonymous";
        return { member_id: memberId };
    }

    const voteMatch = path.match(/^\/trip\/([^/]+)\/vote$/);
if (method === "POST" && voteMatch) {
    const trip = ensureTrip(voteMatch[1]);
    const type = body?.type; // "destination" | "dates"
    const option = body?.option;
    const memberId = body?.member_id;

    if (!type || !option || !memberId) return { ok: false };

    // Track a single vote per member per type, allow changing vote without inflating totals
    trip.memberVotes ??= {};                             // memberId -> { destination: "...", dates: "..." }
    trip.memberVotes[memberId] ??= {};

    const prev = trip.memberVotes[memberId][type];
    if (prev && trip.votes[type][prev] != null) {
        const newCount = (trip.votes[type][prev] || 0) - 1;
        if (newCount <= 0) {
                delete trip.votes[type][prev];            // ✅ removes it entirely
        } else {
                trip.votes[type][prev] = newCount;
        }
    }


    trip.memberVotes[memberId][type] = option;
    trip.votes[type][option] = (trip.votes[type][option] || 0) + 1;

    return { ok: true };
}


    const resMatch = path.match(/^\/trip\/([^/]+)\/results$/);
    if (method === "GET" && resMatch) {
        const trip = ensureTrip(resMatch[1]);
        return tally(trip);
    }

    const recMatch = path.match(/^\/trip\/([^/]+)\/recommendations$/);
    if (method === "GET" && recMatch) {
        const trip = ensureTrip(recMatch[1]);
        const all = trip.options.destination;
        const picks = [all[1], all[3], all[0]].filter(Boolean).slice(0, 3);
        return {
            suggestions: picks.map((d) => ({ destination: d, reason: "Good weekend value + easy transit" })),
        };
    }

    return { error: "Mock route not found", path };
}

export async function apiFetch(path, options = {}) {
    const controller = new AbortController();
    const timeoutMs = 250; // fast fallback
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const res = await fetch(`${API_BASE}${path}`, {
            signal: controller.signal,
            headers: { "Content-Type": "application/json", ...(options.headers || {}) },
            ...options,
        });
        clearTimeout(timer);
        if (!res.ok) throw new Error(await res.text());
        return await res.json();
    } catch (e) {
        clearTimeout(timer);
        console.warn("API fallback:", path, e);
        return await mock(path, options);
    }
}

