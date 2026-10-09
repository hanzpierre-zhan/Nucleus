/* Respuestas de API: no confundir errores HTTP o sesión vencida con fallos de red. */
window.nucleusLeerRespuestaJSON = async function(response) {
    if (response.status === 401 || (response.redirected && /\/login(?:[/?#]|$)/.test(response.url))) {
        // Recuperar el acceso directamente, sin abrir avisos repetidos.
        window.location.assign('/login');
        return new Promise(() => {});
    }
    const text = await response.text();
    try {
        const data = JSON.parse(text);
        if (!data || typeof data !== 'object') throw new Error('Respuesta inválida');
        return data;
    } catch (error) {
        const messages = {
            404: 'La función solicitada no está disponible en esta versión del servidor.',
            413: 'El archivo supera el tamaño permitido.',
            502: 'El servidor no está disponible temporalmente (HTTP 502). Reintenta en unos momentos.',
            503: 'El servidor no está disponible temporalmente (HTTP 503). Reintenta en unos momentos.',
            504: 'El servidor tardó demasiado en responder (HTTP 504). Comprueba el estado del registro antes de reintentar.'
        };
        throw new Error(messages[response.status] || `El servidor devolvió una respuesta inesperada (HTTP ${response.status}).`);
    }
};
window.nucleusErrorSolicitud = function(error) {
    return error instanceof TypeError ? 'No se pudo contactar con el servidor. Revisa tu conexión y reintenta.' : (error.message || 'No se pudo completar la solicitud.');
};
