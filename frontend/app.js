import {
    createTrip,
    getTripOptions,
    joinTrip,
    castVote,
    getTripResults,
    getRecommendations,
} from "./api.js";

const $ = (s) => document.querySelector(s);

const ls = {
    set(k, v) { localStorage.setItem(k, JSON.stringify(v)); },
    get(k, fb = null) {
        try { return JSON.parse(localStorage.getItem(k)) ?? fb; }
        catch { return fb; }
    },
};

const SUGGESTED_CITIES = [
    "Paris", "London", "Barcelona", "Madrid", "Lisbon", "Porto", "Rome", "Milan",
    "Amsterdam", "Berlin", "Munich", "Vienna", "Prague", "Budapest", "Warsaw",
    "Copenhagen", "Stockholm", "Oslo", "Helsinki", "Dublin", "Edinburgh",
    "Brussels", "Zurich", "Geneva", "Athens", "Istanbul", "Dubrovnik",
    "Valencia", "Seville", "Granada", "Malaga", "Bilbao", "Nice", "Lyon",
    "Marseille", "Florence", "Venice", "Naples", "Krakow", "Wroclaw"
];


function lsGet(key, fallback = null) {
    try {
        return JSON.parse(localStorage.getItem(key)) ?? fallback;
    } catch {
        return fallback;
    }
}

