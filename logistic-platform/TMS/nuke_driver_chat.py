"""
Remove ALL WebSocket/live-trip chat code from driver.js.
Keep only the clean polling-based openDriverChatWidget we added.
"""
content = open('frontend/js/driver.js', encoding='utf-8').read()

# Remove the entire "Live WebSocket" block
ws_start = '// ── Live WebSocket (shipper chat + trip events) ──────────────'
ws_end   = 'function escapeHtmlDriver(s) {'

s = content.find(ws_start)
e = content.find(ws_end)
if s != -1 and e != -1 and e > s:
    content = content[:s] + content[e:]
    print("Removed Live WebSocket block OK")
else:
    print("WS block not found:", s, e)

# Remove loadDriverChatHistory / appendDriverLiveChat / sendTripLiveChat block
# These reference trip-live-messages which no longer exists
for func_start in [
    'async function loadDriverChatHistory(',
    'function appendDriverLiveChat(',
    'function sendTripLiveChat(',
    'function stopDriverTripLive(',
]:
    idx = content.find(func_start)
    if idx == -1:
        print("Not found:", func_start)
        continue
    # Find the closing brace of this function
    depth = 0
    i = idx
    found_open = False
    end = -1
    while i < len(content):
        if content[i] == '{':
            depth += 1
            found_open = True
        elif content[i] == '}':
            depth -= 1
            if found_open and depth == 0:
                end = i + 1
                break
        i += 1
    if end > 0:
        content = content[:idx] + content[end:]
        print("Removed:", func_start)
    else:
        print("Could not find end of:", func_start)

# Remove variable declarations for old WS
for var in [
    'let driverTripWs = null;\n',
    'let driverTripWsShipmentId = null;\n',
    'let driverTripPingTimer = null;\n',
    'let shownChangeRequests = new Set();\n',
]:
    if var in content:
        content = content.replace(var, '', 1)
        print("Removed var:", var.strip())

open('frontend/js/driver.js', 'w', encoding='utf-8').write(content)

# Syntax check
import subprocess
r = subprocess.run(['node', '--check', 'frontend/js/driver.js'], capture_output=True, text=True)
if r.returncode == 0:
    print("Syntax OK")
else:
    print("Syntax ERROR:", r.stderr[:300])
