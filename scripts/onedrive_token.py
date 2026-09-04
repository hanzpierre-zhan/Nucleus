import os
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error

BASE = 'https://login.microsoftonline.com/common/oauth2/v2.0'
SCOPE = 'Files.ReadWrite offline_access'

def post(url, datos):
    body = urllib.parse.urlencode(datos).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))

def main():
    client_id = os.environ.get('OD_CLIENT_ID', '').strip()
    if not client_id:
        client_id = input('Pega aqui el Application (client) ID de Azure: ').strip()
    if not client_id:
        print('Sin client ID, no se puede continuar.')
        sys.exit(1)
    if os.environ.get('OD_CLIENT_SECRET', '').strip():
        print('Tambien se usara el client secret de la variable OD_CLIENT_SECRET.')

    dc = post(BASE + '/devicecode', {'client_id': client_id, 'scope': SCOPE})
    print('\n1) Abre esta pagina: ' + dc['verification_uri'])
    print('2) Ingresa este codigo: ' + dc['user_code'])
    print('\nEsperando que autorices en tu cuenta personal...')

    payload = {
        'client_id': client_id,
        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
        'device_code': dc['device_code'],
    }
    intervalo = max(int(dc.get('interval', 5)), 3)
    intentos = int(dc.get('expires_in', 900)) // intervalo
    for _ in range(intentos):
        time.sleep(intervalo)
        try:
            r = post(BASE + '/token', payload)
            print('\n===== TU REFRESH TOKEN =====')
            print(r.get('refresh_token', ''))
            print('=============================')
            print('\nPegalo en la variable OD_REFRESH_TOKEN de Render.')
            sys.exit(0)
        except urllib.error.HTTPError as e:
            err = json.loads(e.read().decode('utf-8'))
            codigo = err.get('error', '')
            if codigo == 'authorization_pending':
                continue
            if codigo == 'authorization_declined':
                print('Autorizacion rechazada.')
                sys.exit(1)
            print('Error:', err)
            sys.exit(1)
    print('Se agoto el tiempo de espera.')

if __name__ == '__main__':
    main()