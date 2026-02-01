window.API_BASE = "https://ichack26-backend.onrender.com";

async function readError(res) {
  const txt = await res.text().catch(() => "");
  return txt || `${res.status} ${res.statusText}`;
}

export async function apiFetch(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();

  // POST/PUT with JSON triggers preflight; backend supports OPTIONS now.
  const headers = {
    ...(options.headers || {}),
    ...(method !== "GET" && method !== "HEAD" ? { "Content-Type": "application/json" } : {}),
  };

  let res;
  try {
    res = await fetch(`${window.API_BASE}${path}`, { ...options, method, headers });
  } catch {
    throw new Error(`Network error: cannot reach ${window.API_BASE}. Is backend running?`);
  }

  if (!res.ok) throw new Error(await readError(res));
  return await res.json();
}

// Trip
export const createTrip = (title) =>
  apiFetch("/trip", { method: "POST", body: JSON.stringify({ title }) });

export const getTrip = (tripId) => apiFetch(`/trip/${tripId}`);

export const updateTripTitle = (tripId, title) =>
  apiFetch(`/trip/${tripId}`, { method: "PUT", body: JSON.stringify({ title }) });

export const getMembers = (tripId) => apiFetch(`/trip/${tripId}/members`);

// Options / join / vote / results
export const getTripOptions = (tripId) => apiFetch(`/trip/${tripId}/options`);

export const joinTrip = (tripId, name) =>
  apiFetch(`/trip/${tripId}/join`, { method: "POST", body: JSON.stringify({ name }) });

export const castVote = (tripId, memberId, type, option) =>
  apiFetch(`/trip/${tripId}/vote`, {
    method: "POST",
    body: JSON.stringify({ member_id: memberId, type, option }),
  });

export const getTripResults = (tripId) => apiFetch(`/trip/${tripId}/results`);

// Recs / itinerary (anti-touristy by default on the backend)
export const getRecommendations = (tripId) =>
  apiFetch(`/trip/${tripId}/recommendations`);

export const getItinerary = (tripId) =>
  apiFetch(`/trip/${tripId}/itinerary`);

// Expenses / settle
export const addExpense = (tripId, expense) =>
  apiFetch(`/trip/${tripId}/expense`, { method: "POST", body: JSON.stringify(expense) });

export const getExpenses = (tripId) => apiFetch(`/trip/${tripId}/expenses`);

export const getSettlement = (tripId) => apiFetch(`/trip/${tripId}/settle`);

// Add option (ONLY works if backend implements POST /trip/{id}/options)
export const addOption = (tripId, type, label) =>
  apiFetch(`/trip/${tripId}/options`, {
    method: "POST",
    body: JSON.stringify({ type, label }),
  });
