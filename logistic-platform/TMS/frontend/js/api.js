// ============================================================
// FreightBid — Shared API Utility
// All fetch() calls live here. Import this in every HTML page.
// ============================================================

const BASE = "";  // same origin — no need for absolute URL

// ---------- Auth helpers (localStorage) ----------

function saveAuth(data) {
    localStorage.setItem("fb_token", data.token);
    localStorage.setItem("fb_role", data.role);
    localStorage.setItem("fb_name", data.name);
    localStorage.setItem("fb_id", data.id);
    if (data.kyc_status !== undefined) {
        localStorage.setItem("fb_kyc_status", data.kyc_status);
    }
}

function getToken() { return localStorage.getItem("fb_token"); }
function getRole() { return localStorage.getItem("fb_role"); }
function getName() { return localStorage.getItem("fb_name"); }
function getUserId() { return localStorage.getItem("fb_id"); }
function getKycStatus() { return localStorage.getItem("fb_kyc_status") || "pending"; }

function isLoggedIn() { return !!getToken(); }

/** WebSocket URL for a shipment room (token and driverId in query — browsers cannot set WS headers). */
function getWsShipmentUrl(shipmentId, driverId) {
    if (!shipmentId || !getToken()) return null;
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    let url = proto + "//" + host + "/ws/shipment/" + encodeURIComponent(shipmentId)
        + "?token=" + encodeURIComponent(getToken());
    if (driverId) {
        url += "&driver_id=" + encodeURIComponent(driverId);
    }
    return url;
}

function logout() {
    ["fb_token", "fb_role", "fb_name", "fb_id", "fb_kyc_status"].forEach(k => localStorage.removeItem(k));
    window.location.href = "/";
}

// ---------- Core fetch wrapper ----------

async function apiFetch(path, options = {}) {
    const headers = {
        "Content-Type": "application/json",
        ...(getToken() ? { "Authorization": `Bearer ${getToken()}` } : {}),
        ...(options.headers || {})
    };

    const res = await fetch(BASE + path, {
        ...options,
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined
    });

    let data;
    try {
        data = await res.json();
    } catch (e) {
        throw new Error(`Server error (${res.status})`);
    }

    if (!res.ok) {
        throw new Error(data.detail || "Something went wrong");
    }

    return data;
}

// ---------- Auth ----------

async function register(name, email, password, role, phone = "") {
    const data = await apiFetch("/api/auth/register", {
        method: "POST",
        body: { name, email, password, role, phone }
    });
    saveAuth(data);
    return data;
}

async function login(email, password) {
    const data = await apiFetch("/api/auth/login", {
        method: "POST",
        body: { email, password }
    });
    saveAuth(data);
    return data;
}



// ---------- Shipments ----------

async function postShipment(payload) {
    return apiFetch("/api/shipments/", { method: "POST", body: payload });
}

async function getOpenShipments() {
    return apiFetch("/api/shipments/open");
}

async function getMyShipments() {
    return apiFetch("/api/shipments/my");
}

async function getShipment(id) {
    return apiFetch(`/api/shipments/${id}`);
}

async function updateShipmentStatus(id, status) {
    return apiFetch(`/api/shipments/${id}/status`, {
        method: "PATCH",
        body: { status }
    });
}

async function updateDestinationStatus(shipmentId, destId, status) {
    return apiFetch(`/api/shipments/${shipmentId}/destinations/${destId}`, {
        method: "PATCH",
        body: { status }
    });
}

async function abandonShipment(shipmentId) {
    return apiFetch(`/api/shipments/${shipmentId}/abandon`, {
        method: "POST"
    });
}

async function sendArrivalAck(shipmentId, destId) {
    return apiFetch(`/api/shipments/${shipmentId}/destinations/${destId}/arrive`, {
        method: "POST"
    });
}

async function approveArrival(shipmentId, destId) {
    return apiFetch(`/api/shipments/${shipmentId}/destinations/${destId}/approve`, {
        method: "POST"
    });
}

async function sendDriverLocation(shipmentId, lat, lng) {
    return apiFetch(`/api/track/${shipmentId}/location`, {
        method: "POST",
        body: { lat, lng }
    });
}

async function getLatestLocation(shipmentId) {
    return apiFetch(`/api/track/${shipmentId}/location`);
}

async function rateDriver(shipmentId, score) {
    return apiFetch(`/api/shipments/${shipmentId}/rate`, {
        method: "POST",
        body: { score }
    });
}

async function getDriverProfile(driverId) {
    return apiFetch(`/api/drivers/${driverId}/profile`);
}

async function getMyDriverProfile() {
    return apiFetch(`/api/drivers/me/profile`);
}

// ---------- Bids ----------

