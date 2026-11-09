"""Crea una solicitud de ejemplo de Caja Chica en Validación (solo local).

Uso: python scratch/ejemplo_caja_chica_validacion.py
"""
import os
import sys
from pathlib import Path

os.environ.pop('DATABASE_URL', None)  # fuerza la base local nucleus.db
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app
from blueprints.caja_chica import PROYECTOS, BANCOS
from blueprints import caja_chica as bp
from services import caja_chica as cc
from services.formularios_prueba import importe

MOTIVO = '[EJEMPLO] Revisar el selector de Tiempo de respuesta en Validación.'


def main():
    with app.app_context():
        existente = cc.CajaChicaSolicitud.query.filter_by(motivo=MOTIVO).first()
        if existente:
            print('Ya existe:', existente.codigo, 'id', existente.id)
            return
        modulo, config = bp._config_catalogo()
        catalogo = bp._catalogo(config)
        datos = {
            'proyecto': 'CLARO',
            'motivo': MOTIVO,
            'banco': 'BCP',
            'cuenta': '00240519113894502798',
            'items': [
                {'tipo_gasto': 'Compra de materiales y/o repuestos', 'monto': '185.50',
                 'descripcion': 'Cable y conectores para el site'},
                {'tipo_gasto': 'Peajes', 'monto': '24.00', 'descripcion': 'Peaje ida y vuelta'},
            ],
            'site': 'ZZ9901_PRUEBA',
            'wo': 'CM-20261109-00009901',
            'tipo_billetera': 'No aplica',
            'numero_billetera': '',
            'responsable_validacion': '',
        }
        formulario = cc.datos_formulario(datos, 'SUPERVISOR DE PRUEBA', {})
        tecnico = {'documento': '45963666', 'nombre': 'HUANCAPAZA CONDORI, ELOY', 'proyecto': 'FLM - CLARO'}
        sol = cc.crear(tecnico, datos, catalogo, PROYECTOS, BANCOS, importe, formulario)
        print('Creada:', sol.codigo, 'id', sol.id, 'total', sol.total)


if __name__ == '__main__':
    main()
