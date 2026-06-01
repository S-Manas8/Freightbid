// ============================================================
// FreightBid — Driver Dashboard Logic
// ============================================================

if (!isLoggedIn() || getRole() !== 'driver') {
    window.location.href = '/';
}


document.getElementById('nav-name').textContent = getName();

let selectedLoad = null;
let openLoads    = [];
let driverMessageNotifications = [];
let driverNotificationPoll = null;
let myBidsMap    = {};   // shipment_id → amount

// ── Tab switching ─────────────────────────────────────────────
function switchTab(tab) {
    ['loads','bids','trips','rating','analytics'].forEach(t => {
        document.getElementById('tabn-' + t).classList.toggle('active', t === tab);
        document.getElementById('pane-' + t).classList.toggle('active', t === tab);
    });
    // Refresh data when switching tabs so cancelled/updated items appear immediately
    if (tab === 'loads') loadOpenLoads();
    if (tab === 'bids')  loadMyActiveBids();
    if (tab === 'analytics') loadDriverAnalytics();
    // Invalidate map when trips tab becomes visible
    if (tab === 'trips' && driverMap) setTimeout(() => driverMap.invalidateSize(), 50);
}

// ── Open Loads ────────────────────────────────────────────────
async function loadOpenLoads() {
    const container = document.getElementById('open-loads-list');
    try {
        openLoads = await getOpenShipments();
        document.getElementById('stat-open').textContent = openLoads.length;
        filterOpenLoadsByLocation();
        return;

        if (!openLoads.length) {
            container.innerHTML = '<div class="empty-state"><div class="icon">📭</div><p>No open loads right now.</p></div>';
            return;
        }

        container.innerHTML = openLoads.map(s => {
            const dest = s.destinations && s.destinations.length > 0
                ? (s.destinations.length > 1 ? s.destinations.length + ' Stops' : s.destinations[0].address)
                : (s.drop_address || 'N/A');
            const hasBid = !!myBidsMap[s.id];
            return `<div class="load-card" id="lcard-${s.id}" onclick="selectLoad('${s.id}')">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                    <div style="flex:1;min-width:0;margin-right:10px;">
                        <div style="font-weight:700;font-size:0.88rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${s.pickup_address}</div>
                        <div style="font-size:0.78rem;color:var(--muted);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">→ ${dest}</div>
                    </div>
                    ${hasBid ? `<span class="already-bid-badge">✓ ${fmt(myBidsMap[s.id])}</span>` : ''}
                </div>
                <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                    <span style="font-size:0.75rem;color:var(--muted);">📦 ${s.goods_desc}</span>
                    <span style="font-size:0.75rem;color:var(--muted);">⚖️ ${s.weight_kg} kg</span>
                    <span style="font-size:0.75rem;color:var(--muted);">🚛 ${s.vehicle_type}</span>
                    ${s.est_time_hours ? `<span style="font-size:0.75rem;color:var(--muted);">⏱ ${s.est_time_hours}h</span>` : ''}
                    ${s.bid_count > 0 ? `<span style="font-size:0.72rem;font-family:var(--font-mono);color:var(--accent);background:rgba(245,158,11,0.1);padding:1px 7px;border-radius:10px;">${s.bid_count} bid${s.bid_count!==1?'s':''}</span>` : ''}
                    <span style="font-size:0.7rem;color:var(--muted);margin-left:auto;">${timeAgo(s.created_at)}</span>
                </div>
                ${s.deadline ? `<div style="font-size:0.7rem;color:#f59e0b;margin-top:5px;font-family:var(--font-mono);">⏰ Deadline: ${new Date(s.deadline).toLocaleString()}</div>` : ''}
            </div>`;
        }).join('');
    } catch (err) {
        container.innerHTML = `<div class="alert alert-error">${err.message}</div>`;
    }
}

// ── Select Load → Bid Panel ───────────────────────────────────
function getLoadLocationText(load) {
    const destinations = (load.destinations || []).map(d => d.address).join(' ');
    return [
        load.pickup_address,
        load.drop_address,
        destinations
    ].filter(Boolean).join(' ').toLowerCase();
}

function filterOpenLoadsByLocation() {
    const searchInput = document.getElementById('load-location-search');
    const query = (searchInput?.value || '').trim().toLowerCase();
    const loads = query
        ? openLoads.filter(load => getLoadLocationText(load).includes(query))
        : openLoads;

    renderOpenLoads(loads, query);
}

function clearLoadLocationSearch() {
    const searchInput = document.getElementById('load-location-search');
    if (searchInput) searchInput.value = '';
    filterOpenLoadsByLocation();
}

function renderOpenLoads(loads, query = '') {
    const container = document.getElementById('open-loads-list');
    const countEl = document.getElementById('load-search-count');

    if (countEl) {
        countEl.textContent = query
            ? `${loads.length} of ${openLoads.length} loads match "${query}"`
            : `${openLoads.length} open load${openLoads.length !== 1 ? 's' : ''}`;
    }

    if (!openLoads.length) {
        container.innerHTML = '<div class="empty-state"><div class="icon">ðŸ“­</div><p>No open loads right now.</p></div>';
        return;
    }

    if (!loads.length) {
        container.innerHTML = '<div class="empty-state"><div class="icon">ðŸ”</div><p>No loads found for this location.</p></div>';
        return;
    }

    container.innerHTML = loads.map(s => {
        const dest = s.destinations && s.destinations.length > 0
            ? (s.destinations.length > 1 ? s.destinations.length + ' Stops' : s.destinations[0].address)
            : (s.drop_address || 'N/A');
        const hasBid = !!myBidsMap[s.id];
        return `<div class="load-card" id="lcard-${s.id}" onclick="selectLoad('${s.id}')">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                <div style="flex:1;min-width:0;margin-right:10px;">
                    <div style="font-weight:700;font-size:0.88rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${s.pickup_address}</div>
                    <div style="font-size:0.78rem;color:var(--muted);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">â†’ ${dest}</div>
                </div>
                ${hasBid ? `<span class="already-bid-badge">âœ“ ${fmt(myBidsMap[s.id])}</span>` : ''}
            </div>
            <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                <span style="font-size:0.75rem;color:var(--muted);">ðŸ“¦ ${s.goods_desc}</span>
                <span style="font-size:0.75rem;color:var(--muted);">âš–ï¸ ${s.weight_kg} kg</span>
                <span style="font-size:0.75rem;color:var(--muted);">ðŸš› ${s.vehicle_type}</span>
                ${s.est_time_hours ? `<span style="font-size:0.75rem;color:var(--muted);">â± ${s.est_time_hours}h</span>` : ''}
                ${s.bid_count > 0 ? `<span style="font-size:0.72rem;font-family:var(--font-mono);color:var(--accent);background:rgba(245,158,11,0.1);padding:1px 7px;border-radius:10px;">${s.bid_count} bid${s.bid_count!==1?'s':''}</span>` : ''}
                <span style="font-size:0.7rem;color:var(--muted);margin-left:auto;">${timeAgo(s.created_at)}</span>
            </div>
            ${s.deadline ? `<div style="font-size:0.7rem;color:#f59e0b;margin-top:5px;font-family:var(--font-mono);">â° Deadline: ${new Date(s.deadline).toLocaleString()}</div>` : ''}
        </div>`;
    }).join('');
}

async function selectLoad(id) {
    document.querySelectorAll('.load-card').forEach(c => c.classList.remove('selected'));
    document.getElementById(`lcard-${id}`)?.classList.add('selected');

    selectedLoad = openLoads.find(x => x.id === id);
    if (!selectedLoad) return;

    document.getElementById('bid-placeholder').style.display = 'none';
    document.getElementById('bid-panel').style.display = 'block';
    document.getElementById('bid-alert').innerHTML = '';
    document.getElementById('bid-panel-title').textContent = selectedLoad.goods_desc;
    document.getElementById('bid-panel-status').innerHTML = statusBadge(selectedLoad.status);

    const destDisplay = selectedLoad.destinations && selectedLoad.destinations.length > 0
        ? selectedLoad.destinations.map(d => `<div style="font-size:0.85rem;margin-left:8px;">📍 ${d.address}</div>`).join('')
        : `<span class="route-to">${selectedLoad.drop_address || 'N/A'}</span>`;

    document.getElementById('bid-panel-route').innerHTML =
        `<div class="route-display" style="flex-direction:column;align-items:flex-start;gap:6px;">
            <div style="display:flex;align-items:center;gap:8px;">
                <span class="route-from">${selectedLoad.pickup_address}</span>
                <span class="route-arrow">→</span>
            </div>
            ${destDisplay}
        </div>`;

    document.getElementById('bid-panel-meta').innerHTML =
        `<div class="meta-item"><span class="meta-label">Weight</span><span class="meta-value">${selectedLoad.weight_kg} kg</span></div>
         <div class="meta-item"><span class="meta-label">Vehicle</span><span class="meta-value">${selectedLoad.vehicle_type}</span></div>
         ${selectedLoad.est_time_hours ? `<div class="meta-item"><span class="meta-label">Est. Time</span><span class="meta-value">${selectedLoad.est_time_hours}h</span></div>` : ''}
         ${selectedLoad.bid_count > 0 ? `<div class="meta-item"><span class="meta-label">Bids So Far</span><span class="meta-value accent">${selectedLoad.bid_count}</span></div>` : ''}
         <div class="meta-item"><span class="meta-label">Posted</span><span class="meta-value" style="font-size:0.85rem">${timeAgo(selectedLoad.created_at)}</span></div>`;

    const myBid = myBidsMap[id];
    if (myBid) {
        document.getElementById('bid-panel-myBid').innerHTML = `<div class="alert alert-success">✓ You bid ${fmt(myBid)} — you can lower it below.</div>`;
        document.getElementById('bid-amount').value = myBid;
        document.getElementById('bid-btn').textContent = 'Update Bid';
    } else {
        document.getElementById('bid-panel-myBid').innerHTML = '';
        document.getElementById('bid-amount').value = '';
        document.getElementById('bid-btn').textContent = 'Place Bid';
    }
}

// ── Bid Placement ─────────────────────────────────────────────
function doPlaceBid() {
    const amount = document.getElementById('bid-amount').value;
    if (!selectedLoad) return;
    if (!amount || Number(amount) <= 0) {
        document.getElementById('bid-alert').innerHTML = '<div class="alert alert-error">Enter a valid bid amount.</div>';
        return;
    }
    if (myBidsMap[selectedLoad.id]) {
        submitBid(Number(amount));
    } else {
        showBidAssurance(selectedLoad, Number(amount));
    }
}

function showBidAssurance(load, amount) {
    const existing = document.getElementById('bid-assurance-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'bid-assurance-modal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.65);z-index:1000;display:flex;align-items:center;justify-content:center;padding:24px;';
    modal.innerHTML = `
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:32px;max-width:440px;width:100%;">
            <div style="text-align:center;margin-bottom:20px;">
                <div style="font-size:2.5rem;margin-bottom:8px;">🤝</div>
                <div style="font-size:1.1rem;font-weight:700;margin-bottom:4px;">Delivery Assurance</div>
                <div style="font-size:0.82rem;color:var(--muted);">Read and confirm before placing your bid</div>
            </div>
            <div style="background:var(--surface2);border-radius:8px;padding:14px;margin-bottom:20px;border-left:3px solid var(--accent);">
                <div style="font-size:0.75rem;color:var(--muted);font-family:var(--font-mono);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Your Bid</div>
                <div style="font-size:1.1rem;font-weight:700;color:var(--accent);">${fmt(amount)}</div>
                <div style="font-size:0.82rem;color:var(--muted);margin-top:4px;">${load.goods_desc} · ${load.pickup_address}</div>
            </div>
            <div style="font-size:0.85rem;margin-bottom:24px;">
                By placing this bid, I confirm that:
                <ul style="margin:10px 0 0 16px;color:var(--muted);font-size:0.82rem;line-height:1.7;">
                    <li>I will deliver all goods safely and on time if awarded</li>
                    <li>I will follow the route stops in the given order</li>
                    <li>I will keep the shipper updated on my progress</li>
                    <li>I take full responsibility for the goods during transit</li>
                </ul>
            </div>
            <div style="display:flex;gap:12px;">
                <button onclick="document.getElementById('bid-assurance-modal').remove()" class="btn btn-outline" style="flex:1;">✕ Cancel</button>
                <button onclick="document.getElementById('bid-assurance-modal').remove(); submitBid(${amount})" class="btn btn-primary" style="flex:2;font-weight:700;">✅ Agree &amp; Place Bid</button>
            </div>
        </div>`;
    document.body.appendChild(modal);
}