async function placeBid(shipmentId, amount) {
    return apiFetch(`/api/shipments/${shipmentId}/bid`, {
        method: "POST",
        body: { amount }
    });
}

async function getMyBids() {
    return apiFetch(`/api/shipments/my-bids`);
}
async function getBids(shipmentId) {
    return apiFetch(`/api/shipments/${shipmentId}/bids`);
}

async function awardShipment(shipmentId, bidId = null) {
    return apiFetch(`/api/shipments/${shipmentId}/award`, {
        method: "POST",
        body: bidId ? { bid_id: bidId } : {}
    });
}

async function cancelShipment(shipmentId, reason) {
    return apiFetch(`/api/shipments/${shipmentId}/cancel`, {
        method: "POST",
        body: { reason }
    });
}

async function getCancellationRecord(shipmentId) {
    return apiFetch(`/api/shipments/${shipmentId}/cancellation`);
}

// ---------- Destination Change Requests ----------

async function requestDestinationChange(shipmentId, destId, newAddress, newLat, newLng) {
    return apiFetch(`/api/shipments/${shipmentId}/destinations/${destId}/change-request`, {
        method: "POST",
        body: { new_address: newAddress, new_lat: newLat || null, new_lng: newLng || null }
    });
}

async function respondDestinationChange(shipmentId, destId, action) {
    return apiFetch(`/api/shipments/${shipmentId}/destinations/${destId}/change-request/respond`, {
        method: "POST",
        body: { action }
    });
}

async function getPendingChangeRequest(shipmentId, destId) {
    return apiFetch(`/api/shipments/${shipmentId}/destinations/${destId}/change-request`);
}

// ---------- Escrow / Award-and-Pay ----------

async function createAwardIntent(shipmentId, bidId = null) {
    return apiFetch(`/api/payments/${shipmentId}/award-intent`, {
        method: "POST",
        body: bidId ? { bid_id: bidId } : {}
    });
}

async function awardAndPay(shipmentId, paymentIntentId, bidId, cardNumber, expMonth, expYear, cvc) {
    return apiFetch(`/api/payments/${shipmentId}/award-and-pay`, {
        method: "POST",
        body: {
            payment_intent_id: paymentIntentId,
            bid_id: bidId,
            card_number: cardNumber,
            exp_month: expMonth,
            exp_year: expYear,
            cvc: cvc
        }
    });
}

// ---------- POD & Proof Requests ----------

async function uploadDeliveryPhoto(shipmentId, destId, photoFile, notes = "") {
    const formData = new FormData();
    formData.append("photo", photoFile);
    formData.append("notes", notes);
    const res = await fetch(`/api/pod/${shipmentId}/destinations/${destId}/upload`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${getToken()}` },
        body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    return data;
}

async function getShipmentPhotos(shipmentId) {
    return apiFetch(`/api/pod/${shipmentId}/photos`);
}

async function requestProofPhoto(shipmentId) {
    return apiFetch(`/api/pod/${shipmentId}/proof-request`, { method: "POST" });
}

async function getProofRequests(shipmentId) {
    return apiFetch(`/api/pod/${shipmentId}/proof-requests`);
}

async function fulfillProofRequest(shipmentId, requestId, photoFile) {
    const formData = new FormData();
    formData.append("photo", photoFile);
    const res = await fetch(`/api/pod/${shipmentId}/proof-request/${requestId}/fulfill`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${getToken()}` },
        body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    return data;
}

async function acknowledgePodPhoto(shipmentId, podId, action, notes = "") {
    return apiFetch(`/api/pod/${shipmentId}/photos/${podId}/acknowledge`, {
        method: "POST",
        body: { action, notes }
    });
}

async function raiseComplaint(shipmentId, reason, description = "") {
    return apiFetch(`/api/pod/${shipmentId}/complaint`, {
        method: "POST",
        body: { reason, description }
    });
}

async function getComplaints(shipmentId) {
    return apiFetch(`/api/pod/${shipmentId}/complaints`);
}

// ---------- Payments ----------

async function createPaymentIntent(shipmentId) {
    return apiFetch(`/api/payments/${shipmentId}/create-intent`, { method: "POST" });
}

async function confirmPayment(shipmentId, paymentIntentId, cardNumber, expMonth, expYear, cvc) {
    return apiFetch(`/api/payments/${shipmentId}/pay`, {
        method: "POST",
        body: {
            payment_intent_id: paymentIntentId,
            card_number: cardNumber,
            exp_month: expMonth,
            exp_year: expYear,
            cvc: cvc
        }
    });
}

async function getPaymentStatus(shipmentId) {
    return apiFetch(`/api/payments/${shipmentId}/status`);
}

async function requestFreightAdjustment(shipmentId, amount, note = "") {
    return apiFetch(`/api/payments/${shipmentId}/adjustment-request`, {
        method: "POST",
        body: { extra_amount: amount, note }
    });
}

