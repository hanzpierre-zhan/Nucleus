import urllib.request
import urllib.parse
import http.cookiejar

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

# Try with correct credentials (try different combos)
for user, pw in [('admin', 'admin'), ('zeno', 'zeno'), ('admin', '1234'), ('zeno', '1234')]:
    login_data = urllib.parse.urlencode({'usuario': user, 'password': pw}).encode()
    try:
        r = opener.open('http://127.0.0.1:5001/login', login_data, timeout=10)
        body = r.read(3000).decode('utf-8', errors='replace')
        if 'login' not in r.url.lower() and 'Log in' not in body[:500]:
            print(f'Login OK with {user}/{pw}')
            print('URL after login:', r.url)
            break
        else:
            print(f'Login FAILED with {user}/{pw}')
    except Exception as e:
        print(f'Error with {user}/{pw}:', e)

# Try main page after login
try:
    r = opener.open('http://127.0.0.1:5001/', timeout=10)
    body = r.read(2000).decode('utf-8', errors='replace')
    print('Main page URL:', r.url)
    print('Status:', r.status)
    print('First 500 chars:', body[:500])
except Exception as e:
    print('Main page error:', e)
