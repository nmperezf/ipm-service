/*
 * Evita cargas duplicadas por doble-toque (típico con mala señal en el
 * lugar de trabajo): al enviar cualquier formulario, el botón de submit
 * se deshabilita y muestra un spinner hasta que la página siguiente cargue.
 * No se aplica a formularios marcados con data-sin-bloqueo (por si algún
 * caso puntual necesita reenviarse rápido, como filtros).
 *
 * inicializarEvitarDobleEnvio(root) queda expuesta globalmente para que los
 * formularios cargados dentro de una ventana flotante (ver modal-form.js)
 * puedan sumarse sin esperar un segundo DOMContentLoaded, que no vuelve a
 * dispararse para contenido inyectado después de la carga inicial.
 */
function inicializarEvitarDobleEnvio(root) {
    (root || document).querySelectorAll('form').forEach(function (formulario) {
        if (formulario.dataset.dobleEnvioListo === '1') return;
        formulario.dataset.dobleEnvioListo = '1';
        if (formulario.hasAttribute('data-sin-bloqueo')) return;

        formulario.addEventListener('submit', function (evento) {
            // Si un onsubmit anterior (ej. un confirm() de "¿Eliminar?") ya
            // canceló el envío, no tocamos el botón.
            if (evento.defaultPrevented) return;

            if (formulario.dataset.enviando === '1') {
                evento.preventDefault();
                return;
            }
            // Si el navegador va a bloquear el envío por validación HTML5,
            // no tocamos el botón — si no, queda deshabilitado para siempre.
            if (formulario.checkValidity && !formulario.checkValidity()) return;

            formulario.dataset.enviando = '1';
            const boton = formulario.querySelector('button[type="submit"], input[type="submit"]');
            if (boton) {
                boton.dataset.textoOriginal = boton.innerHTML;
                boton.disabled = true;
                boton.innerHTML =
                    '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Guardando...';
            }
        });
    });
}
window.inicializarEvitarDobleEnvio = inicializarEvitarDobleEnvio;
document.addEventListener('DOMContentLoaded', function () { inicializarEvitarDobleEnvio(document); });