async function acceptFreightAdjustment(shipmentId) {
    return apiFetch(`/api/payments/${shipmentId}/adjustment-accept`, { method: "POST" });
}

async function rejectFreightAdjustment(shipmentId) {
    return apiFetch(`/api/payments/${shipmentId}/adjustment-reject`, { method: "POST" });
}

async function createFreightAdjustmentIntent(shipmentId) {
    return apiFetch(`/api/payments/${shipmentId}/adjustment-intent`, { method: "POST" });
}

async function payFreightAdjustment(shipmentId, paymentIntentId, cardNumber, expMonth, expYear, cvc) {
    return apiFetch(`/api/payments/${shipmentId}/adjustment-pay`, {
        method: "POST",
        body: {
            payment_intent_id: paymentIntentId,
            card_number: cardNumber,
            exp_month: expMonth,
            exp_year: expYear,
            cvc: cvc
        }
    });
}

window.createFreightAdjustmentIntent = createFreightAdjustmentIntent;
window.payFreightAdjustment = payFreightAdjustment;

function fmt(amount) {
    return "₹" + Number(amount).toLocaleString("en-IN");
}

function timeAgo(isoString) {
    const diff = (Date.now() - new Date(isoString)) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
}

function calculateTimeTaken(startIso, endIso) {
    if (!startIso || !endIso) return "N/A";
    const start = new Date(startIso);
    const end = new Date(endIso);
    const diffMs = end - start;
    if (diffMs <= 0) return "0m";
    
    const totalMins = Math.floor(diffMs / 60000);
    const h = Math.floor(totalMins / 60);
    const m = totalMins % 60;
    
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

function statusBadge(status) {
    const map = {
        open: ["🟡", "#f59e0b"],
        assigned: ["🔵", "#3b82f6"],
        in_transit: ["🟠", "#fb923c"],
        delivered: ["🟢", "#22c55e"],
        cancelled: ["🚫", "#ef4444"],
    };
    const [icon, color] = map[status] || ["⚪", "#6b7280"];
    return `<span style="color:${color};font-size:0.8rem;font-family:var(--font-mono);text-transform:uppercase;letter-spacing:0.06em">${icon} ${status.replace("_", " ")}</span>`;
}

// ---------- KYC ----------

async function getKycStatusFromServer() {
    const data = await apiFetch("/api/kyc/status");
    if (data.kyc_status) {
        localStorage.setItem("fb_kyc_status", data.kyc_status);
    }
    return data;
}

async function completeKyc(sessionId, status, licenseNumber = null, aadhaarNumber = null, panNumber = null, kycName = null, kycDob = null, reviewReason = null, reviewDetails = null) {
    const body = { session_id: sessionId, status };
    if (licenseNumber) body.license_number = licenseNumber;
    if (aadhaarNumber) body.aadhaar_number = aadhaarNumber;
    if (panNumber) body.pan_number = panNumber;
    if (kycName) body.kyc_name = kycName;
    if (kycDob) body.kyc_dob = kycDob;
    if (reviewReason) body.review_reason = reviewReason;
    if (reviewDetails) body.review_details = reviewDetails;
    const data = await apiFetch("/api/kyc/complete", { method: "POST", body });
    if (data.kyc_status) {
        localStorage.setItem("fb_kyc_status", data.kyc_status);
    }
    return data;
}

// ---------- Messages ----------

async function getMessages(shipmentId, driverId = null) {
    let url = `/api/shipments/${shipmentId}/messages`;
    if (driverId) {
        url += `?driver_id=${encodeURIComponent(driverId)}`;
    }
    return apiFetch(url);
}

async function sendMessage(shipmentId, body, driverId = null) {
    const payload = { body };
    if (driverId) payload.driver_id = driverId;
    return apiFetch(`/api/shipments/${shipmentId}/messages`, {
        method: "POST",
        body: payload
    });
}

async function getUnreadCount(shipmentId, driverId = null) {
    let url = `/api/shipments/${shipmentId}/messages/unread-count`;
    if (driverId) {
        url += `?driver_id=${encodeURIComponent(driverId)}`;
    }
    return apiFetch(url);
}

async function getMessageNotifications() {
    return apiFetch('/api/shipments/messages/notifications');
}

// ---------- Admin Manual KYC review ----------
async function getAdminKycProfiles() {
    return apiFetch('/api/kyc/admin/profiles');
}

async function adminApproveKyc(userId) {
    return apiFetch(`/api/kyc/admin/approve/${userId}`, { method: 'POST' });
}

async function adminRejectKyc(userId) {
    return apiFetch(`/api/kyc/admin/reject/${userId}`, { method: 'POST' });
}