async function submitBid(amount) {
    const alertEl = document.getElementById('bid-alert');
    const btn     = document.getElementById('bid-btn');
    btn.disabled  = true;
    btn.textContent = 'Submitting...';
    try {
        const result = await placeBid(selectedLoad.id, amount);
        myBidsMap[selectedLoad.id] = amount;
        alertEl.innerHTML = `<div class="alert alert-success">✓ ${result.message}</div>`;
        document.getElementById('bid-btn').textContent = 'Update Bid';
        document.getElementById('bid-panel-myBid').innerHTML = `<div class="alert alert-success">✓ You bid ${fmt(amount)} — you can lower it below.</div>`;
        loadOpenLoads();
        loadMyActiveBids();
    } catch (err) {
        alertEl.innerHTML = `<div class="alert alert-error">${err.message}</div>`;
    } finally {
        btn.disabled = false;
    }
}

// ── My Active Bids ────────────────────────────────────────────
async function loadMyActiveBids() {
    const container = document.getElementById('my-bids-list');
    if (!container) return;
    try {
        const bids = await getMyBids();
        const activeBids = bids.filter(b => b.shipment_status === 'open');

        myBidsMap = {};
        activeBids.forEach(b => { myBidsMap[b.shipment_id] = b.my_amount; });

        document.getElementById('stat-mybids').textContent = activeBids.length;

        // Update bids tab badge
        const bidBadge = document.getElementById('badge-bids');
        if (activeBids.length > 0) { bidBadge.textContent = activeBids.length; bidBadge.style.display = ''; }
        else bidBadge.style.display = 'none';

        if (!activeBids.length) {
            container.innerHTML = '<div class="empty-state" style="padding:20px 0;"><div class="icon">🎯</div><p style="font-size:0.85rem;">No active bids right now.</p></div>';
            return;
        }

        const statusMap = {
            open:       { color: '#f59e0b', label: '⏳ Awaiting Award' },
            assigned:   { color: '#3b82f6', label: null },
            in_transit: { color: '#fb923c', label: null },
            delivered:  { color: '#22c55e', label: null },
        };

        container.innerHTML = activeBids.map(b => {
            let label, color;
            if (b.shipment_status === 'open') {
                label = '⏳ Awaiting Award'; color = '#f59e0b';
            } else if (b.shipment_status === 'cancelled') {
                label = '🚫 Cancelled by Shipper'; color = '#6b7280';
            } else if (b.was_abandoned) {
                label = '⚠️ Abandoned'; color = '#f59e0b';
            } else if (b.is_winner) {
                const lmap = { assigned: '🏆 You Won!', in_transit: '🚚 In Transit', delivered: '✅ Delivered' };
                label = lmap[b.shipment_status] || b.shipment_status; color = '#22c55e';
            } else {
                label = '❌ Not Selected'; color = '#6b7280';
            }

            const border = b.shipment_status === 'cancelled' ? 'rgba(100,100,100,0.25)'
                : b.was_abandoned ? '#f59e0b'
                : b.is_winner ? 'var(--green)'
                : b.shipment_status === 'open' && b.is_lowest ? 'var(--green)'
                : 'var(--border)';

            const isCancelled = b.shipment_status === 'cancelled';

            return `<div style="padding:14px;border:1px solid var(--border);border-radius:8px;margin-bottom:10px;border-left:3px solid ${border};">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                    <div style="font-weight:700;font-size:0.88rem;flex:1;margin-right:8px;">${b.pickup_address} → ${b.drop_address || 'N/A'}</div>
                    <span style="font-size:0.72rem;color:${color};font-family:var(--font-mono);white-space:nowrap;font-weight:600;">${label}</span>
                </div>
                <div style="font-size:0.78rem;color:var(--muted);margin-bottom:10px;">${b.goods_desc} · ${b.weight_kg} kg · ${b.vehicle_type}</div>
                ${isCancelled ? `
                <div style="font-size:0.75rem;color:#ef4444;padding:8px 12px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);border-radius:6px;font-weight:500;">
                    ${b.driver_fee ? `This load was cancelled by the shipper. According to distance and bidded amount, you got <strong>${fmt(b.driver_fee)}</strong> as compensation.` : 'This load was cancelled by the shipper. Your bid has been voided.'}
                </div>` : `
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <div style="font-size:0.68rem;color:var(--muted);font-family:var(--font-mono);text-transform:uppercase;letter-spacing:0.05em;">Your Bid</div>
                        <div style="font-size:1.05rem;font-weight:700;color:var(--accent);">${fmt(b.my_amount)}</div>
                    </div>
                    ${b.shipment_status === 'open' ? `
                    <div style="text-align:right;">
                        <div style="font-size:0.68rem;color:var(--muted);font-family:var(--font-mono);text-transform:uppercase;letter-spacing:0.05em;">${b.total_bids} bid${b.total_bids !== 1 ? 's' : ''}</div>
                        <div style="font-size:0.82rem;font-weight:600;color:${b.is_lowest ? 'var(--green)' : 'var(--muted)'};">${b.is_lowest ? "🏆 You're lowest!" : 'Lowest: ' + fmt(b.lowest_amount)}</div>
                    </div>` : b.winning_bid_amount ? `
                    <div style="text-align:right;">
                        <div style="font-size:0.68rem;color:var(--muted);font-family:var(--font-mono);text-transform:uppercase;letter-spacing:0.05em;">Awarded At</div>
                        <div style="font-size:0.82rem;font-weight:600;">${fmt(b.winning_bid_amount)}</div>
                    </div>` : ''}
                </div>`}
                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;padding-top:8px;border-top:1px solid rgba(148,163,184,0.05);">
                    <div style="font-size:0.7rem;color:var(--muted);font-family:var(--font-mono);">Placed ${timeAgo(b.placed_at)}</div>
                    ${!isCancelled ? `<span style="font-size:0.72rem;color:var(--muted);">Open shipment to chat</span>` : ''}
                </div>
            </div>`;
        }).join('');
    } catch (err) {
        container.innerHTML = `<div class="alert alert-error">${err.message}</div>`;
    }
}

// ── My Trips ──────────────────────────────────────────────────
async function loadMyTrips() {
    const container = document.getElementById('my-trips-list');
    try {
        const trips = (await getMyShipments()).sort((a, b) =>
            new Date(b.created_at || 0) - new Date(a.created_at || 0)
        );
        const active    = trips.filter(t => ['assigned','in_transit'].includes(t.status)).length;
        const completed = trips.filter(t => t.status === 'delivered').length;

        document.getElementById('stat-active').textContent = active;
        document.getElementById('stat-done').textContent   = completed;

        // Update trips tab badge
        const tripBadge = document.getElementById('badge-trips');
        if (active > 0) { tripBadge.textContent = active; tripBadge.style.display = ''; }
        else tripBadge.style.display = 'none';

        if (!trips.length) {
            container.innerHTML = '<div class="empty-state"><div class="icon">🏁</div><p>No assigned trips yet.</p></div>';
            document.getElementById('trip-map').style.display = 'none';
            stopTracking();
            return;
        }

        const activeTrip = trips.find(t => t.status === 'in_transit');
        if (activeTrip) { plotTripOnMap(activeTrip); startTracking(activeTrip.id); startProofRequestPolling(activeTrip.id); }
        else {
            const assignedTrip = trips.find(t => t.status === 'assigned');
            if (assignedTrip) plotTripOnMap(assignedTrip);
            else document.getElementById('trip-map').style.display = 'none';
            stopTracking();
            stopProofRequestPolling();
        }

        // Remember open accordion sections
        const openSections = new Set(
            [...document.querySelectorAll('[id^="photo-section-"]')]
                .filter(el => el.style.display !== 'none')
                .map(el => el.id)
        );
        // Remember open trip accordions
        const openTrips = new Set(
            [...document.querySelectorAll('[id^="trip-body-"]')]
                .filter(el => el.style.display !== 'none')
                .map(el => el.id.replace('trip-body-', ''))
        );

        // Fetch proof requests for in-transit trips
        const proofMap = {};
        for (const t of trips.filter(t => t.status === 'in_transit')) {
            try {
                const reqs = await getProofRequests(t.id);
                const pending = reqs.find(r => r.status === 'pending');
                proofMap[t.id] = pending ? pending.request_id : null;
            } catch (e) { proofMap[t.id] = null; }
        }

        // Fetch photos for in_transit and delivered trips
        const photosMap = {};
        for (const t of trips.filter(t => ['in_transit','delivered'].includes(t.status))) {
            try { photosMap[t.id] = await getShipmentPhotos(t.id); }
            catch (e) { photosMap[t.id] = []; }
        }

        // Fetch payment status
        const paymentMap = {};
        for (const t of trips.filter(t => ['assigned','in_transit','delivered'].includes(t.status))) {
            try { paymentMap[t.id] = await getPaymentStatus(t.id); }
            catch (e) {
                console.warn('Payment fetch failed for', t.id, e.message);
                paymentMap[t.id] = null;
            }
        }

        // Fetch cancellation records for cancelled trips
        const cancelMap = {};
        for (const t of trips.filter(t => t.status === 'cancelled')) {
            try { cancelMap[t.id] = await getCancellationRecord(t.id); }
            catch (e) { cancelMap[t.id] = null; }
        }

        // Determine which trips should be auto-expanded
        // Active trips always open; delivered trips open only if previously open
        const shouldOpen = id => {
            const t = trips.find(x => x.id === id);
            return t && ['assigned','in_transit'].includes(t.status) || openTrips.has(id);
        };

        container.innerHTML = trips.map(t => {
            const dest = t.destinations && t.destinations.length > 0
                ? (t.destinations.length > 1 ? t.destinations.length + ' Stops' : t.destinations[0].address)
                : (t.drop_address || 'N/A');

            const pillClass = { assigned:'pill-assigned', in_transit:'pill-transit', delivered:'pill-delivered', cancelled:'pill-cancelled' };
            const pillIcon  = { assigned:'🔵', in_transit:'🟠', delivered:'🟢', cancelled:'🚫' };
            const isOpen    = shouldOpen(t.id);

            // Payment badge for header
            const pay = paymentMap[t.id];
            let payBadge = '';
            if (pay && pay.status === 'released_to_driver') {
                payBadge = `<span style="font-size:0.65rem;font-family:var(--font-mono);color:var(--green);background:rgba(16,185,129,0.15);padding:1px 7px;border-radius:10px;margin-left:6px;">✅ Paid</span>`;
            } else if (pay && (pay.status === 'escrow_held' || pay.status === 'succeeded')) {
                payBadge = `<span style="font-size:0.65rem;font-family:var(--font-mono);color:#60a5fa;background:rgba(59,130,246,0.15);padding:1px 7px;border-radius:10px;margin-left:6px;">🔒 Secured</span>`;
            } else if (pay && pay.status === 'cancelled_with_fee') {
                payBadge = `<span style="font-size:0.65rem;font-family:var(--font-mono);color:#ef4444;background:rgba(239,68,68,0.15);padding:1px 7px;border-radius:10px;margin-left:6px;">🚫 Compensated</span>`;
            } else if (t.status === 'delivered' && (!pay || pay.status === 'not_initiated')) {
                payBadge = `<span style="font-size:0.65rem;font-family:var(--font-mono);color:#f59e0b;background:rgba(245,158,11,0.15);padding:1px 7px;border-radius:10px;margin-left:6px;">⏳ Unpaid</span>`;
            }

            return `
            <div class="trip-card" id="trip-card-${t.id}">
                <!-- Accordion header -->
                <div class="trip-card-header" onclick="toggleTripCard('${t.id}')">
                    <div style="flex:1;min-width:0;">
                        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
                            <span class="pill ${pillClass[t.status] || 'pill-assigned'}">${pillIcon[t.status] || '⚪'} ${t.status.replace('_',' ')}</span>
                            ${t.winning_bid_amount ? `<span style="font-family:var(--font-cond);font-weight:700;font-size:0.95rem;color:var(--accent);">${fmt(t.winning_bid_amount)}</span>` : ''}
                            ${payBadge}
                        </div>
                        <div style="font-weight:700;font-size:0.88rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${t.pickup_address} → ${dest}</div>
                        <div style="font-size:0.75rem;color:var(--muted);margin-top:2px;">📦 ${t.goods_desc} · ⚖️ ${t.weight_kg} kg · 🚛 ${t.vehicle_type}</div>
                    </div>
                    ${['assigned','in_transit'].includes(t.status) ? `
                    <button class="btn btn-outline btn-sm"
                            title="Open chat"
                            onclick="event.stopPropagation();openDriverChatWidget('${t.id}', 'Chat: ${t.pickup_address.split(',')[0]} → ${t.destinations && t.destinations.length > 0 ? t.destinations[0].address : t.drop_address || 'Stop'}')"
                            style="display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;padding:0;border-radius:8px;margin-left:10px;flex-shrink:0;">
                        💬
                    </button>` : ''}
                    <span id="trip-arrow-${t.id}" style="font-size:0.8rem;color:var(--muted);margin-left:12px;flex-shrink:0;transition:transform 0.2s;${isOpen ? 'transform:rotate(180deg)' : ''}">▼</span>
                </div>

                <!-- Accordion body -->
                <div id="trip-body-${t.id}" style="${isOpen ? '' : 'display:none;'}">
                    <!-- Meta strip -->
                    <div style="padding:10px 16px;background:rgba(0,0,0,0.15);border-bottom:1px solid var(--border);display:flex;gap:16px;flex-wrap:wrap;">
                        ${t.est_time_hours ? `<span style="font-size:0.75rem;color:var(--muted);">⏱ Est. ${t.est_time_hours}h</span>` : ''}
                        ${t.status === 'delivered' && t.started_at && t.delivered_at ? `<span style="font-size:0.75rem;color:var(--green);">✅ Took ${calculateTimeTaken(t.started_at, t.delivered_at)}</span>` : ''}
                        ${t.deadline ? `<span style="font-size:0.75rem;color:#f59e0b;">⏰ ${new Date(t.deadline).toLocaleDateString()}</span>` : ''}
                        <span style="font-size:0.72rem;color:var(--muted);margin-left:auto;">${timeAgo(t.created_at)}</span>
                    </div>

                    <div style="padding:14px 16px;">
                        ${renderPaymentSection(t, paymentMap[t.id], cancelMap[t.id])}
                        ${renderProofRequestInline(t, proofMap[t.id])}
                        ${renderTripButtons(t)}
                        ${renderDriverPhotoHistory(t, photosMap[t.id] || [])}
                    </div>
                </div>
            </div>`;
        }).join('');

        // Restore open photo sections
        openSections.forEach(sectionId => {
            const body  = document.getElementById(sectionId);
            const arrow = document.getElementById(sectionId + '-arrow');
            if (body)  body.style.display  = 'block';
            if (arrow) arrow.style.transform = 'rotate(180deg)';
        });

    } catch (err) {
        container.innerHTML = `<div class="alert alert-error">${err.message}</div>`;
    }
}

