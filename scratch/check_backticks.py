import io

with io.open('c:/Mega/Proyect/Nucleus/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

in_script = False
for i, line in enumerate(lines):
    if '<script>' in line:
        in_script = True
    if '</script>' in line:
        in_script = False
    if in_script:
        cnt = line.count('`')
        if cnt % 2 != 0:
            print(f'Odd backtick at line {i+1}: {line.strip()[:120]}')
