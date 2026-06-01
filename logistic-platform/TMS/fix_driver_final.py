content = open('frontend/js/driver.js', encoding='utf-8').read()

# Find the new clean chat code we added
new_chat_start = '// ── Driver Chat Widget (polling-based) ───────────────────────'
new_chat_end   = "    } catch(e) {\n        showToast('Failed to send: ' + e.message, 'error');\n    }\n}"

start_idx = content.find(new_chat_start)
end_idx   = content.find(new_chat_end)

if start_idx == -1:
    print("ERROR: new chat start not found")
    exit()
if end_idx == -1:
    print("ERROR: new chat end not found")
    exit()

# Everything after end_idx + len(new_chat_end) is old broken code
end_of_new = end_idx + len(new_chat_end)
old_remaining = content[end_of_new:]
print("Old remaining code length:", len(old_remaining))
print("First 200 chars of old remaining:", repr(old_remaining[:200]))

# Keep only up to end of new chat code
content = content[:end_of_new] + '\n'
open('frontend/js/driver.js', 'w', encoding='utf-8').write(content)

# Verify
content2 = open('frontend/js/driver.js', encoding='utf-8').read()
broken = ['driverChatWs', 'appendDriverChatMsgWidget', 'WebSocket(wsUrl)']
for b in broken:
    count = content2.count(b)
    print(f'{b}: {count} occurrences')

# Also check the live trip WS code
ws_count = content2.count('driverTripWs')
print(f'driverTripWs: {ws_count} occurrences')
print('File size:', len(content2), 'chars, lines:', content2.count(chr(10)))
print('Done')
