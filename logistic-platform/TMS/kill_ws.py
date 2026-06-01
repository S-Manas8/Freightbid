content = open('frontend/js/driver.js', encoding='utf-8').read()

# Find and remove syncDriverTripLive function entirely
start_marker = '\nfunction syncDriverTripLive('
end_marker   = '\n// ── My Rating'

s = content.find(start_marker)
e = content.find(end_marker)

if s != -1 and e != -1 and e > s:
    content = content[:s] + content[e:]
    print("Removed syncDriverTripLive block OK")
else:
    print("ERROR: markers not found", s, e)

# Remove remaining driverTripWs variable declarations
for var in [
    'let driverTripWs = null;\n',
    'let driverTripWsShipmentId = null;\n',
    'let driverTripPingTimer = null;\n',
]:
    if var in content:
        content = content.replace(var, '', 1)
        print("Removed:", var.strip())

open('frontend/js/driver.js', 'w', encoding='utf-8').write(content)

import subprocess
r = subprocess.run(['node', '--check', 'frontend/js/driver.js'], capture_output=True, text=True)
if r.returncode == 0:
    print("Syntax OK - driver.js is clean")
else:
    print("Syntax ERROR:", r.stderr[:300])
    # Show the error line
    lines = content.split('\n')
    import re
    m = re.search(r':(\d+)\n', r.stderr)
    if m:
        ln = int(m.group(1))
        print("Context around line", ln, ":")
        for i in range(max(0,ln-3), min(len(lines), ln+3)):
            print(f"  {i+1}: {lines[i]}")
