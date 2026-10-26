"""Arranque de Render: puerto público explícito y aplicación cargada en el worker."""
import os

bind = '0.0.0.0:' + str(int(os.environ.get('PORT', '10000')))
workers = 1
worker_class = 'gthread'
threads = 4
timeout = 300
preload_app = False
accesslog = '-'
errorlog = '-'
capture_output = True


def when_ready(server):
    server.log.info('Nucleus: puerto abierto en %s; iniciando aplicación.', bind)


def post_worker_init(worker):
    worker.log.info('Nucleus: aplicación inicializada y lista para responder.')
