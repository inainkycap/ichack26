import { getTrip, getMembers } from "./api.js";

export const $ = (s) => document.querySelector(s);

export const BRAND = {
  name: "Collie",
  tagline: "herding you to your next destination",
};

export function toast(msg) {
  const t = $("#toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.remove("opacity-0", "translate-y-2");
  t.classList.add("opacity-100", "translate-y-0");
  setTimeout(() => {
    t.classList.add("opacity-0", "translate-y-2");
    t.classList.remove("opacity-100", "translate-y-0");
  }, 1400);
}

export function getTripId() {
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get("trip");
  if (fromUrl) return fromUrl;
  try { return JSON.parse(localStorage.getItem("trip_id") || "null"); }
  catch { return null; }
}

export function setTripId(tripId) {
  localStorage.setItem("trip_id", JSON.stringify(tripId));
}

export function nav(page, tripId) {
  window.location.href = `${page}?trip=${encodeURIComponent(tripId)}`;
}

export function getMember(tripId) {
  try { return JSON.parse(localStorage.getItem(`member_${tripId}`) || "null"); }
  catch { return null; }
}

export function setMember(tripId, member) {
  localStorage.setItem(`member_${tripId}`, JSON.stringify(member));
}

export function requireTripId() {
  const tripId = getTripId();
  if (!tripId) {
    toast("No trip found. Create one first.");
    window.location.href = "index.html";
    return null;
  }
  setTripId(tripId);
  return tripId;
}

export function requireMember(tripId) {
  const m = getMember(tripId);
  if (!m?.id) {
    toast("Join first");
    nav("join.html", tripId);
    return null;
  }
  return m;
}

export async function renderTripHeader(tripId) {
  const chip = $("#tripChip");
  const titleEl = $("#tripTitle");
  const brandEl = $("#brandLine");

  if (chip) chip.textContent = `${BRAND.name} • Trip ${tripId}`;
  if (brandEl) brandEl.textContent = `${BRAND.name} — ${BRAND.tagline}`;

  if (titleEl) {
    // Show loading state first
    titleEl.textContent = "Loading...";
    
    try {
      const t = await getTrip(tripId);
      const actualTitle = (t.title || "").trim();
      
      // Use actual title if it exists and isn't the default
      if (actualTitle && actualTitle !== "Weekend Trip") {
        titleEl.textContent = actualTitle;
      } else {
        // Check localStorage as fallback
        const localTitle = localStorage.getItem(`trip_title_${tripId}`);
        if (localTitle) {
          try {
            titleEl.textContent = JSON.parse(localTitle);
          } catch {
            titleEl.textContent = localTitle;
          }
        } else {
          titleEl.textContent = actualTitle || "Trip";
        }
      }
    } catch (error) {
      console.error("Failed to fetch trip title:", error);
      
      // Fallback to localStorage
      try {
        const localTitle = localStorage.getItem(`trip_title_${tripId}`);
        if (localTitle) {
          titleEl.textContent = JSON.parse(localTitle);
        } else {
          titleEl.textContent = "Trip";
        }
      } catch {
        titleEl.textContent = "Trip";
      }
    }
  }
}

export async function renderMemberList(tripId, elId) {
  const el = document.getElementById(elId);
  if (!el) return;

  try {
    const data = await getMembers(tripId);
    const members = data.members || [];
    if (!members.length) {
      el.innerHTML = `<div class="text-base text-slate-500">No one joined yet</div>`;
      return;
    }
    el.innerHTML = "";
    members.forEach((m) => {
      const row = document.createElement("div");
      row.className = "flex items-center justify-between py-3 border-b border-slate-100";
      row.innerHTML = `
        <div class="text-slate-900 font-semibold text-base">${m.name}</div>
        <div class="text-xs text-slate-400">${m.member_id}</div>
      `;
      el.appendChild(row);
    });
  } catch {
    el.innerHTML = `<div class="text-base text-red-600">Failed to load members</div>`;
  }
}

export function prettyRange(startISO, endISO) {
  const a = new Date(`${startISO}T00:00:00`);
  const b = new Date(`${endISO}T00:00:00`);
  const fmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
  const fmtY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });

  if (a.getFullYear() === b.getFullYear()) return `${fmt.format(a)} – ${fmt.format(b)}`;
  return `${fmtY.format(a)} – ${fmtY.format(b)}`;
}
