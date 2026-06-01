content = open('frontend/js/driver.js', encoding='utf-8').read()

# Remove everything from the old widget code that's still there
# The old code starts after our new sendDriverChatMsg function
# Find the marker where old code begins
old_start = """    driverChatShipmentId = shipmentId;
    const widget = document.getElementById('driver-chat-widget');
    const meta = document.getElementById('driver-chat-meta');
    const messagesBox = document.getElementById('driver-chat-messages');
    const status = document.getElementById('driver-chat-status');"""

if old_start in content:
    idx = content.find(old_start)
    # Find the end of the old block - the last function ends with the appendDriverChatMsgWidget
    end_marker = "    messagesBox.scrollTop = messagesBox.scrollHeight;\n}\n"
    end_idx = content.find(end_marker, idx)
    if end_idx > 0:
        content = content[:idx] + content[end_idx + len(end_marker):]
        print("Removed old driver chat block OK")
    else:
        print("End marker not found")
else:
    print("Old start not found - already clean")

open('frontend/js/driver.js', 'w', encoding='utf-8').write(content)

# Verify no WebSocket references remain in chat code
ws_refs = [l for l in content.split('\n') if 'WebSocket' in l or 'driverChatWs' in l or 'driverChatPingInterval' in l]
if ws_refs:
    print("WARNING: WebSocket refs still present:")
    for r in ws_refs[:5]:
        print(" ", r.strip())
else:
    print("No WebSocket refs in chat code - clean!")

print("Done")
