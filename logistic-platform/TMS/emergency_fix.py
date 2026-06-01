"""Emergency fix: find and replace the broken openDriverChatWidget and remove connectDriverChatSocket."""
import re, subprocess

content = open('frontend/js/driver.js', encoding='utf-8').read()

# Find openDriverChatWidget and replace its body
# Find the function start
idx = content.find('async function openDriverChatWidget(')
if idx == -1:
    print("openDriverChatWidget not found")
else:
    # Find the closing brace
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
    
    old_func = content[idx:end]
    new_func = """async function openDriverChatWidget(shipmentId, displayTitle) {
    driverChatShipmentId = shipmentId;
    const widget = document.getElementById('driver-chat-widget');
    if (!widget) return;
    widget.style.display = 'flex';
    const meta = document.getElementById('driver-chat-meta');
    if (meta) meta.textContent = displayTitle || 'Chat with Shipper';
    const status = document.getElementById('driver-chat-status');
    if (status) { status.textContent = 'Connected'; status.style.color = '#22c55e'; }
    await refreshDriverChat();
    if (driverChatPollInterval) clearInterval(driverChatPollInterval);
    driverChatPollInterval = setInterval(refreshDriverChat, 5000);
}"""
    content = content[:idx] + new_func + content[end:]
    print("Replaced openDriverChatWidget OK")

# Remove connectDriverChatSocket function
for func_name in ['function connectDriverChatSocket(', 'async function loadDriverChatHistoryWidget(']:
    idx2 = content.find(func_name)
    if idx2 == -1:
        print("Not found:", func_name)
        continue
    # Find function start (go back to find 'async' or 'function')
    func_start = content.rfind('\n', 0, idx2) + 1
    depth = 0
    i = idx2
    found_open = False
    end2 = -1
    while i < len(content):
        if content[i] == '{':
            depth += 1
            found_open = True
        elif content[i] == '}':
            depth -= 1
            if found_open and depth == 0:
                end2 = i + 1
                if end2 < len(content) and content[end2] == '\n':
                    end2 += 1
                break
        i += 1
    if end2 > 0:
        content = content[:func_start] + content[end2:]
        print("Removed:", func_name)

# Remove driverChatSocketShipmentId variable
content = content.replace('let driverChatSocketShipmentId = null;\n', '', 1)

# Add driverChatPollInterval if not present
if 'let driverChatPollInterval' not in content:
    content = content.replace('let driverChatShipmentId   = null;\n',
                               'let driverChatShipmentId   = null;\nlet driverChatPollInterval = null;\n', 1)

open('frontend/js/driver.js', 'w', encoding='utf-8').write(content)

r = subprocess.run(['node', '--check', 'frontend/js/driver.js'], capture_output=True, text=True)
if r.returncode == 0:
    print("driver.js: Syntax OK")
else:
    print("driver.js: Syntax ERROR:", r.stderr[:300])
    lines = content.split('\n')
    m = re.search(r':(\d+)\n', r.stderr)
    if m:
        ln = int(m.group(1))
        for i in range(max(0,ln-3), min(len(lines), ln+3)):
            print(f"  {i+1}: {lines[i]}")
