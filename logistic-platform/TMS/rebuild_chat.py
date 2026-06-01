"""
Remove all broken WebSocket/live-trip chat code from shipper.html
and replace with clean polling-based chat functions.
"""
import re

content = open('frontend/pages/shipper.html', encoding='utf-8').read()

# ── 1. Remove the entire stopTripLiveFeed / setLiveTripPanelVisible / loadChatHistory /
#       appendLiveChatLine / sendLiveTripChat / openBidChat / startLiveTripFeed /
#       pollDriverLocation / getWsShipmentUrl / pollDriverLocationFallback / fetchLatestDriverDot
#       block — find by markers

# Find start: the stopTripLiveFeed function
start_marker = '        function stopTripLiveFeed() {'
# Find end: the last function in this block before the next unrelated function
end_marker = '        async function selectShipment(id) {'

start_idx = content.find(start_marker)
end_idx   = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("ERROR: markers not found")
    print("start_idx:", start_idx, "end_idx:", end_idx)
else:
    # Remove the block between start and end (keep end)
    content = content[:start_idx] + '\n' + content[end_idx:]
    print("Removed broken WebSocket/live-trip block OK")

# ── 2. Remove the WebSocket variables declared near detailMap
old_vars = """        let shipmentLiveWs = null;
        let shipmentPingTimer = null;
        let activeChatDriverId = null;"""
if old_vars in content:
    content = content.replace(old_vars, '', 1)
    print("Removed WS variable declarations OK")
else:
    # Try partial
    for v in ['let shipmentLiveWs = null;', 'let shipmentPingTimer = null;', 'let activeChatDriverId = null;']:
        if v in content:
            content = content.replace(v, '', 1)
            print("Removed:", v)

# Also remove activeChatDriverName
for v in ['let activeChatDriverName = null;', 'activeChatDriverName = null;']:
    content = content.replace(v, '', 1)

# ── 3. Fix switchDetailTab to include 'chat'
old_switch = """        function switchDetailTab(tab) {
            ['route','bids','photos'].forEach(t => {
                document.getElementById('tab-' + t).classList.toggle('active', t === tab);
                document.getElementById('pane-' + t).classList.toggle('active', t === tab);
            });
            // Invalidate map size when route tab becomes visible
            if (tab === 'route' && detailMap) setTimeout(() => detailMap.invalidateSize(), 50);
        }"""
new_switch = """        function switchDetailTab(tab) {
            ['route','bids','photos','chat'].forEach(t => {
                const btn = document.getElementById('tab-' + t);
                const pane = document.getElementById('pane-' + t);
                if (btn) btn.classList.toggle('active', t === tab);
                if (pane) pane.classList.toggle('active', t === tab);
            });
            if (tab === 'route' && detailMap) setTimeout(() => detailMap.invalidateSize(), 50);
            if (tab === 'chat' && currentShipmentId) loadShipperChat(currentShipmentId);
        }"""
if old_switch in content:
    content = content.replace(old_switch, new_switch, 1)
    print("Fixed switchDetailTab OK")
else:
    print("WARNING: switchDetailTab not found with expected text")