function toggleTripCard(id) {
    const body  = document.getElementById('trip-body-' + id);
    const arrow = document.getElementById('trip-arrow-' + id);
    if (!body) return;
    const isOpen = body.style.display !== 'none';
    body.style.display    = isOpen ? 'none' : '';
    arrow.style.transform = isOpen ? '' : 'rotate(180deg)';
}

// ── Payment section inside trip card (driver view) ───────────
function renderPaymentSection(trip, pay, cancelRec) {
    // Handle cancelled trips — show cancellation compensation
    if (trip.status === 'cancelled') {
        if (!cancelRec) {
            // No cancellation record — either cancelled before record system,
            // or cancelled before driver was assigned
            // Check if there's a payment with cancelled_with_fee status
            if (pay && pay.status === 'cancelled_with_fee' && pay.amount) {
                return `
                    <div style="margin-top:12px;padding:12px 14px;
                                background:rgba(239,68,68,0.08);
                                border:1px solid rgba(239,68,68,0.25);
                                border-radius:8px;">
                        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
                            <div style="display:flex;align-items:center;gap:8px;">
                                <span style="font-size:1.2rem;">🚫</span>
                                <div style="font-weight:700;font-size:0.9rem;color:#ef4444;">Trip Cancelled by Shipper</div>
                            </div>
                        </div>
                        <div style="font-size:0.75rem;color:var(--muted);">
                            Shipper cancelled this trip. Compensation will be processed by FreightBid.
                        </div>
                    </div>`;
            }
            return `
                <div style="margin-top:12px;padding:12px 14px;
                            background:rgba(100,100,100,0.08);
                            border:1px solid rgba(100,100,100,0.2);
                            border-radius:8px;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-size:1.1rem;">🚫</span>
                        <div style="font-weight:700;font-size:0.88rem;color:#94a3b8;">Trip Cancelled by Shipper</div>
                    </div>
                    <div style="font-size:0.75rem;color:var(--muted);margin-top:4px;">
                        Cancelled before driver was assigned. No compensation applicable.
                    </div>
                </div>`;
        }

        const cancelDate = new Date(cancelRec.cancelled_at).toLocaleDateString('en-IN', {
            day:'numeric', month:'short', year:'numeric'
        });
        const cancelTime = new Date(cancelRec.cancelled_at).toLocaleTimeString('en-IN', {
            hour:'2-digit', minute:'2-digit'
        });

        // Build detail line based on scenario
        let detailLine = '';
        if (cancelRec.scenario === 'assigned_penalty') {
            if (cancelRec.km_travelled > 0 && cancelRec.total_route_km > 0) {
                detailLine = `You travelled ${cancelRec.km_travelled} km of ${cancelRec.total_route_km} km total route`;
            } else {
                detailLine = 'Compensation based on trip fare';
            }
        } else if (cancelRec.scenario === 'in_transit_penalty') {
            detailLine = `${cancelRec.completed_stops || 0} of ${cancelRec.total_stops || 0} stops completed`;
        }

        const hasCompensation = cancelRec.driver_fee > 0;

        return `
            <div style="margin-top:12px;padding:12px 14px;
                        background:${hasCompensation ? 'rgba(239,68,68,0.08)' : 'rgba(100,100,100,0.08)'};
                        border:1px solid ${hasCompensation ? 'rgba(239,68,68,0.25)' : 'rgba(100,100,100,0.2)'};
                        border-radius:8px;">
                <!-- Header -->
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-size:1.2rem;">🚫</span>
                        <div style="font-weight:700;font-size:0.9rem;color:#ef4444;">Trip Cancelled by Shipper</div>
                    </div>
                    ${hasCompensation ? `
                    <div style="font-family:var(--font-cond);font-size:1.1rem;font-weight:700;color:#ef4444;">
                        ${fmt(cancelRec.driver_fee)}
                    </div>` : ''}
                </div>

                <!-- Reason -->
                <div style="font-size:0.75rem;color:var(--muted);margin-bottom:8px;">
                    Reason: <strong style="color:var(--text);">${cancelRec.reason}</strong>
                </div>

                ${hasCompensation ? `
                <!-- Compensation breakdown -->
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
                    <div style="background:rgba(0,0,0,0.2);border-radius:6px;padding:7px 10px;">
                        <div style="color:var(--muted);font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:2px;">Your Compensation</div>
                        <div style="font-weight:700;font-size:0.95rem;color:#ef4444;">${fmt(cancelRec.driver_fee)}</div>
                        <div style="font-size:0.68rem;color:var(--muted);margin-top:2px;">${detailLine}</div>
                    </div>
                    <div style="background:rgba(0,0,0,0.2);border-radius:6px;padding:7px 10px;">
                        <div style="color:var(--muted);font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:2px;">Original Bid</div>
                        <div style="font-weight:700;font-size:0.95rem;color:var(--muted);">${fmt(cancelRec.trip_amount)}</div>
                    </div>
                </div>
                <div style="font-size:0.7rem;color:var(--muted);">
                    Cancelled on ${cancelDate} at ${cancelTime}
                </div>` : `
                <div style="font-size:0.75rem;color:var(--muted);">
                    No compensation — cancelled before trip started.
                    Cancelled on ${cancelDate} at ${cancelTime}
                </div>`}
            </div>`;
    }

    // Only show for trips that have been awarded
    if (!['assigned', 'in_transit', 'delivered'].includes(trip.status)) return '';
    if (!trip.winning_bid_amount) return '';

    // No payment record yet
    if (!pay || pay.status === 'not_initiated') {
        // Only show "awaiting payment" for delivered trips — during transit it's expected
        if (trip.status !== 'delivered') return '';
        return `
            <div style="margin-top:12px;padding:12px 14px;
                        background:rgba(245,158,11,0.08);
                        border:1px solid rgba(245,158,11,0.25);
                        border-radius:8px;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                    <span style="font-size:1.1rem;">⏳</span>
                    <div style="font-weight:700;font-size:0.88rem;color:#f59e0b;">Payment Not Received Yet</div>
                </div>
                <div style="font-size:0.78rem;color:var(--muted);">
                    Trip completed · Awaiting payment of
                    <strong style="color:var(--accent);">${fmt(trip.winning_bid_amount)}</strong>
                    from shipper
                </div>
            </div>`;
    }

    if (pay.status === 'pending') {
        return `
            <div style="margin-top:12px;padding:12px 14px;
                        background:rgba(245,158,11,0.08);
                        border:1px solid rgba(245,158,11,0.25);
                        border-radius:8px;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                    <span style="font-size:1.1rem;">⏳</span>
                    <div style="font-weight:700;font-size:0.88rem;color:#f59e0b;">Payment Pending</div>
                </div>
                <div style="font-size:0.78rem;color:var(--muted);">
                    <strong style="color:var(--accent);">${fmt(pay.amount)}</strong>
                    — Shipper has initiated payment, processing...
                </div>
                ${pay.shipper_name ? `
                <div style="margin-top:6px;font-size:0.75rem;color:var(--muted);">
                    👤 Shipper: <strong style="color:var(--text);">${pay.shipper_name}</strong>
                    ${pay.shipper_phone ? `· <a href="tel:${pay.shipper_phone}" style="color:var(--accent);">${pay.shipper_phone}</a>` : ''}
                </div>` : ''}
            </div>`;
    }

    if (pay.status === 'succeeded' || pay.status === 'escrow_held' || pay.status === 'released_to_driver') {
        const paidDate = pay.paid_at
            ? new Date(pay.paid_at).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' })
            : '—';
        const paidTime = pay.paid_at
            ? new Date(pay.paid_at).toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' })
            : '';

        // succeeded and escrow_held = shipper paid, funds held, driver hasn't delivered yet
        // released_to_driver = delivery confirmed, driver gets the money
        const isReleased = pay.status === 'released_to_driver';

        const titleStr  = isReleased ? "Payment Released to You"       : "Payment Secured by FreightBid";
        const iconStr   = isReleased ? "✅"                             : "🔒";
        const noteStr   = isReleased ? "Delivery confirmed · Funds released to your account"
                                     : "Shipper paid · Held by FreightBid · Released after delivery";
        const bgColor   = isReleased ? "rgba(16,185,129,0.08)"         : "rgba(59,130,246,0.08)";
        const bdColor   = isReleased ? "rgba(16,185,129,0.25)"         : "rgba(59,130,246,0.3)";
        const txtColor  = isReleased ? "var(--green)"                  : "#60a5fa";

        return `
            <div style="margin-top:12px;padding:12px 14px;
                        background:${bgColor};
                        border:1px solid ${bdColor};
                        border-radius:8px;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-size:1.2rem;">${iconStr}</span>
                        <div style="font-weight:700;font-size:0.9rem;color:${txtColor};">${titleStr}</div>
                    </div>
                    <div style="font-family:var(--font-cond);font-size:1.1rem;font-weight:700;color:${txtColor};">
                        ${fmt(pay.amount)}
                    </div>
                </div>
                <div style="font-size:0.72rem;color:var(--muted);margin-bottom:10px;">${noteStr}</div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:0.75rem;">
                    <div style="background:rgba(0,0,0,0.2);border-radius:6px;padding:7px 10px;">
                        <div style="color:var(--muted);margin-bottom:2px;text-transform:uppercase;font-size:0.65rem;letter-spacing:0.05em;">Paid On</div>
                        <div style="font-weight:600;">${paidDate}</div>
                        <div style="color:var(--muted);font-size:0.7rem;">${paidTime}</div>
                    </div>
                    <div style="background:rgba(0,0,0,0.2);border-radius:6px;padding:7px 10px;">
                        <div style="color:var(--muted);margin-bottom:2px;text-transform:uppercase;font-size:0.65rem;letter-spacing:0.05em;">Payment Method</div>
                        <div style="font-weight:600;text-transform:capitalize;">
                            ${pay.card_brand || 'Card'}
                            ${pay.card_last4 ? `<span style="font-family:var(--font-mono);"> ****${pay.card_last4}</span>` : ''}
                        </div>
                    </div>
                    ${pay.shipper_name ? `
                    <div style="background:rgba(0,0,0,0.2);border-radius:6px;padding:7px 10px;">
                        <div style="color:var(--muted);margin-bottom:2px;text-transform:uppercase;font-size:0.65rem;letter-spacing:0.05em;">Paid By (Shipper)</div>
                        <div style="font-weight:600;">${pay.shipper_name}</div>
                        ${pay.shipper_phone ? `<div style="color:var(--muted);font-size:0.7rem;">${pay.shipper_phone}</div>` : ''}
                    </div>` : ''}
                    ${pay.charge_id ? `
                    <div style="background:rgba(0,0,0,0.2);border-radius:6px;padding:7px 10px;">
                        <div style="color:var(--muted);margin-bottom:2px;text-transform:uppercase;font-size:0.65rem;letter-spacing:0.05em;">Transaction ID</div>
                        <div style="font-family:var(--font-mono);font-size:0.68rem;word-break:break-all;color:var(--muted);">${pay.charge_id}</div>
                    </div>` : ''}
                </div>
            </div>`;
    }

    if (pay.status === 'failed') {
        return `
            <div style="margin-top:12px;padding:12px 14px;
                        background:rgba(239,68,68,0.08);
                        border:1px solid rgba(239,68,68,0.25);
                        border-radius:8px;">
                <div style="display:flex;align-items:center;gap:8px;">
                    <span style="font-size:1.1rem;">❌</span>
                    <div>
                        <div style="font-weight:700;font-size:0.88rem;color:#ef4444;">Payment Failed</div>
                        <div style="font-size:0.75rem;color:var(--muted);margin-top:2px;">
                            Shipper's payment attempt failed. Amount: <strong>${fmt(pay.amount)}</strong>
                        </div>
                    </div>
                </div>
            </div>`;
    }

    if (pay.status === 'cancelled_with_fee') {
        return `
            <div style="margin-top:12px;padding:12px 14px;
                        background:rgba(239,68,68,0.08);
                        border:1px solid rgba(239,68,68,0.25);
                        border-radius:8px;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-size:1.2rem;">🚫</span>
                        <div style="font-weight:700;font-size:0.9rem;color:#ef4444;">Trip Cancelled by Shipper</div>
                    </div>
                    <div style="font-family:var(--font-cond);font-size:1.1rem;font-weight:700;color:#ef4444;">
                        ${fmt(pay.driver_fee || 0)}
                    </div>
                </div>
                <div style="font-size:0.72rem;color:var(--muted);">
                    This load was cancelled by the shipper. According to distance and bidded amount, you got this amount as compensation.
                </div>
            </div>`;
    }

    return '';
}

