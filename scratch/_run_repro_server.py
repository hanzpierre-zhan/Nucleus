# Runner temporal para reproducir en un puerto libre y sin recargador.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('PORT', '5020')
from app import app

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ['PORT']),
            debug=False, use_reloader=False, threaded=True)
