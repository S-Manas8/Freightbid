content = open('frontend/js/driver.js', encoding='utf-8').read()
lines = content.split('\n')

# Remove specific broken calls inline
replacements = [
    ('            stopDriverTripLive();\n', ''),
    ('    stopDriverTripLive();\n', ''),
    ('    const url = getWsShipmentUrl(shipmentId, getUserId());\n', ''),
    ('    if (!url) return;\n', ''),
    ('    loadDriverChatHistory(shipmentId);\n', ''),
    ('            appendDriverLiveChat(msg.from_role, msg.sender_name, msg.text, msg.ts);\n', ''),
]
for old, new in replacements:
    if old in content:
        content = content.replace(old, new, 1)
        print("Removed:", repr(old.strip()))

# Remove the entire startDriverTripLive / connectDriverChatSocket block
# Find it by looking for the function that uses getWsShipmentUrl
import re

# Remove any function that references getWsShipmentUrl or driverTripWs
funcs_to_remove = [
    r'function startDriverTripLive\b',
    r'function connectDriverChatSocket\b',
    r'async function loadDriverChatHistoryWidget\b',
    r'function openDriverChatWidgetOld\b',
]

for pattern in funcs_to_remove:
    m = re.search(pattern, content)
    if not m:
        continue
    start = m.start()
    # Find the function keyword before it
    func_start = content.rfind('\n', 0, start) + 1
    # Find closing brace
    depth = 0
    i = start
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
                # Skip trailing newline
                if end < len(content) and content[end] == '\n':
                    end += 1
                break
        i += 1
    if end > 0:
        content = content[:func_start] + content[end:]
        print("Removed function:", pattern)

# Remove the large WebSocket block around line 1040 that still has driverTripWs = new WebSocket
# Find it
ws_block_start = '    try {\n        driverTripWs = new WebSocket(url);'
if ws_block_start in content:
    idx = content.find(ws_block_start)
    # Find the matching closing brace
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
                if end < len(content) and content[end] == '\n':
                    end += 1
                break
        i += 1
    if end > 0:
        content = content[:idx] + content[end:]
        print("Removed WebSocket try block")

# Remove remaining driverTripWs variable declarations
for var in ['let driverTripWs = null;\n', 'let driverTripWsShipmentId = null;\n', 'let driverTripPingTimer = null;\n']:
    content = content.replace(var, '', 1)

open('frontend/js/driver.js', 'w', encoding='utf-8').write(content)

# Syntax check
import subprocess
r = subprocess.run(['node', '--check', 'frontend/js/driver.js'], capture_output=True, text=True)
if r.returncode == 0:
    print("Syntax OK")
else:
    print("Syntax ERROR:", r.stderr[:500])

# Check remaining broken refs
broken = ['stopDriverTripLive', 'getWsShipmentUrl', 'appendDriverLiveChat', 'loadDriverChatHistory', 'driverTripWs', 'new WebSocket']
for b in broken:
    count = content.count(b)
    if count > 0:
        print(f"Still has {count}x: {b}")
