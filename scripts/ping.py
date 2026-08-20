import urllib.request

url = 'https://nucleus-j2cv.onrender.com/healthz'
try:
    with urllib.request.urlopen(url, timeout=120) as resp:
        print('PING OK', resp.status)
except Exception as e:
    print('PING ERROR', e)