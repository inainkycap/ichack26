import { $, toast, requireTripId, requireMember, renderTripHeader, nav } from "./common.js";

function buildInviteLink(tripId) {
  // Always generate based on current origin + path (works even if you host elsewhere)
  const base = `${window.location.origin}${window.location.pathname.replace("menu.html", "")}`;
  return `${base}join.html?trip=${encodeURIComponent(tripId)}`;
}

document.addEventListener("DOMContentLoaded", async () => {
  const tripId = requireTripId();
  if (!tripId) return;

  const member = requireMember(tripId);
  if (!member) return;

  await renderTripHeader(tripId);

  $("#backBtn").addEventListener("click", () => nav("join.html", tripId));
  $("#voteBtn").addEventListener("click", () => nav("vote.html", tripId));
  $("#itineraryBtn").addEventListener("click", () => nav("itinerary.html", tripId));
  $("#expensesBtn").addEventListener("click", () => nav("expenses.html", tripId));
  $("#settingsBtn").addEventListener("click", () => nav("settings.html", tripId));

  // Invite link re-copy (anytime)
  const inviteCard = $("#inviteCard");
  const inviteLinkInput = $("#inviteLink");

  $("#inviteBtn").addEventListener("click", () => {
    const link = buildInviteLink(tripId);
    inviteLinkInput.value = link;
    inviteCard.classList.remove("hidden");
    toast("Invite link ready");
  });

  $("#copyBtn").addEventListener("click", async () => {
    const link = inviteLinkInput.value || buildInviteLink(tripId);
    await navigator.clipboard.writeText(link);
    toast("Copied invite link");
  });
});
