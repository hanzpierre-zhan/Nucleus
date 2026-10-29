"""Correcciones de los datos de solicitud, separadas de las transiciones de estado."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation


def normalizar(campo):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(campo)).encode('ascii','ignore').decode().lower())


CAMPOS = {
    normalizar(c) for c in (
        'DEPARTAMENTO','Técnico beneficiario','Documento del beneficiario','Motivo de la solicitud',
        'Número CM / PM / PLM','Nombre de site','Monto total del depósito','Tipo de gasto','Tipo de presupuesto',
        'Titular de la cuenta','Número de cuenta o CCI','Número de celular o CCI','Numero de Yape/Plin',
        'Tipo de billetera digital','Tipo de depósito a realizar','Supervisor encargado','Observaciones (Form)',
        'Criticidad - Prioridad')
}


def validar_cambios(cambios, row):
    if not isinstance(cambios, dict) or not cambios or len(cambios)>30:
        raise ValueError('No hay correcciones válidas para guardar.')
    salida={}
    for campo, valor in cambios.items():
        if campo not in row and campo != 'DEPARTAMENTO':
            raise ValueError('El campo no pertenece a esta solicitud.')
        if normalizar(campo) not in CAMPOS:
            raise ValueError('Solo puedes corregir los datos de la solicitud; el flujo y el proyecto se mantienen protegidos.')
        if not isinstance(valor, str) or len(valor)>4000:
            raise ValueError('Los valores deben ser texto de hasta 4000 caracteres.')
        valor=valor.strip()
        if campo == 'Tipo de gasto':
            from services.rendicion_gastos import validar_manual
            validar_manual(valor)
        if normalizar(campo) in ('documentodelbeneficiario','tecnicobeneficiario') and not valor:
            raise ValueError('El documento y el técnico no pueden quedar vacíos.')
        if normalizar(campo)=='montototaldeldeposito':
            try:
                numero=Decimal(valor.replace(',','.'))
                if not numero.is_finite() or numero<0 or numero>Decimal('999999999.99'):
                    raise ValueError('Monto inválido.')
                valor=format(numero.quantize(Decimal('0.01')),'f')
            except (InvalidOperation, ValueError):
                raise ValueError('Ingresa un monto válido mayor o igual a cero.')
        salida[campo]=valor
    return salida