# ── 4. Add clean polling-based chat functions before showShipperToast
chat_js = """
        // ── Shipper Chat (polling-based) ───────────────────────────
        let shipperChatPollInterval = null;
        let shipperChatShipmentId   = null;

        async function loadShipperChat(shipmentId) {
            if (!shipmentId) return;
            shipperChatShipmentId = shipmentId;
            const box = document.getElementById('shipper-chat-messages');
            if (!box) return;

            // Check if driver is assigned
            const s = myShipments.find(x => x.id === shipmentId);
            if (!s || !s.assigned_driver) {
                box.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:0.8rem;padding:20px;">Chat is available once a driver is assigned to this shipment.</div>';
                return;
            }

            box.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:0.78rem;padding:16px;">Loading messages...</div>';
            try {
                const msgs = await getMessages(shipmentId);
                renderShipperChatMessages(msgs);
                // Start polling
                if (shipperChatPollInterval) clearInterval(shipperChatPollInterval);
                shipperChatPollInterval = setInterval(() => refreshShipperChat(), 5000);
            } catch(e) {
                box.innerHTML = '<div style="text-align:center;color:#ef4444;font-size:0.78rem;padding:16px;">Could not load messages.</div>';
            }
        }

        async function refreshShipperChat() {
            if (!shipperChatShipmentId) return;
            try {
                const msgs = await getMessages(shipperChatShipmentId);
                renderShipperChatMessages(msgs);
                // Update unread badge
                const unread = msgs.filter(m => m.sender_role === 'driver' && !m.read_at).length;
                const badge = document.getElementById('chat-unread-badge');
                if (badge) {
                    badge.textContent = unread;
                    badge.style.display = unread > 0 ? 'inline' : 'none';
                }
            } catch(e) { /* silent */ }
        }

        function renderShipperChatMessages(msgs) {
            const box = document.getElementById('shipper-chat-messages');
            if (!box) return;
            const wasAtBottom = box.scrollHeight - box.scrollTop <= box.clientHeight + 40;

            if (!msgs || msgs.length === 0) {
                box.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:0.78rem;padding:20px;font-style:italic;">No messages yet. Say hello to the driver!</div>';
                return;
            }

            box.innerHTML = msgs.map(m => {
                const isMine = m.sender_role === 'shipper';
                const time   = new Date(m.created_at).toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit'});
                return `
                <div style="display:flex;flex-direction:column;align-items:${isMine ? 'flex-end' : 'flex-start'};">
                    <div style="max-width:80%;padding:8px 12px;border-radius:${isMine ? '12px 12px 2px 12px' : '12px 12px 12px 2px'};
                                background:${isMine ? 'rgba(245,158,11,0.2)' : 'rgba(59,130,246,0.15)'};
                                border:1px solid ${isMine ? 'rgba(245,158,11,0.3)' : 'rgba(59,130,246,0.25)'};
                                font-size:0.85rem;line-height:1.4;">
                        ${escapeHtml(m.body)}
                    </div>
                    <div style="font-size:0.65rem;color:var(--muted);margin-top:2px;padding:0 4px;">
                        ${isMine ? 'You' : escapeHtml(m.sender_name)} · ${time}
                    </div>
                </div>`;
            }).join('');

            if (wasAtBottom) box.scrollTop = box.scrollHeight;
        }

        async function doShipperSendMessage() {
            const inp = document.getElementById('shipper-chat-input');
            if (!inp || !currentShipmentId) return;
            const text = inp.value.trim();
            if (!text) return;
            inp.value = '';
            try {
                await sendMessage(currentShipmentId, text);
                await refreshShipperChat();
                const box = document.getElementById('shipper-chat-messages');
                if (box) box.scrollTop = box.scrollHeight;
            } catch(e) {
                showShipperToast('Failed to send message: ' + e.message, 'error');
            }
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }

        // Stop chat polling when detail panel closes
        const _origCloseDetail = typeof closeDetail === 'function' ? closeDetail : null;

"""

insert_before = '        function showShipperToast(message, type'
if insert_before in content:
    content = content.replace(insert_before, chat_js + '        ' + insert_before.lstrip(), 1)
    print("Added chat JS OK")
else:
    print("ERROR: showShipperToast not found")

# ── 5. Wire chat loading into selectShipment — stop old poll, start new
old_close = """                } else {
                    document.getElementById('pod-photos-grid').innerHTML = '';
                    document.getElementById('proof-request-status').innerHTML = '';
                }
            }

            // Auto-switch to bids tab
            switchDetailTab('bids');
            await loadBids(id);"""
new_close = """                } else {
                    document.getElementById('pod-photos-grid').innerHTML = '';
                    document.getElementById('proof-request-status').innerHTML = '';
                }
            }

            // Stop old chat poll when switching shipments
            if (shipperChatPollInterval) { clearInterval(shipperChatPollInterval); shipperChatPollInterval = null; }
            shipperChatShipmentId = null;

            // Auto-switch to bids tab
            switchDetailTab('bids');
            await loadBids(id);"""
if old_close in content:
    content = content.replace(old_close, new_close, 1)
    print("Wired chat stop into selectShipment OK")
else:
    print("WARNING: selectShipment close block not found")

open('frontend/pages/shipper.html', 'w', encoding='utf-8').write(content)
print("\nDone. File written.")