// ── Inline proof request block inside trip card ───────────────
function renderProofRequestInline(trip, pendingRequestId) {
    if (trip.status !== 'in_transit') return '';
    if (!pendingRequestId) return '';

    return `
        <div style="margin-top:14px;padding:14px;background:rgba(245,158,11,0.1);
                    border:2px solid #f59e0b;border-radius:10px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                <span style="font-size:1.3rem;">📸</span>
                <div>
                    <div style="font-weight:700;font-size:0.88rem;color:#f59e0b;">Shipper Requested Proof</div>
                    <div style="font-size:0.75rem;color:#94a3b8;margin-top:1px;">Take a photo of the goods and upload it now</div>
                </div>
            </div>
            <label style="display:flex;align-items:center;justify-content:center;gap:8px;
                           padding:10px;background:#f59e0b;color:#000;font-weight:700;
                           border-radius:8px;cursor:pointer;font-size:0.85rem;width:100%;box-sizing:border-box;">
                📷 Take / Upload Proof Photo
                <input type="file" accept="image/*" capture="environment" style="display:none"
                    onchange="doFulfillProofRequest('${trip.id}','${pendingRequestId}',this)">
            </label>
        </div>`;
}

// ── Photo history inside trip card (driver view) ──────────────
function renderDriverPhotoHistory(trip, photos) {
    if (!photos || photos.length === 0) return '';

    const sectionId = `photo-section-${trip.id}`;

    const rows = photos.map(p => {
        const isProof   = p.pod_type === 'proof_request';
        const isRejected = p.ack_status === 'rejected';
        const isApproved = p.ack_status === 'approved';

        const typeLabel = isProof
            ? '<span style="font-size:0.68rem;font-family:var(--font-mono);color:#f59e0b;background:rgba(245,158,11,0.15);padding:1px 6px;border-radius:4px;">🔔 Proof</span>'
            : '<span style="font-size:0.68rem;font-family:var(--font-mono);color:var(--green);background:rgba(34,197,94,0.12);padding:1px 6px;border-radius:4px;">✅ Delivery</span>';

        const ackBadge = isApproved
            ? '<span style="font-size:0.68rem;color:var(--green);font-family:var(--font-mono);margin-left:4px;">✅ Approved</span>'
            : isRejected
            ? '<span style="font-size:0.68rem;color:#ef4444;font-family:var(--font-mono);margin-left:4px;">❌ Rejected</span>'
            : '<span style="font-size:0.68rem;color:#f59e0b;font-family:var(--font-mono);margin-left:4px;">⏳ Pending</span>';

        const location = p.dest_address
            ? `<div style="font-size:0.72rem;color:var(--muted);margin-top:2px;">📍 ${p.dest_address}</div>`
            : `<div style="font-size:0.72rem;color:var(--muted);margin-top:2px;">On-demand proof</div>`;

        const dt      = new Date(p.uploaded_at);
        const dateStr = dt.toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' });
        const timeStr = dt.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' });

        // Rejection notice + re-upload button
        const rejectionBlock = isRejected ? `
            <div style="margin-top:8px;padding:8px 10px;background:rgba(239,68,68,0.1);
                        border:1px solid #ef4444;border-radius:6px;">
                <div style="font-size:0.72rem;color:#ef4444;font-weight:600;margin-bottom:4px;">
                    ❌ Shipper rejected this photo
                </div>
                ${p.ack_notes ? `<div style="font-size:0.72rem;color:var(--muted);margin-bottom:8px;">"${p.ack_notes}"</div>` : ''}
                <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;
                               padding:5px 10px;background:#ef4444;color:#fff;border-radius:6px;
                               font-size:0.75rem;font-weight:600;">
                    📷 Re-upload Photo
                    <input type="file" accept="image/*" capture="environment" style="display:none"
                        onchange="doReuploadPhoto('${trip.id}','${p.dest_id || ''}','${p.pod_id}',this)">
                </label>
            </div>` : '';

        const borderColor = isApproved ? 'var(--green)' : isRejected ? '#ef4444' : 'var(--border)';

        return `
            <div style="display:flex;gap:10px;align-items:flex-start;padding:10px 0;
                        border-bottom:1px solid var(--border);">
                <img src="${p.image_url}" alt="photo"
                     onclick="driverOpenPhoto('${p.image_url}','${(p.dest_address||'Proof Photo').replace(/'/g,"\\'")}','${p.uploaded_at}','${(p.shipper_name||'').replace(/'/g,"\\'")}')"
                     style="width:64px;height:64px;object-fit:cover;border-radius:6px;
                            cursor:pointer;flex-shrink:0;border:2px solid ${borderColor};">
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;">
                        ${typeLabel}${ackBadge}
                        <span style="font-size:0.7rem;color:var(--muted);margin-left:2px;">${dateStr} · ${timeStr}</span>
                    </div>
                    ${location}
                    <div style="font-size:0.72rem;color:var(--muted);margin-top:2px;">
                        👤 <strong style="color:var(--text);">${p.shipper_name || 'Unknown'}</strong>
                        ${p.shipper_phone ? `· ${p.shipper_phone}` : ''}
                    </div>
                    ${rejectionBlock}
                </div>
            </div>`;
    }).join('');

    return `
        <div style="margin-top:12px;border:1px solid var(--border);border-radius:8px;overflow:hidden;">
            <button onclick="togglePhotoSection('${sectionId}')"
                    style="width:100%;display:flex;justify-content:space-between;align-items:center;
                           padding:10px 14px;background:var(--surface2);border:none;cursor:pointer;
                           font-size:0.82rem;font-weight:600;color:var(--text);">
                <span>📷 Delivery Photos <span style="font-size:0.72rem;font-family:var(--font-mono);
                      color:var(--muted);font-weight:400;margin-left:4px;">${photos.length} photo${photos.length !== 1 ? 's' : ''}</span>
                ${photos.some(p => p.ack_status === 'rejected') ? '<span style="font-size:0.7rem;color:#ef4444;margin-left:6px;">⚠ Action needed</span>' : ''}
                </span>
                <span id="${sectionId}-arrow" style="font-size:0.75rem;color:var(--muted);transition:transform 0.2s;">▼</span>
            </button>
            <div id="${sectionId}" style="display:none;padding:0 14px;">
                ${rows}
            </div>
        </div>`;
}

function togglePhotoSection(sectionId) {
    const body  = document.getElementById(sectionId);
    const arrow = document.getElementById(sectionId + '-arrow');
    if (!body) return;
    const isOpen = body.style.display !== 'none';
    body.style.display  = isOpen ? 'none' : 'block';
    arrow.style.transform = isOpen ? '' : 'rotate(180deg)';
}

