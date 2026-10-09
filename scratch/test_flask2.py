import urllib.request
import urllib.parse
import http.cookiejar

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

# Get the login page first to check for CSRF token
r = opener.open('http://127.0.0.1:5001/login', timeout=10)
body = r.read(5000).decode('utf-8', errors='replace')

# Find CSRF token if present
import re
csrf = re.search(r'name=["\']csrf_token["\'] value=["\']([^"\']+)["\']', body)
csrf_token = csrf.group(1) if csrf else ''
print('CSRF token found:', bool(csrf_token))

# Try login with first user found in DB
import sqlite3
conn = sqlite3.connect('c:/Mega/Proyect/Nucleus/nucleus.db')
c = conn.cursor()
c.execute("SELECT nombre_usuario, contrasena FROM usuario LIMIT 3")
users = c.fetchall()
conn.close()
print('Users found:', [(u[0], u[1][:10]) for u in users])

for user, pw in users:
    params = {'usuario': user, 'password': pw}
    if csrf_token:
        params['csrf_token'] = csrf_token
    login_data = urllib.parse.urlencode(params).encode()
    try:
        r = opener.open('http://127.0.0.1:5001/login', login_data, timeout=10)
        body_l = r.read(2000).decode('utf-8', errors='replace')
        if 'Log in' not in body_l and 'login' not in r.url.lower():
            print(f'Login OK with {user}')
            # Now try main page
            r2 = opener.open('http://127.0.0.1:5001/', timeout=10)
            body2 = r2.read(20000).decode('utf-8', errors='replace')
            print('Main page status:', r2.status)
            # Check for Jinja2/Python errors
            if 'UndefinedError' in body2 or 'TemplateError' in body2 or 'Traceback' in body2:
                idx = max(body2.find('UndefinedError'), body2.find('TemplateError'), body2.find('Traceback'))
                print('TEMPLATE ERROR:', body2[max(0, idx-50):idx+500])
            else:
                print('No template errors found in page')
                # Check for the rawData
                if 'rawData' in body2:
                    idx = body2.find('const rawData')
                    print('rawData line:', body2[idx:idx+100])
            break
        else:
            pass
    except Exception as e:
        print(f'Error with {user}:', e)
