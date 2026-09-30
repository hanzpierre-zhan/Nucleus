import sqlite3, json
db = sqlite3.connect('nucleus.db')
c = db.cursor()
c.execute("SELECT data_json FROM nucleus_data WHERE key_value = '29/9/2026 15:41:05'")
row = c.fetchone()
raw = row[0]
# Print the raw bytes of a section with accented key
idx = raw.index('cnico')
print("Bytes around 'cnico':", [hex(b) for b in raw[max(0,idx-3):idx+8].encode('utf-8')])
# Find the actual character
print("Chars:", [repr(ch) for ch in raw[max(0,idx-3):idx+8]])
# Print exact unicode codepoints
for ch in raw[max(0,idx-3):idx+8]:
    print(f'  U+{ord(ch):04X} = {repr(ch)}')