// ── Driver photo full-screen viewer ──────────────────────────
function driverOpenPhoto(url, label, uploadedAt, shipperName) {
    const existing = document.getElementById('driver-photo-modal');
    if (existing) existing.remove();

    const dt      = new Date(uploadedAt);
    const dateStr = dt.toLocaleDateString('en-IN', { day:'numeric', month:'long', year:'numeric' });
    const timeStr = dt.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' });

    const modal = document.createElement('div');
    modal.id = 'driver-photo-modal';
    modal.style.cssText = `
        position:fixed;inset:0;background:rgba(0,0,0,0.88);
        z-index:2000;display:flex;align-items:center;justify-content:center;padding:20px;
    `;
    modal.innerHTML = `
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;
                    max-width:520px;width:100%;overflow:hidden;box-shadow:0 16px 48px rgba(0,0,0,0.5);">
            <!-- Header -->
            <div style="padding:14px 18px;border-bottom:1px solid var(--border);
                        display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="font-weight:700;font-size:0.9rem;">📷 ${label}</div>
                    <div style="font-size:0.72rem;color:var(--muted);margin-top:2px;">
                        ${dateStr} at ${timeStr}
                        ${shipperName ? ` · Shipper: <strong>${shipperName}</strong>` : ''}
                    </div>
                </div>
                <button onclick="document.getElementById('driver-photo-modal').remove()"
                        style="background:none;border:none;color:var(--muted);font-size:1.3rem;cursor:pointer;">✕</button>
            </div>
            <!-- Image -->
            <div style="background:#000;display:flex;align-items:center;justify-content:center;max-height:60vh;overflow:hidden;">
                <img src="${url}" alt="Photo"
                     style="max-width:100%;max-height:60vh;object-fit:contain;display:block;">
            </div>
            <!-- Footer -->
            <div style="padding:12px 18px;display:flex;justify-content:flex-end;gap:8px;">
                <a href="${url}" download target="_blank"
                   class="btn btn-outline btn-sm" style="font-size:0.78rem;">⬇ Download</a>
                <button onclick="document.getElementById('driver-photo-modal').remove()"
                        class="btn btn-outline btn-sm" style="font-size:0.78rem;">✕ Close</button>
            </div>
        </div>`;
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
    document.body.appendChild(modal);
}

function renderTripButtons(trip) {
    if (trip.status === 'cancelled') {
        return `<div style="font-size:0.75rem;color:#ef4444;font-weight:600;text-align:center;padding:6px;background:rgba(239,68,68,0.05);border:1px dashed rgba(239,68,68,0.2);border-radius:6px;">This trip has been cancelled.</div>`;
    }
    if (trip.status === 'assigned') {
        return `<div class="trip-status-btns"><button class="btn btn-primary btn-sm" onclick="doUpdateStatus('${trip.id}','in_transit')">🚚 Start Trip</button></div>`;
    }
    if (trip.status === 'in_transit') {
        let html = '<div style="margin-top:12px;font-weight:600;font-size:0.85rem;">Route Stops:</div><ul style="margin:8px 0;padding-left:20px;font-size:0.85rem;">';
        if (trip.destinations && trip.destinations.length > 0) {
            const sorted = [...trip.destinations].sort((a, b) => a.order_index - b.order_index);
            const nextIdx = sorted.findIndex(d => d.status !== 'delivered');
            sorted.forEach((d, i) => {
                const isDelivered = d.status === 'delivered';
                const isActive    = i === nextIdx;
                const isFuture    = !isDelivered && !isActive;
                let icon, label;
                if (isDelivered) {
                    icon = '✅'; label = '<span style="font-size:0.7rem;color:var(--muted);margin-left:6px;">Delivered</span>';
                } else if (isActive) {
                    if (!d.ack_status || d.ack_status === 'none') {
                        icon = '📍'; label = `<button class="btn btn-primary btn-sm" style="margin-left:8px;padding:2px 8px;font-size:0.7rem;" onclick="doSendArrival('${trip.id}','${d.id}')">I've Arrived</button>`;
                    } else if (d.ack_status === 'pending_approval') {
                        icon = '⏳'; label = '<span style="margin-left:8px;font-size:0.7rem;color:#f59e0b;font-family:var(--font-mono);">Waiting for shipper approval...</span>';
                    } else if (d.ack_status === 'approved') {
                        icon = '✔️';
                        label = `
                            <button class="btn btn-outline btn-sm" style="margin-left:8px;padding:2px 8px;font-size:0.7rem;border-color:var(--green);color:var(--green);" onclick="doMarkDestDelivered('${trip.id}','${d.id}')">Mark Delivered</button>
                            <label class="btn btn-outline btn-sm" style="margin-left:6px;padding:2px 8px;font-size:0.7rem;cursor:pointer;" title="Upload delivery photo">
                                📷 Photo
                                <input type="file" accept="image/*" capture="environment" style="display:none"
                                    onchange="doUploadDeliveryPhoto('${trip.id}','${d.id}',this)">
                            </label>`;
                    }
                } else {
                    icon = '🔒'; label = `<span style="margin-left:8px;font-size:0.7rem;color:var(--muted);">Complete stop ${i} first</span>`;
                }
                html += `<li style="margin-bottom:8px;${isFuture ? 'opacity:0.45;' : ''}">${icon} <strong>Stop ${i+1}:</strong> ${d.address} ${label}</li>`;
            });
        } else {
            html += `<li>No multi-stop data — <button class="btn btn-outline btn-sm" onclick="doUpdateStatus('${trip.id}','delivered')">Mark Delivered</button></li>`;
        }
        html += '</ul>';
        const sorted = trip.destinations ? [...trip.destinations].sort((a,b) => a.order_index - b.order_index) : [];
        if (sorted.some(d => d.status === 'delivered') && sorted.some(d => d.status !== 'delivered')) {
            html += `<div class="trip-status-btns"><button class="btn btn-outline btn-sm" onclick="doEndTripEarly('${trip.id}')" style="color:red;border-color:red;">⚠️ End Trip Early (Abandon)</button></div>`;
        }
        return html;
    }
    return '';
}

async function doSendArrival(shipmentId, destId) {
    try { await sendArrivalAck(shipmentId, destId); await loadMyTrips(); }
    catch (err) { alert('Error: ' + err.message); }
}

async function doMarkDestDelivered(shipmentId, destId) {
    if (!confirm('Confirm: mark this stop as delivered?')) return;
    try { await updateDestinationStatus(shipmentId, destId, 'delivered'); await loadMyTrips(); }
    catch (err) { alert('Error: ' + err.message); }
}

async function doEndTripEarly(shipmentId) {
    if (!confirm('End trip early? You will be paid proportionally and remaining stops re-posted.')) return;
    try { await abandonShipment(shipmentId); await loadMyTrips(); await loadOpenLoads(); alert('Trip ended. You have been paid proportionally.'); }
    catch (err) { alert('Error: ' + err.message); }
}

async function doUpdateStatus(shipmentId, status) {
    if (!confirm(`Confirm: ${status === 'in_transit' ? 'start this trip' : 'mark as delivered'}?`)) return;
    try {
        await updateShipmentStatus(shipmentId, status);
        if (status === 'in_transit') startTracking(shipmentId); else stopTracking();
        await loadMyTrips();
    } catch (err) { alert('Error: ' + err.message); }
}

// ── GPS Tracking ──────────────────────────────────────────────
let trackingInterval = null;
let driverMap        = null;
let mapMarkers       = [];

function initDriverMap() {
    if (driverMap) return;
    document.getElementById('trip-map').style.display = 'block';
    driverMap = L.map('trip-map').setView([20.5937, 78.9629], 5); 
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap contributors' }).addTo(driverMap);
}

function plotTripOnMap(trip) {
    initDriverMap();
    mapMarkers.forEach(m => driverMap.removeLayer(m));
    mapMarkers = [];
    const points = [];
    if (trip.pickup_lat && trip.pickup_lng) {
        const p = [trip.pickup_lat, trip.pickup_lng];
        points.push(p);
        mapMarkers.push(L.marker(p).addTo(driverMap).bindPopup('Pickup: ' + trip.pickup_address));
    }
    (trip.destinations || []).forEach(d => {
        const p = [d.lat, d.lng];
        points.push(p);
        const icon = L.icon({
            iconUrl: d.status === 'delivered'
                ? 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png'
                : 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25,41], iconAnchor: [12,41], popupAnchor: [1,-34], shadowSize: [41,41]
        });
        mapMarkers.push(L.marker(p, { icon }).addTo(driverMap).bindPopup('Drop: ' + d.address));
    });
    if (points.length) driverMap.fitBounds(L.latLngBounds(points), { padding: [30,30] });
}

function startTracking(shipmentId) {
    if (trackingInterval) clearInterval(trackingInterval);
    trackingInterval = setInterval(() => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                pos => sendDriverLocation(shipmentId, pos.coords.latitude, pos.coords.longitude).catch(e => console.error('Tracking error', e)),
                err => console.warn('Geolocation error', err)
            );
        }
    }, 15000);
}

function stopTracking() {
    if (trackingInterval) clearInterval(trackingInterval);
    trackingInterval = null;
}

