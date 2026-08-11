/*
 * Foto ligada a un punto puntual del checklist (no al equipo en general):
 * ver campo "requiere_foto" en TipoFormulario/ServicioTipo. Sube por AJAX
 * al mismo endpoint que la foto general de la visita (fotos.subir), sin
 * recargar la pantalla -- el checklist puede tener muchos campos sin
 * guardar todavía, y una navegación de página completa los perdería.
 *
 * A diferencia de fotos-input.js (selector-foto-doc, usado por el form de
 * "Fotos" de la visita), acá no hay compresión del lado del cliente: sube
 * el archivo tal cual. Es un trade-off deliberado -- este widget dispara
 * la subida apenas se elige el archivo (no hay botón "enviar" que esperar
 * a que la compresión async termine), y evitar esa carrera es más simple
 * subiendo directo. Para cargas masivas de fotos pesadas sigue estando el
 * flujo de siempre (con compresión) en la sección "Fotos" de la visita.
 */
function inicializarFotosCampo(root) {
    (root || document).querySelectorAll('.widget-foto-campo').forEach(function (widget) {
        if (widget.dataset.fotoCampoListo === '1') return;
        widget.dataset.fotoCampoListo = '1';

        var input = widget.querySelector('input[type="file"]');
        var miniaturas = widget.querySelector('.miniaturas-foto-campo');
        var boton = widget.querySelector('.btn-foto-campo');
        var urlSubir = widget.dataset.urlSubir;
        var urlEliminarPlantilla = widget.dataset.urlEliminarPlantilla; // .../0/eliminar -- 0 se reemplaza por el id real

        function enlazarQuitar(mini) {
            var boton = mini.querySelector('.quitar');
            boton.addEventListener('click', function () {
                if (!confirm('¿Quitar esta foto?')) return;
                var url = urlEliminarPlantilla.replace('0', mini.dataset.fotoId);
                fetch(url, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.ok) { mini.remove(); return; }
                        if (window.mostrarToast) window.mostrarToast(data.mensaje || 'No se pudo quitar la foto.');
                    })
                    .catch(function () {
                        if (window.mostrarToast) window.mostrarToast('No se pudo quitar la foto.');
                    });
            });
        }

        miniaturas.querySelectorAll('.miniatura-foto').forEach(enlazarQuitar);

        input.addEventListener('change', function () {
            var archivo = input.files[0];
            if (!archivo) return;
            var datos = new FormData();
            datos.append('foto', archivo);
            datos.append('equipo_id', widget.dataset.equipo);
            datos.append('campo_formulario', widget.dataset.campo);

            var textoOriginal = boton.innerHTML;
            boton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
            boton.classList.add('disabled');

            fetch(urlSubir, { method: 'POST', body: datos, headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    boton.innerHTML = textoOriginal;
                    boton.classList.remove('disabled');
                    input.value = '';
                    if (!data.ok) {
                        if (window.mostrarToast) window.mostrarToast(data.mensaje || 'No se pudo subir la foto.');
                        return;
                    }
                    var mini = document.createElement('div');
                    mini.className = 'miniatura-foto';
                    mini.dataset.fotoId = data.foto_id;
                    mini.innerHTML =
                        '<a href="' + data.url + '" target="_blank"><img src="' + data.url + '" alt=""></a>' +
                        '<button type="button" class="quitar" title="Quitar">✕</button>';
                    miniaturas.appendChild(mini);
                    enlazarQuitar(mini);
                    if (window.mostrarToast) window.mostrarToast('Foto subida.');
                })
                .catch(function () {
                    boton.innerHTML = textoOriginal;
                    boton.classList.remove('disabled');
                    input.value = '';
                    if (window.mostrarToast) window.mostrarToast('No se pudo subir la foto.');
                });
        });
    });
}
window.inicializarFotosCampo = inicializarFotosCampo;
document.addEventListener('DOMContentLoaded', function () { inicializarFotosCampo(document); });
