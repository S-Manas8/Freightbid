content = open('frontend/pages/shipper.html', encoding='utf-8').read()

old = """                    // Check if there is an active pending change request for this destination (outside in transit check to be safe)
                    let pendingChangeHtml = "";
                    const pChange = s.destination_change_requests
                        ? s.destination_change_requests.find(cr => cr.dest_id === d.id && cr.status === "pending")
                        : null;
                    if (pChange) {
                        pendingChangeHtml =
                            '<div style="font-size:0.75rem;color:#f59e0b;margin-top:4px;display:flex;align-items:center;gap:4px;">' +
                            '⏳ Pending Change: <span style="text-decoration:line-through;color:var(--muted);">' + d.address + '</span> ➜ <strong>' + pChange.new_address + '</strong>' +
                            '</div>';
                    }"""

new = """                    // Show pending destination change if shipper sent one and driver hasn't responded yet
                    let pendingChangeHtml = "";
                    if (d.pending_change && d.pending_change.new_address) {
                        pendingChangeHtml =
                            '<div style="font-size:0.72rem;color:#60a5fa;background:rgba(59,130,246,0.1);' +
                            'border:1px solid rgba(59,130,246,0.25);border-radius:4px;padding:3px 8px;margin-top:4px;display:inline-block;">' +
                            '⏳ Awaiting driver approval → <strong>' + d.pending_change.new_address + '</strong>' +
                            '</div>';
                    }"""

if old in content:
    content = content.replace(old, new, 1)
    print("Patched renderDetailRoute pendingChangeHtml OK")
else:
    print("ERROR: pattern not found")
    idx = content.find('destination_change_requests')
    print("Context:", repr(content[max(0,idx-100):idx+200]))

open('frontend/pages/shipper.html', 'w', encoding='utf-8').write(content)
print("Done")
