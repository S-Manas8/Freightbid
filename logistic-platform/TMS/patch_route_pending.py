content = open('frontend/pages/shipper.html', encoding='utf-8').read()

# Find the renderDetailRoute function and add pending change request display
# After the stop address is shown, check if there's a pending change request

old = """                    stopsHtml +=
                        '<div style="display:flex;justify-content:space-between;align-items:center;' +
                        'padding:10px 0;border-bottom:1px solid var(--border);">' +
                            '<span style="font-size:0.9rem;">' +
                                icon + ' <strong>Stop ' + (i + 1) + ':</strong> ' + d.address +
                            '</span>' +
                            '<span style="display:flex;align-items:center;gap:6px;flex-shrink:0;margin-left:12px;">' +
                                rightSide +
                            '</span>' +
                        '</div>';"""

new = """                    // Check for pending destination change request on this stop
                    const pendingChangeKey = 'pending_change_' + d.id;
                    const pendingChange = window[pendingChangeKey] || null;
                    const pendingBadge = pendingChange
                        ? '<div style="font-size:0.7rem;color:#60a5fa;background:rgba(59,130,246,0.1);' +
                          'border:1px solid rgba(59,130,246,0.25);border-radius:4px;padding:2px 7px;margin-top:3px;">' +
                          '⏳ Pending new address: ' + pendingChange + '</div>'
                        : '';

                    stopsHtml +=
                        '<div style="display:flex;justify-content:space-between;align-items:flex-start;' +
                        'padding:10px 0;border-bottom:1px solid var(--border);">' +
                            '<div>' +
                                '<span style="font-size:0.9rem;">' +
                                    icon + ' <strong>Stop ' + (i + 1) + ':</strong> ' + d.address +
                                '</span>' +
                                pendingBadge +
                            '</div>' +
                            '<span style="display:flex;align-items:center;gap:6px;flex-shrink:0;margin-left:12px;">' +
                                rightSide +
                            '</span>' +
                        '</div>';"""

if old in content:
    content = content.replace(old, new, 1)
    print("Patched renderDetailRoute OK")
else:
    print("ERROR: pattern not found")
    idx = content.find("Stop ' + (i + 1) + ':</strong>")
    print("Context:", repr(content[idx-100:idx+200]))

# Also update doRequestDestChange to store pending address in window object
old2 = """                await requestDestinationChange(shipmentId, destId, finalAddr, changeDestLat, changeDestLng);
                document.getElementById('change-dest-modal').remove();
                showShipperToast('📍 Destination change sent to driver — awaiting response', 'success');
                // Refresh shipments list AND detail panel so new address shows immediately
                await loadMyShipments();
                await selectShipment(shipmentId);"""

new2 = """                await requestDestinationChange(shipmentId, destId, finalAddr, changeDestLat, changeDestLng);
                document.getElementById('change-dest-modal').remove();
                // Store pending address so route panel shows it immediately
                window['pending_change_' + destId] = finalAddr;
                showShipperToast('📍 Destination change sent to driver — awaiting response', 'success');
                // Refresh detail panel to show pending badge
                await selectShipment(shipmentId);"""

if old2 in content:
    content = content.replace(old2, new2, 1)
    print("Patched doRequestDestChange OK")
else:
    print("ERROR: doRequestDestChange pattern not found")

# Clear pending when driver responds (in loadBids auto-refresh)
# Add clearing logic in renderDetailRoute when stop is delivered
old3 = """                    // Check for pending destination change request on this stop
                    const pendingChangeKey = 'pending_change_' + d.id;"""

new3 = """                    // Clear pending change if stop is delivered or address changed
                    if (d.status === 'delivered') { delete window['pending_change_' + d.id]; }
                    // Check for pending destination change request on this stop
                    const pendingChangeKey = 'pending_change_' + d.id;"""

if old3 in content:
    content = content.replace(old3, new3, 1)
    print("Patched clear pending OK")

open('frontend/pages/shipper.html', 'w', encoding='utf-8').write(content)
print("Done")
