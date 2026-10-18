import subprocess
import sys


def test_red_externa_bloqueada_en_proceso_aislado():
    resultado = subprocess.run([sys.executable, '-c', '''
from services.sandbox import instalar_bloqueo_red
import socket
instalar_bloqueo_red()
for host in ('example.com','8.8.8.8'):
    try:
        socket.getaddrinfo(host,443)
    except PermissionError:
        continue
    raise AssertionError('Se permitió un destino externo')
assert socket.getaddrinfo('127.0.0.1',5058)
'''],capture_output=True,text=True,timeout=10)
    assert resultado.returncode == 0, resultado.stderr
