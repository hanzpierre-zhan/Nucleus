"""Homologación por DNI, conservadora y sin coincidencias aproximadas."""
import re
import unicodedata


def dni(valor):
    valor = re.sub(r'[\s.\-]', '', str(valor or ''))
    return valor if re.fullmatch(r'\d{8}', valor) and len(set(valor)) > 1 else ''


def tokens(nombre):
    texto = unicodedata.normalize('NFKD', str(nombre or '')).encode('ascii', 'ignore').decode().lower()
    return frozenset(re.findall(r'[a-z]+', texto))


def nombre_completo(nombres):
    candidatos = {' '.join(str(n or '').split()) for n in nombres if str(n or '').strip()}
    if not candidatos:
        return None
    if any(re.search(r'\d', n) or tokens(n) & {'cochera', 'tarma', 'satipo', 'cm', 'sin', 'beneficiario'} for n in candidatos):
        return None
    mayor = max(candidatos, key=lambda n: (len(tokens(n)), len(n), n.casefold(), n))
    # El nombre corto solo se amplía si todas sus palabras están en el completo.
    if len(tokens(mayor)) < 2 or any(not tokens(n) <= tokens(mayor) for n in candidatos):
        return None
    return mayor


def aplicar(datos, catalogo):
    """Solo cambia el nombre visible; conserva DNI, formulario y correcciones."""
    if datos.get('_PERSONAL_CORRECCION_MANUAL'):
        return datos
    doc = dni(datos.get('Documento del beneficiario') or datos.get('DNI') or datos.get('DOCUMENTO'))
    entrada = catalogo.get(doc)
    if not entrada:
        return datos
    nombre = entrada['nombre']
    anterior = str(datos.get('Técnico beneficiario') or '')
    previo = datos.get('_BENEFICIARIO_HOMOLOGACION') or {}
    if anterior != nombre or previo:
        datos['_BENEFICIARIO_HOMOLOGACION'] = {
            'dni': doc, 'nombre': nombre, 'original': previo.get('original', anterior),
            'fuente': entrada['fuente'], 'lote': 'dni-nombres-20261029'}
        datos['Técnico beneficiario'] = nombre
    return datos
