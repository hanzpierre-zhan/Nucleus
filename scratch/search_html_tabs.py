import io

with io.open('c:/Mega/Proyect/Nucleus/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "'Resguardo'" in line or '"Resguardo"' in line or "'Estado'" in line or '"Estado"' in line or "Gastos" in line:
        if '[' in line or '{' in line or 'tab' in line.lower() or 'pest' in line.lower() or 'btn' in line.lower() or 'button' in line.lower() or 'push' in line.lower():
            print(f"{i+1}: {line.strip()}")