function lsSet(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

function toast(msg) {
    const t = $("#toast");
    if (!t) return;
    t.textContent = msg;
    t.classList.remove("opacity-0", "translate-y-2");
    t.classList.add("opacity-100", "translate-y-0");
    setTimeout(() => {
        t.classList.add("opacity-0", "translate-y-2");
        t.classList.remove("opacity-100", "translate-y-0");
    }, 1200);
}

function getTripId() {
    const url = new URL(window.location.href);
    return url.searchParams.get("trip") || ls.get("trip_id");
}

function setActiveStep(step) {
    const steps = ["step-join", "step-vote", "step-results"];
    steps.forEach((id, i) => {
        const el = document.getElementById(id);
        if (!el) return;
        const active = i <= step;
        el.className = active
            ? "px-3 py-1 rounded-full text-xs font-medium bg-pink-500 text-white"
            : "px-3 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-500";
    });
}

function renderPills(container, options, onPick) {
    container.innerHTML = "";
    options.forEach((opt) => {
        const b = document.createElement("button");
        b.className =
            "pill px-3 py-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50 transition text-sm";
        b.textContent = opt;
        b.onclick = () => onPick(opt, b);
        container.appendChild(b);
    });
}

function selectPill(container, btn) {
    [...container.querySelectorAll(".pill")].forEach((b) => {
        b.className =
            "pill px-3 py-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50 transition text-sm";
    });
    btn.className =
        "pill px-3 py-2 rounded-full border border-pink-200 bg-pink-500 text-white shadow-sm transition text-sm";
}

export async function initIndex() {
    $("#createBtn").addEventListener("click", async () => {
        const title = $("#tripTitle").value.trim() || "Weekend Trip";
        const data = await createTrip(title);

        localStorage.setItem("trip_id", JSON.stringify(data.trip_id));
        localStorage.setItem(`trip_title_${data.trip_id}`, JSON.stringify(title));

        const link = `${window.location.origin}${window.location.pathname.replace("index.html", "")}trip.html?trip=${data.trip_id}`;
        $("#inviteLink").value = link;
        $("#shareCard").classList.remove("hidden");
        toast("Link created");
    });

    $("#copyBtn").addEventListener("click", async () => {
        await navigator.clipboard.writeText($("#inviteLink").value);
        toast("Copied link");
    });

    $("#goBtn").addEventListener("click", () => {
        const tripId = JSON.parse(localStorage.getItem("trip_id"));
        window.location.href = `trip.html?trip=${tripId}`;
    });
}

export async function initTrip() {
    const tripId = getTripId();
    if (!tripId) {
        $("#error").textContent = "No trip found. Go back and create a link.";
        return;
    }
    lsSet("trip_id", tripId);
    $("#tripChip").textContent = `Trip • ${tripId}`;

    // ✅ If already joined earlier, prefill name + set step
    const existingMember = ls.get(`member_${tripId}`, null);
    if (existingMember?.name) {
        $("#nameInput").value = existingMember.name;
        setActiveStep(1);
    }

    const opt = await getTripOptions(tripId);

    const savedTitle = lsGet(`trip_title_${tripId}`, null);
    const apiTitle = (opt.title || "").trim();

    const finalTitle =
        (!apiTitle || apiTitle === "Weekend Trip") && savedTitle
            ? savedTitle
            : (apiTitle || savedTitle || "Weekend Trip");

    $("#tripTitle").textContent = finalTitle;
    lsSet(`trip_title_${tripId}`, finalTitle); // keep it consistent

    const destWrap = $("#destOptions");
    const dateWrap = $("#dateOptions");

    // Make local mutable copies (so we can add options on the fly)
    const destinationOptions = [...new Set([...SUGGESTED_CITIES, ...opt.options.destination])];

    const dateOptions = [...opt.options.dates];

    function renderAll() {
        renderPills(destWrap, destinationOptions, async (choice, btn) => {
            const ok = await vote(tripId, "destination", choice);
            if (ok) selectPill(destWrap, btn);
        });

        renderPills(dateWrap, dateOptions, async (choice, btn) => {
            const ok = await vote(tripId, "dates", choice);
            if (ok) selectPill(dateWrap, btn);
        });
    }

    renderAll();

    // Add destination button
    $("#addDestBtn").addEventListener("click", () => {
        const v = ($("#destInput").value || "").trim();
        if (!v) return;

        if (!destinationOptions.includes(v)) {
            destinationOptions.unshift(v);
            renderAll();
            toast("Added destination");
        }
        $("#destInput").value = "";
    });

    // Add date range button
    $("#addDateBtn").addEventListener("click", () => {
        const start = $("#startDate").value;
        const end = $("#endDate").value;

        if (!start || !end) {
            toast("Pick start + end");
            return;
        }

        if (end < start) {
            toast("End date must be after start");
            return;
        }

        const label = `${start} → ${end}`;

        if (!dateOptions.includes(label)) {
            dateOptions.unshift(label);
            renderAll();
            toast("Added date range");
        }
    });

    $("#joinBtn").addEventListener("click", async () => {
        const name = $("#nameInput").value.trim() || "Anonymous";
        const data = await joinTrip(tripId, name);

        // ✅ store member so voting works
        ls.set(`member_${tripId}`, { id: data.member_id, name: name });

        toast(`Joined as ${name}`);
        setActiveStep(1);
        await refresh(tripId);
    });

    await refresh(tripId);
    setInterval(() => refresh(tripId), 5000);

    $("#recsBtn").addEventListener("click", async () => {
        await refreshRecs(tripId);
        toast("Updated suggestions");
    });
}

async function vote(tripId, type, option) {
    const member = ls.get(`member_${tripId}`, null);
    if (!member?.id) {
        toast("Join first");
        return false;
    }
    await castVote(tripId, member.id, type, option);

    toast(`Voted: ${option}`);
    setActiveStep(2);
    await refresh(tripId);
    return true;
}

async function refresh(tripId) {
    const data = await getTripResults(tripId);
    $("#winnerDest").textContent = data.winner.destination ?? "—";
    $("#winnerDate").textContent = data.winner.dates ?? "—";
    renderList($("#destResults"), data.destinations);
    renderList($("#dateResults"), data.dates);
}

function renderList(el, items) {
    el.innerHTML = "";
    const filtered = (items || []).filter(it => (it.votes || 0) > 0);

    if (!filtered.length) {
        el.innerHTML = `<div class="text-sm text-slate-500">No votes yet</div>`;
        return;
    }

    filtered.forEach((it) => {
        const row = document.createElement("div");
        row.className = "flex items-center justify-between text-sm py-1";
        row.innerHTML = `<span class="text-slate-700">${it.option}</span>
                        <span class="font-semibold text-slate-900">${it.votes}</span>`;
        el.appendChild(row);
    });
}

async function refreshRecs(tripId) {
    const data = await getRecommendations(tripId);
    const el = $("#recsList");
    el.innerHTML = "";
    (data.suggestions || []).slice(0, 3).forEach((s) => {
        const card = document.createElement("div");
        card.className = "p-4 rounded-2xl border border-slate-200 bg-white";
        card.innerHTML = `
            <div class="font-semibold text-slate-900">${s.destination}</div>
            <div class="text-sm text-slate-600 mt-1">${s.reason}</div>
        `;
        el.appendChild(card);
    });
}
