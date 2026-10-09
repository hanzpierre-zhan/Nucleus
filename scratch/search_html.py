import io

with io.open('c:/Mega/Proyect/Nucleus/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("--- Resguardo ---")
for i, line in enumerate(lines):
    if 'Resguardo' in line and ('<button' in line or '<li' in line or 'tab' in line.lower() or 'pestania' in line.lower() or 'pest' in line.lower()):
        print(f"{i+1}: {line.strip()}")

print("--- Estado ---")
for i, line in enumerate(lines):
    if 'Estado' in line and ('<button' in line or '<li' in line or 'tab' in line.lower() or 'pestania' in line.lower() or 'pest' in line.lower()):
        print(f"{i+1}: {line.strip()}")

print("--- Departamento ---")
for i, line in enumerate(lines):
    if 'Departamento' in line:
        print(f"{i+1}: {line.strip()}")
