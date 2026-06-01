import re

html = open('frontend/pages/driver.html', encoding='utf-8').read()
js   = open('frontend/js/driver.js', encoding='utf-8').read()

# Find all function calls in HTML onclick attributes
calls_raw = re.findall(r'onclick="([^"]+)"', html) + re.findall(r'onkeydown="([^"]+)"', html)
funcs_called = set()
for c in calls_raw:
    for m in re.findall(r'(\w+)\(', c):
        funcs_called.add(m)

# Find all function definitions in driver.js
defined = set(re.findall(r'(?:async\s+)?function\s+(\w+)\s*\(', js))
# Also check arrow functions assigned to variables
defined |= set(re.findall(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(', js))

skip = {'event', 'if', 'document', 'window', 'parseInt', 'parseFloat', 'Number', 'String', 'Boolean', 'Object', 'Array', 'Math', 'Date', 'JSON', 'console', 'alert', 'confirm', 'setTimeout', 'clearInterval', 'setInterval', 'fetch', 'URL', 'URLSearchParams', 'FormData', 'Promise', 'Error'}

missing = funcs_called - defined - skip
print("Functions called in HTML but NOT defined in driver.js:")
for f in sorted(missing):
    print("  MISSING:", f)
if not missing:
    print("  None - all OK")

# Also check for runtime errors - look for references to removed functions
removed = ['sendTripLiveChat', 'stopDriverTripLive', 'getWsShipmentUrl', 'startLiveTripFeed', 'openBidChat', 'appendDriverLiveChat', 'loadDriverChatHistory']
print("\nRemoved functions still referenced in driver.js:")
for f in removed:
    count = js.count(f)
    if count > 0:
        print(f"  {f}: {count} times")
if not any(js.count(f) > 0 for f in removed):
    print("  None - clean")