function escapeHtmlDriver(s) {
    if (s == null || s === '') return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function formatChatTimestampDriver(ts) {
    if (!ts) return '';
    try {
        const date = new Date(ts);
        if (isNaN(date.getTime())) return ts;
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' ' + date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch (e) {
        return ts;
    }
}







// ── My Rating ─────────────────────────────────────────────────
async function loadMyRating() {
    const box = document.getElementById('my-rating-box');
    if (!box) return;
    try {
        const p = await getMyDriverProfile();
        if (!p.avg_rating) {
            box.innerHTML = '<div style="color:var(--muted);font-size:0.85rem;text-align:center;padding:12px 0;">No ratings yet. Complete your first delivery to get rated.</div>';
            return;
        }
        const breakdownHtml = [5,4,3,2,1].map(star => {
            const count = p.breakdown[String(star)] || 0;
            const pct   = p.total_ratings > 0 ? Math.round((count / p.total_ratings) * 100) : 0;
            return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:3px;font-size:0.8rem;">
                <span style="width:14px;text-align:right;color:var(--muted);">${star}</span>
                <span style="color:#f59e0b;font-size:0.7rem;">⭐</span>
                <div style="flex:1;background:var(--surface2);border-radius:3px;height:7px;overflow:hidden;">
                    <div style="width:${pct}%;background:#f59e0b;height:100%;border-radius:3px;"></div>
                </div>
                <span style="width:24px;color:var(--muted);font-family:var(--font-mono);font-size:0.7rem;">${count}</span>
            </div>`;
        }).join('');
        const recentHtml = p.history.slice(0, 5).map(r =>
            `<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:0.82rem;">
                <div style="display:flex;justify-content:space-between;">
                    <span style="font-weight:600;">${r.shipment_goods}</span>
                    <span style="color:#f59e0b;">${'⭐'.repeat(Math.round(r.score))} <strong>${r.score}</strong></span>
                </div>
                <div style="color:var(--muted);font-size:0.72rem;margin-top:2px;">By ${r.shipper_name} · ${timeAgo(r.created_at)}</div>
            </div>`
        ).join('');
        box.innerHTML = `
            <div style="display:flex;gap:20px;align-items:center;margin-bottom:16px;">
                <div style="text-align:center;">
                    <div style="font-size:2.4rem;font-weight:700;color:#f59e0b;line-height:1;">${p.avg_rating.toFixed(1)}</div>
                    <div style="font-size:0.72rem;color:var(--muted);margin-top:2px;">out of 5</div>
                </div>
                <div style="flex:1;">${breakdownHtml}</div>
                <div style="text-align:center;">
                    <div style="font-size:1.4rem;font-weight:700;">${p.total_ratings}</div>
                    <div style="font-size:0.72rem;color:var(--muted);">ratings</div>
                </div>
            </div>
            <div style="font-size:0.72rem;font-family:var(--font-mono);color:var(--muted);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Recent Ratings</div>
            ${recentHtml}`;
    } catch (err) {
        box.innerHTML = '<div style="color:var(--muted);font-size:0.82rem;">Could not load ratings.</div>';
    }
}

// ── Init ──────────────────────────────────────────────────────
loadMyRating();
loadMyTrips();
loadMyActiveBids().then(() => loadOpenLoads());
refreshDriverMessageNotifications();
driverNotificationPoll = setInterval(refreshDriverMessageNotifications, 10000);

// Lightweight background refresh — only updates stats + proof banners,
// never rebuilds the trip cards HTML so photo sections stay open.
setInterval(refreshTripStats, 10000);

async function refreshTripStats() {
    try {
        const trips = await getMyShipments();
        const active    = trips.filter(t => ['assigned','in_transit'].includes(t.status)).length;
        const completed = trips.filter(t => t.status === 'delivered').length;
        document.getElementById('stat-active').textContent = active;
        document.getElementById('stat-done').textContent   = completed;

        // Check proof requests for in-transit trips without re-rendering
        for (const t of trips.filter(t => t.status === 'in_transit')) {            try {
                const reqs    = await getProofRequests(t.id);
                const pending = reqs.find(r => r.status === 'pending');
                if (pending && pending.request_id !== activeProofRequestId) {
                    activeProofRequestId = pending.request_id;
                    showProofRequestBanner(t.id, pending.request_id);
                    const inlineEl = document.getElementById(`proof-inline-${t.id}`);
                    if (inlineEl) inlineEl.style.display = 'block';
                } else if (!pending) {
                    const banner = document.getElementById('proof-request-banner');
                    if (banner) banner.remove();
                    if (activeProofRequestId) activeProofRequestId = null;
                }
            } catch (e) { /* silent */ }

            // Check if any photos were rejected — auto-open photo section so driver sees it
            // Skip cancelled trips — no point alerting about photos on cancelled shipments
            try {
                const photos   = await getShipmentPhotos(t.id);
                const rejected = photos.some(p => p.ack_status === 'rejected');
                if (rejected) {
                    const sectionId = `photo-section-${t.id}`;
                    const body      = document.getElementById(sectionId);
                    const arrow     = document.getElementById(sectionId + '-arrow');
                    if (body && body.style.display === 'none') {
                        body.style.display    = 'block';
                        if (arrow) arrow.style.transform = 'rotate(180deg)';
                        showToast('⚠️ Shipper rejected a photo — please re-upload', 'error');
                    }
                }
            } catch (e) { /* silent */ }

            // Check for pending destination change requests
            try {
                const tripData = trips.find(x => x.id === t.id);
                if (tripData && tripData.destinations) {
                    for (const dest of tripData.destinations.filter(d => d.status !== 'delivered')) {
                        const changeReq = await getPendingChangeRequest(t.id, dest.id).catch(() => null);
                        if (changeReq && changeReq.request_id) {
                            const bannerId = 'dest-change-banner-' + changeReq.request_id;
                            if (!document.getElementById(bannerId)) {
                                showDestinationChangeBanner(t.id, dest.id, changeReq);
                            }
                        }
                    }
                }
            } catch (e) { /* silent */ }
        }
    } catch (e) { /* silent */ }
}

// ── Destination Change Banner (driver view) ───────────────────
let shownChangeRequests = new Set(); // track which requests already shown

function showDestinationChangeBanner(shipmentId, destId, changeReq) {
    const bannerId = 'dest-change-banner-' + changeReq.request_id;
    // Already showing this banner
    if (document.getElementById(bannerId)) return;

    const banner = document.createElement('div');
    banner.id = bannerId;
    banner.style.cssText = `
        position:fixed; top:70px; left:50%; transform:translateX(-50%);
        background:#1e293b; border:2px solid #3b82f6; border-radius:12px;
        padding:18px 22px; z-index:999; max-width:460px; width:90%;
        box-shadow:0 8px 32px rgba(0,0,0,0.5);
    `;
    banner.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
            <span style="font-size:1.4rem;">📍</span>
            <div>
                <div style="font-weight:700;font-size:0.95rem;color:#60a5fa;">Shipper Changed Destination</div>
                <div style="font-size:0.75rem;color:#94a3b8;margin-top:2px;">Please accept or reject the new drop location</div>
            </div>
        </div>
        <div style="padding:10px 14px;background:rgba(0,0,0,0.3);border-radius:8px;margin-bottom:14px;">
            <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">New Address</div>
            <div style="font-weight:600;font-size:0.9rem;color:#f8fafc;">📍 ${changeReq.new_address}</div>
        </div>
        <div style="padding:8px 12px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2);
                    border-radius:6px;margin-bottom:14px;font-size:0.75rem;color:#f59e0b;">
            If you <strong>reject</strong>: deliver at original location and trip ends there.
        </div>
        <button onclick="openDriverChatWidget('${shipmentId}', 'Destination change chat')"
                style="width:100%;padding:10px 12px;margin-bottom:10px;background:rgba(59,130,246,0.12);color:#93c5fd;
                       border:1px solid rgba(59,130,246,0.35);border-radius:8px;font-weight:700;cursor:pointer;font-size:0.85rem;">
            💬 Chat with Shipper Before Deciding
        </button>
        <div style="display:flex;gap:10px;">
            <button onclick="doRespondDestChange('${shipmentId}','${destId}','rejected','${bannerId}')"
                    style="flex:1;padding:10px;background:rgba(239,68,68,0.15);color:#ef4444;
                           border:1px solid rgba(239,68,68,0.4);border-radius:8px;font-weight:700;cursor:pointer;font-size:0.85rem;">
                ✕ Reject — Deliver Here
            </button>
            <button onclick="doRespondDestChange('${shipmentId}','${destId}','accepted','${bannerId}')"
                    style="flex:1;padding:10px;background:#3b82f6;color:#fff;
                           border:none;border-radius:8px;font-weight:700;cursor:pointer;font-size:0.85rem;">
                ✓ Accept New Location
            </button>
        </div>
    `;
    document.body.appendChild(banner);
}

async function doRespondDestChange(shipmentId, destId, action, bannerId) {
    const banner = document.getElementById(bannerId);
    if (banner) {
        banner.innerHTML = `<div style="text-align:center;padding:8px;color:#94a3b8;">Processing...</div>`;
    }
    try {
        const result = await respondDestinationChange(shipmentId, destId, action);
        if (banner) banner.remove();
        // Remove from shown set so it won't re-appear
        shownChangeRequests.delete(bannerId.replace('dest-change-banner-', ''));
        if (action === 'accepted') {
            showToast('✅ New destination accepted — navigate to new location', 'success');
        } else {
            showToast('📍 Delivering at original location — trip will end here', 'success');
        }
        // Force full reload of trips so new address / updated stops show immediately
        await loadMyTrips();
    } catch(err) {
        if (banner) banner.remove();
        showToast('Error: ' + err.message, 'error');
    }
}

// ── Delivery Photo Upload ─────────────────────────────────────
async function doUploadDeliveryPhoto(shipmentId, destId, inputEl) {    const file = inputEl.files[0];
    if (!file) return;
    inputEl.value = '';
    showPhotoPreviewModal({
        file,
        title: '📷 Delivery Photo Preview',
        subtitle: 'Review the photo before uploading as proof of delivery',
        confirmLabel: '✅ Upload as Delivery Proof',
        onConfirm: async () => {
            try {
                await uploadDeliveryPhoto(shipmentId, destId, file);
                showToast('📷 Delivery photo uploaded!', 'success');
            } catch (err) {
                showToast('Upload failed: ' + err.message, 'error');
            }
        }
    });
}

// ── Re-upload after shipper rejection ────────────────────────
async function doReuploadPhoto(shipmentId, destId, oldPodId, inputEl) {
    const file = inputEl.files[0];
    if (!file) return;
    inputEl.value = '';
    showPhotoPreviewModal({
        file,
        title: '📷 Re-upload Photo',
        subtitle: 'Shipper rejected the previous photo — review before sending',
        confirmLabel: '📤 Send New Photo',
        onConfirm: async () => {
            try {
                // Use "none" as destId when photo is not tied to a specific stop
                const effectiveDestId = destId || 'none';
                await uploadDeliveryPhoto(shipmentId, effectiveDestId, file, 'Re-uploaded after shipper rejection');
                showToast('📷 New photo sent to shipper!', 'success');
                await loadMyTrips();
            } catch (err) {
                showToast('Upload failed: ' + err.message, 'error');
            }
        }
    });
}

// ── Proof Request Polling ─────────────────────────────────────
// Check every 12 seconds if shipper has raised a proof request
let proofPollInterval = null;
let activeProofRequestId = null;

function startProofRequestPolling(shipmentId) {
    if (proofPollInterval) clearInterval(proofPollInterval);
    proofPollInterval = setInterval(() => checkProofRequests(shipmentId), 12000);
}

function stopProofRequestPolling() {
    if (proofPollInterval) clearInterval(proofPollInterval);
    proofPollInterval = null;
    activeProofRequestId = null;
}

async function checkProofRequests(shipmentId) {
    try {
        const requests = await getProofRequests(shipmentId);
        const pending  = requests.find(r => r.status === 'pending');
        if (pending && pending.request_id !== activeProofRequestId) {
            activeProofRequestId = pending.request_id;
            showProofRequestBanner(shipmentId, pending.request_id);
        } else if (!pending) {
            // Remove banner if no pending request
            const banner = document.getElementById('proof-request-banner');
            if (banner) banner.remove();
            activeProofRequestId = null;
        }
    } catch (e) { /* silent */ }
}

function showProofRequestBanner(shipmentId, requestId) {
    // Remove existing banner
    const existing = document.getElementById('proof-request-banner');
    if (existing) existing.remove();

    const banner = document.createElement('div');
    banner.id = 'proof-request-banner';
    banner.style.cssText = `
        position: fixed; top: 70px; left: 50%; transform: translateX(-50%);
        background: #1e293b; border: 2px solid #f59e0b; border-radius: 12px;
        padding: 18px 24px; z-index: 999; max-width: 420px; width: 90%;
        box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    `;
    banner.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
            <span style="font-size:1.5rem;">📸</span>
            <div>
                <div style="font-weight:700;font-size:0.95rem;color:#f59e0b;">Shipper Requested Proof</div>
                <div style="font-size:0.78rem;color:#94a3b8;margin-top:2px;">Please take a photo of the goods now</div>
            </div>
        </div>
        <label style="display:block;width:100%;text-align:center;padding:10px;background:#f59e0b;
                       color:#000;font-weight:700;border-radius:8px;cursor:pointer;font-size:0.9rem;">
            📷 Take / Upload Photo
            <input type="file" accept="image/*" capture="environment" style="display:none"
                onchange="doFulfillProofRequest('${shipmentId}','${requestId}',this)">
        </label>
        <button onclick="document.getElementById('proof-request-banner').remove()"
                style="margin-top:8px;width:100%;background:none;border:1px solid #334155;
                       color:#94a3b8;border-radius:8px;padding:6px;cursor:pointer;font-size:0.8rem;">
            Dismiss (respond later)
        </button>
    `;
    document.body.appendChild(banner);
}

async function doFulfillProofRequest(shipmentId, requestId, inputEl) {
    const file = inputEl.files[0];
    if (!file) return;
    inputEl.value = '';
    showPhotoPreviewModal({
        file,
        title: '📸 Proof Photo Preview',
        subtitle: 'Shipper requested this — review before sending',
        confirmLabel: '📤 Send to Shipper',
        onConfirm: async () => {
            try {
                await fulfillProofRequest(shipmentId, requestId, file);
                const banner = document.getElementById('proof-request-banner');
                if (banner) banner.remove();
                activeProofRequestId = null;
                showToast('✅ Proof photo sent to shipper!', 'success');
                await loadMyTrips();
            } catch (err) {
                showToast('Upload failed: ' + err.message, 'error');
            }
        }
    });
}

// ── Photo Preview Modal ───────────────────────────────────────
// Shows a preview of the selected image before uploading.
// Options: { file, title, subtitle, confirmLabel, onConfirm }
function showPhotoPreviewModal({ file, title, subtitle, confirmLabel, onConfirm }) {
    const existing = document.getElementById('photo-preview-modal');
    if (existing) existing.remove();

    const objectUrl = URL.createObjectURL(file);
    const sizeMB    = (file.size / (1024 * 1024)).toFixed(2);

    const modal = document.createElement('div');
    modal.id = 'photo-preview-modal';
    modal.style.cssText = `
        position: fixed; inset: 0; background: rgba(0,0,0,0.82);
        z-index: 2000; display: flex; align-items: center;
        justify-content: center; padding: 20px;
    `;

    modal.innerHTML = `
        <div style="background: var(--surface); border: 1px solid var(--border);
                    border-radius: 14px; max-width: 480px; width: 100%;
                    overflow: hidden; box-shadow: 0 16px 48px rgba(0,0,0,0.5);">

            <!-- Header -->
            <div style="padding: 16px 20px; border-bottom: 1px solid var(--border);
                        display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-weight: 700; font-size: 0.95rem;">${title}</div>
                    <div style="font-size: 0.75rem; color: var(--muted); margin-top: 2px;">${subtitle}</div>
                </div>
                <button id="ppm-close" style="background:none;border:none;color:var(--muted);
                        font-size:1.3rem;cursor:pointer;padding:4px 8px;line-height:1;">✕</button>
            </div>

            <!-- Image preview -->
            <div style="background: #000; position: relative; max-height: 55vh; overflow: hidden;
                        display: flex; align-items: center; justify-content: center;">
                <img id="ppm-img" src="${objectUrl}" alt="Preview"
                     style="max-width: 100%; max-height: 55vh; object-fit: contain; display: block;">
            </div>

            <!-- File info -->
            <div style="padding: 10px 20px; background: var(--surface2);
                        display: flex; gap: 16px; font-size: 0.78rem; color: var(--muted);
                        border-bottom: 1px solid var(--border);">
                <span>📄 ${file.name}</span>
                <span>📦 ${sizeMB} MB</span>
                <span>🖼 ${file.type.split('/')[1].toUpperCase()}</span>
            </div>

            <!-- Re-select option -->
            <div style="padding: 10px 20px; border-bottom: 1px solid var(--border);">
                <label style="display: inline-flex; align-items: center; gap: 6px;
                               font-size: 0.8rem; color: var(--muted); cursor: pointer;">
                    <input type="file" id="ppm-reselect" accept="image/*" capture="environment"
                           style="display:none">
                    🔄 Choose a different photo
                </label>
            </div>

            <!-- Actions -->
            <div style="padding: 16px 20px; display: flex; gap: 10px;">
                <button id="ppm-cancel" class="btn btn-outline" style="flex: 1;">
                    ✕ Cancel
                </button>
                <button id="ppm-confirm" class="btn btn-primary" style="flex: 2; font-weight: 700;">
                    ${confirmLabel}
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Close / cancel
    const closeModal = () => {
        URL.revokeObjectURL(objectUrl);
        modal.remove();
    };
    document.getElementById('ppm-close').onclick   = closeModal;
    document.getElementById('ppm-cancel').onclick  = closeModal;
    modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });

    // Re-select a different photo
    document.getElementById('ppm-reselect').addEventListener('change', function () {
        const newFile = this.files[0];
        if (!newFile) return;
        URL.revokeObjectURL(objectUrl);
        modal.remove();
        // Re-open preview with the new file, same callbacks
        showPhotoPreviewModal({ file: newFile, title, subtitle, confirmLabel, onConfirm });
    });

    // Confirm upload
    const confirmBtn = document.getElementById('ppm-confirm');
    confirmBtn.onclick = async () => {
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Uploading...';
        await onConfirm();
        closeModal();
    };
}

// ── Toast helper ──────────────────────────────────────────────
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
        background: ${type === 'success' ? '#22c55e' : '#ef4444'};
        color: #fff; padding: 12px 24px; border-radius: 8px; font-weight: 600;
        font-size: 0.88rem; z-index: 9999; box-shadow: 0 4px 16px rgba(0,0,0,0.3);
        animation: fadeInUp 0.3s ease;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

// ── Driver Analytics & Insights ───────────────────────────────
let chartDriverEarnings = null;
let chartDriverCategories = null;
let chartDriverVehicles = null;
let chartDriverTrips = null;

function renderDriverAnalytics() {
    loadDriverAnalytics();
}

async function loadDriverAnalytics() {
    const timeframe = document.getElementById("driver-timeframe").value;
    try {
        const trips = await getMyShipments();

        // Timeframe filtering
        let filtered = trips;
        const now = new Date();
        if (timeframe !== 'all') {
            const daysLimit = parseInt(timeframe);
            const limitDate = new Date(now.getTime() - daysLimit * 24 * 60 * 60 * 1000);
            filtered = filtered.filter(t => new Date(t.created_at) >= limitDate);
        }

        // Compute Driver KPIs
        let totalEarnings = 0;
        let escrowAmount = 0;
        let totalWeight = 0;
        let completedCount = 0;

        filtered.forEach(t => {
            if (t.status === 'delivered') {
                totalEarnings += Number(t.winning_bid_amount) || 0;
                totalWeight += Number(t.weight_kg) || 0;
                completedCount++;
            } else if (t.status === 'cancelled') {
                totalEarnings += Number(t.driver_fee) || 0;
            } else if (['assigned', 'in_transit'].includes(t.status)) {
                escrowAmount += Number(t.winning_bid_amount) || 0;
            }
        });

        document.getElementById("dr-kpi-earnings").textContent = "₹" + totalEarnings.toLocaleString('en-IN');
        document.getElementById("dr-kpi-escrow").textContent = "₹" + escrowAmount.toLocaleString('en-IN');
        document.getElementById("dr-kpi-weight").textContent = totalWeight >= 1000 
            ? (totalWeight / 1000).toFixed(1) + " tons" 
            : totalWeight.toLocaleString('en-IN') + " kg";
        document.getElementById("dr-kpi-trips").textContent = completedCount;

        // Categorized goods analysis
        const categories = {};
        filtered.forEach(t => {
            const cat = categorizeGoods(t.goods_desc);
            if (!categories[cat]) {
                categories[cat] = { count: 0, earnings: 0, weight: 0, completed: 0 };
            }
            categories[cat].count++;
            if (t.status === 'delivered') {
                categories[cat].earnings += Number(t.winning_bid_amount) || 0;
                categories[cat].weight += Number(t.weight_kg) || 0;
                categories[cat].completed++;
            } else if (t.status === 'cancelled') {
                categories[cat].earnings += Number(t.driver_fee) || 0;
            }
        });

        const catLabels = Object.keys(categories).sort();
        const catEarnings = catLabels.map(l => categories[l].earnings);
        const catCompletions = catLabels.map(l => categories[l].completed);
        const catWeights = catLabels.map(l => categories[l].weight);

        // Fill Table
        const tableBody = document.querySelector("#table-driver-categories tbody");
        if (tableBody) {
            if (catLabels.length === 0) {
                tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:20px;">No trip performance data available.</td></tr>`;
            } else {
                tableBody.innerHTML = catLabels.map(l => {
                    const data = categories[l];
                    const avg = data.completed > 0 ? Math.round(data.earnings / data.completed) : 0;
                    return `<tr style="border-bottom:1px solid var(--border);">
                        <td style="padding:10px 12px;"><strong>${l}</strong></td>
                        <td style="padding:10px 12px;">${data.completed}</td>
                        <td style="padding:10px 12px;">₹${data.earnings.toLocaleString('en-IN')}</td>
                        <td style="padding:10px 12px;">${avg > 0 ? '₹' + avg.toLocaleString('en-IN') : '—'}</td>
                        <td style="padding:10px 12px;">${data.weight.toLocaleString('en-IN')} kg</td>
                    </tr>`;
                }).join('');
            }
        }

        // Helper function (client-side matching)
        function categorizeGoods(desc) {
            if (!desc) return "Other";
            const d = desc.toLowerCase().trim();
            if (d.includes("electr") || d.includes("phone") || d.includes("tv") || d.includes("computer") || d.includes("gadget") || d.includes("appliances")) return "Electronics";
            if (d.includes("food") || d.includes("veget") || d.includes("fruit") || d.includes("grain") || d.includes("grocery") || d.includes("milk") || d.includes("beverag") || d.includes("meat") || d.includes("perish")) return "Food & Perishables";
            if (d.includes("furnit") || d.includes("wood") || d.includes("table") || d.includes("chair") || d.includes("bed") || d.includes("desk")) return "Furniture";
            if (d.includes("chem") || d.includes("pharma") || d.includes("drug") || d.includes("med") || d.includes("acid") || d.includes("fertiliz")) return "Chemicals & Pharma";
            if (d.includes("steel") || d.includes("metal") || d.includes("iron") || d.includes("cement") || d.includes("brick") || d.includes("construct") || d.includes("pip") || d.includes("sand") || d.includes("industrial")) return "Industrial & Metal";
            if (d.includes("cloth") || d.includes("textil") || d.includes("garment") || d.includes("apparel") || d.includes("shoe") || d.includes("fabric")) return "Apparel & Textiles";
            if (d.includes("paper") || d.includes("book") || d.includes("cardboard") || d.includes("station")) return "Paper & Print";
            if (d.includes("car") || d.includes("auto") || d.includes("motor") || d.includes("part") || d.includes("wheel") || d.includes("tyre")) return "Automotive";
            if (d.includes("pack") || d.includes("box") || d.includes("carton") || d.includes("bag") || d.includes("container") || d.includes("logistics")) return "Packaged Goods";
            return "Other";
        }

        // Charts
        // 1. Earnings Trend
        const monthlyEarnings = {};
        filtered.forEach(t => {
            let val = 0;
            if (t.status === 'delivered') val = Number(t.winning_bid_amount) || 0;
            else if (t.status === 'cancelled') val = Number(t.driver_fee) || 0;

            if (val > 0) {
                const date = new Date(t.created_at);
                const key = date.toLocaleString('default', { month: 'short', year: 'numeric' });
                if (!monthlyEarnings[key]) monthlyEarnings[key] = { amount: 0, dateObj: date };
                monthlyEarnings[key].amount += val;
            }
        });
        const sortedMonths = Object.keys(monthlyEarnings).sort((a,b) => monthlyEarnings[a].dateObj - monthlyEarnings[b].dateObj);
        const trendValues = sortedMonths.map(m => monthlyEarnings[m].amount);

        if (chartDriverEarnings) chartDriverEarnings.destroy();
        const ctxEarn = document.getElementById("chart-driver-earnings").getContext("2d");
        chartDriverEarnings = new Chart(ctxEarn, {
            type: 'line',
            data: {
                labels: sortedMonths,
                datasets: [{
                    label: 'Earnings (₹)',
                    data: trendValues,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.05)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.35,
                    pointBackgroundColor: '#34d399',
                    pointRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148, 163, 184, 0.05)' } },
                    y: { ticks: { color: '#94a3b8', callback: v => '₹' + v.toLocaleString('en-IN') }, grid: { color: 'rgba(148, 163, 184, 0.08)' } }
                }
            }
        });

        // 2. Haulage Categories
        if (chartDriverCategories) chartDriverCategories.destroy();
        const ctxCat = document.getElementById("chart-driver-categories").getContext("2d");
        chartDriverCategories = new Chart(ctxCat, {
            type: 'doughnut',
            data: {
                labels: catLabels,
                datasets: [{
                    data: catCompletions,
                    backgroundColor: [
                        'rgba(16, 185, 129, 0.7)',
                        'rgba(59, 130, 246, 0.7)',
                        'rgba(245, 158, 11, 0.7)',
                        'rgba(139, 92, 246, 0.7)',
                        'rgba(239, 68, 68, 0.7)',
                        'rgba(20, 184, 166, 0.7)',
                        'rgba(100, 116, 139, 0.7)'
                    ],
                    borderWidth: 1,
                    borderColor: '#1b2330'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right', labels: { color: '#94a3b8', font: { family: 'Inter', size: 10 } } }
                }
            }
        });

        // 3. Earnings by Vehicle Type
        const vehicleStats = {};
        filtered.forEach(t => {
            const v = t.vehicle_type || 'Unknown';
            if (!vehicleStats[v]) vehicleStats[v] = { count: 0, earnings: 0 };
            vehicleStats[v].count++;
            if (t.status === 'delivered') vehicleStats[v].earnings += Number(t.winning_bid_amount) || 0;
            else if (t.status === 'cancelled') vehicleStats[v].earnings += Number(t.driver_fee) || 0;
        });
        const vLabels = Object.keys(vehicleStats).sort();
        const vEarnings = vLabels.map(l => vehicleStats[l].earnings);

        if (chartDriverVehicles) chartDriverVehicles.destroy();
        const ctxVeh = document.getElementById("chart-driver-vehicles").getContext("2d");
        chartDriverVehicles = new Chart(ctxVeh, {
            type: 'bar',
            data: {
                labels: vLabels,
                datasets: [{
                    label: 'Earnings by Vehicle Type (₹)',
                    data: vEarnings,
                    backgroundColor: 'rgba(59, 130, 246, 0.7)',
                    borderColor: '#3b82f6',
                    borderWidth: 1.5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148, 163, 184, 0.05)' } },
                    y: { ticks: { color: '#94a3b8', callback: v => '₹' + v.toLocaleString('en-IN') }, grid: { color: 'rgba(148, 163, 184, 0.08)' } }
                }
            }
        });

        // 4. Trip Status Distribution
        const statuses = { delivered: 0, assigned: 0, in_transit: 0, cancelled: 0 };
        filtered.forEach(t => {
            if (statuses[t.status] !== undefined) statuses[t.status]++;
        });

        if (chartDriverTrips) chartDriverTrips.destroy();
        const ctxTrips = document.getElementById("chart-driver-trips").getContext("2d");
        chartDriverTrips = new Chart(ctxTrips, {
            type: 'doughnut',
            data: {
                labels: ['Completed', 'Assigned', 'In Transit', 'Cancelled'],
                datasets: [{
                    data: [statuses.delivered, statuses.assigned, statuses.in_transit, statuses.cancelled],
                    backgroundColor: [
                        'rgba(16, 185, 129, 0.7)',  // Green
                        'rgba(59, 130, 246, 0.7)',  // Blue
                        'rgba(245, 158, 11, 0.7)',  // Orange
                        'rgba(239, 68, 68, 0.7)'    // Red
                    ],
                    borderWidth: 1,
                    borderColor: '#1b2330'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right', labels: { color: '#94a3b8', font: { family: 'Inter', size: 10 } } }
                }
            }
        });

    } catch (e) {
        console.error(e);
        document.getElementById("table-driver-categories").innerHTML = `<div class="alert alert-error">Failed to load analytics: ${e.message}</div>`;
    }
}

// ── Driver Chat Widget ───────────────────────────────────────
let driverChatShipmentId = null;
let driverChatPollInterval = null;

async function openDriverChatWidget(shipmentId, displayTitle) {
    driverChatShipmentId = shipmentId;
    const widget = document.getElementById('driver-chat-widget');
    if (!widget) return;

    widget.style.display = 'flex';
    const meta = document.getElementById('driver-chat-meta');
    if (meta) meta.textContent = displayTitle || 'Chat with Shipper';
    const status = document.getElementById('driver-chat-status');
    if (status) { status.textContent = 'Connecting…'; status.style.color = '#f59e0b'; }

    await loadDriverChatHistoryWidget(shipmentId);
    if (driverChatPollInterval) clearInterval(driverChatPollInterval);
    driverChatPollInterval = setInterval(() => loadDriverChatHistoryWidget(shipmentId, true), 5000);
}

async function loadDriverChatHistoryWidget(shipmentId, silent = false) {
    const box = document.getElementById('driver-chat-messages');
    const status = document.getElementById('driver-chat-status');
    if (!shipmentId || !box) return;

    try {
        if (!silent) {
            box.innerHTML = '<div style="color:var(--muted);font-size:0.75rem;text-align:center;padding:20px;">Loading chat...</div>';
        }
        const msgs = await getMessages(shipmentId);
        renderDriverChatMessages(msgs);
        refreshDriverMessageNotifications();
        if (status) { status.textContent = 'Chat ready'; status.style.color = '#22c55e'; }
    } catch (e) {
        if (!silent) {
            box.innerHTML = '<div style="color:#ef4444;font-size:0.75rem;text-align:center;padding:20px;">Could not load messages.</div>';
        }
        if (status) { status.textContent = 'Chat unavailable'; status.style.color = '#ef4444'; }
    }
}


function renderDriverChatMessages(msgs) {
    const box = document.getElementById('driver-chat-messages');
    if (!box) return;
    if (!msgs || msgs.length === 0) {
        box.innerHTML = '<div style="color:var(--muted);font-size:0.75rem;text-align:center;padding:20px;font-style:italic;">No messages yet. Say hello to the shipper!</div>';
        return;
    }

    const wasAtBottom = box.scrollHeight - box.scrollTop <= box.clientHeight + 40;
    box.innerHTML = msgs.map(m => {
        const isMine = m.sender_role === 'driver';
        const time   = new Date(m.created_at).toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit'});
        return `
            <div style="display:flex;flex-direction:column;align-items:${isMine ? 'flex-end' : 'flex-start'};">
                <div style="max-width:80%;padding:8px 12px;
                            border-radius:${isMine ? '12px 12px 2px 12px' : '12px 12px 12px 2px'};
                            background:${isMine ? 'rgba(245,158,11,0.2)' : 'rgba(59,130,246,0.15)'};
                            border:1px solid ${isMine ? 'rgba(245,158,11,0.3)' : 'rgba(59,130,246,0.25)'};
                            font-size:0.85rem;line-height:1.4;word-break:break-word;">
                    ${escapeHtmlDriver(m.body)}
                </div>
                <div style="font-size:0.65rem;color:var(--muted);margin-top:2px;padding:0 4px;">
                    ${isMine ? 'You' : escapeHtmlDriver(m.sender_name)} · ${time}
                </div>
            </div>`;
    }).join('');
    if (wasAtBottom) box.scrollTop = box.scrollHeight;
}


function appendDriverChatMessage(fromRole, senderName, text, ts) {
    const box = document.getElementById('driver-chat-messages');
    if (!box) return;
    const isMine = fromRole === 'driver';
    const time = ts ? new Date(ts).toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit'}) : '';
    box.insertAdjacentHTML('beforeend', `
        <div style="display:flex;flex-direction:column;align-items:${isMine ? 'flex-end' : 'flex-start'};">
            <div style="max-width:80%;padding:8px 12px;
                        border-radius:${isMine ? '12px 12px 2px 12px' : '12px 12px 12px 2px'};
                        background:${isMine ? 'rgba(245,158,11,0.2)' : 'rgba(59,130,246,0.15)'};
                        border:1px solid ${isMine ? 'rgba(245,158,11,0.3)' : 'rgba(59,130,246,0.25)'};
                        font-size:0.85rem;line-height:1.4;word-break:break-word;">
                ${escapeHtmlDriver(text)}
            </div>
            <div style="font-size:0.65rem;color:var(--muted);margin-top:2px;padding:0 4px;">
                ${isMine ? 'You' : escapeHtmlDriver(senderName)} · ${time}
            </div>
        </div>`);
    box.scrollTop = box.scrollHeight;
}

function closeDriverChatSocket() {
    if (driverChatPollInterval) {
        clearInterval(driverChatPollInterval);
        driverChatPollInterval = null;
    }
}

function closeDriverChatWidget() {
    const widget = document.getElementById('driver-chat-widget');
    if (widget) widget.style.display = 'none';
    closeDriverChatSocket();
    driverChatShipmentId = null;
}

async function sendDriverChatMsg() {
    const inp = document.getElementById('driver-chat-input');
    if (!inp || !driverChatShipmentId) return;
    const text = inp.value.trim();
    if (!text) return;
    inp.value = '';

    try {
        await sendMessage(driverChatShipmentId, text);
        await loadDriverChatHistoryWidget(driverChatShipmentId, true);
        await refreshDriverMessageNotifications();
    } catch(e) {
        showToast('Failed to send message.', 'error');
    }
}

async function sendDriverFreightAdjustment() {
    if (!driverChatShipmentId) {
        showToast('Open the shipment chat before sending a request.', 'error');
        return;
    }
    const amountEl = document.getElementById('driver-adjustment-amount');
    const btn = document.getElementById('driver-adjustment-request-btn');
    const amount = Number(amountEl?.value || 0);
    if (!amount || amount <= 0) {
        showToast('Enter the extra amount to request.', 'error');
        return;
    }

    try {
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Sending...';
        }
        const result = await requestFreightAdjustment(driverChatShipmentId, amount);
        if (amountEl) amountEl.value = '';
        await loadDriverChatHistoryWidget(driverChatShipmentId, true);
        await loadMyTrips();
        showToast(result.message || 'Extra freight request sent to shipper.');
    } catch (e) {
        showToast(e.message || 'Could not request adjustment.', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Request';
        }
    }
}

window.sendDriverFreightAdjustment = sendDriverFreightAdjustment;
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('driver-adjustment-request-btn');
    if (btn) btn.addEventListener('click', sendDriverFreightAdjustment);
});

function driverShortAddress(addr) {
    return (addr || '').split(',')[0] || 'Stop';
}

async function refreshDriverMessageNotifications() {
    try {
        driverMessageNotifications = await getMessageNotifications();
        renderDriverMessageNotifications();
    } catch (err) {
        console.warn('Failed to load driver message notifications', err);
    }
}

function renderDriverMessageNotifications() {
    const badge = document.getElementById('driver-notification-badge');
    const list = document.getElementById('driver-notification-list');
    if (!badge || !list) return;

    const total = driverMessageNotifications.reduce((sum, n) => sum + (n.unread || 0), 0);
    if (total > 0) {
        badge.textContent = total > 99 ? '99+' : total;
        badge.style.display = '';
    } else {
        badge.style.display = 'none';
    }

    if (!driverMessageNotifications.length) {
        list.innerHTML = '<div style="padding:16px;color:var(--muted);font-size:0.8rem;">No new messages.</div>';
        return;
    }

    list.innerHTML = driverMessageNotifications.map(n => {
        const route = `${driverShortAddress(n.pickup_address)} -> ${driverShortAddress(n.drop_address)}`;
        const time = n.latest_at ? new Date(n.latest_at).toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' }) : '';
        return `
            <button onclick="openDriverMessageNotification('${n.shipment_id}')"
                    style="display:block;width:100%;text-align:left;background:none;border:none;border-bottom:1px solid rgba(148,163,184,0.08);padding:12px 14px;color:var(--text);cursor:pointer;">
                <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:4px;">
                    <strong style="font-size:0.84rem;">${escapeHtmlDriver(n.shipment_title || 'Shipment')}</strong>
                    <span style="background:#ef4444;color:#fff;border-radius:999px;padding:1px 7px;font-size:0.66rem;font-family:var(--font-mono);">${n.unread}</span>
                </div>
                <div style="font-size:0.74rem;color:var(--muted);margin-bottom:5px;">${escapeHtmlDriver(route)} - ${escapeHtmlDriver(time)}</div>
                <div style="font-size:0.78rem;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                    ${escapeHtmlDriver(n.sender_name)}: ${escapeHtmlDriver(n.latest_body)}
                </div>
            </button>`;
    }).join('');
}

function toggleDriverNotifications() {
    const panel = document.getElementById('driver-notification-panel');
    if (!panel) return;
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    if (panel.style.display === 'block') refreshDriverMessageNotifications();
}

async function openDriverMessageNotification(shipmentId) {
    const panel = document.getElementById('driver-notification-panel');
    if (panel) panel.style.display = 'none';
    await openDriverChatWidget(shipmentId, 'Chat with Shipper');
    await refreshDriverMessageNotifications();
}
