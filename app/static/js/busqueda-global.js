// Buscador global de la topbar (desktop) y del menú hamburguesa (mobile):
// cada contenedor .buscador-global se comporta igual, con su propio panel
// flotante -- mismo patrón fetch-AJAX-a-fragmento que ya usa la campanita
// de notificaciones (ver notificaciones.resumen), sin backdrop de página
// completa porque esto se siente como un autocompletar, no un modal.
(function () {
    var urlBuscar = document.currentScript.getAttribute('data-url-buscar');
    if (!urlBuscar) return;

    var DEBOUNCE_MS = 300;

    document.querySelectorAll('[data-buscador-global]').forEach(function (contenedor) {
        var input = contenedor.querySelector('.input-busqueda-global');
        var panel = contenedor.querySelector('.panel-busqueda-global');
        var temporizador = null;
        var ultimaQuery = null;

        function cerrarPanel() {
            panel.classList.remove('abierto');
        }

        function buscar(q) {
            fetch(urlBuscar + '?q=' + encodeURIComponent(q), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function (r) { return r.text(); })
                .then(function (html) {
                    panel.innerHTML = html;
                    panel.classList.add('abierto');
                })
                .catch(function () {
                    panel.innerHTML = '<p class="text-danger mb-0 small">No se pudo buscar.</p>';
                    panel.classList.add('abierto');
                });
        }

        input.addEventListener('input', function () {
            var q = input.value.trim();
            ultimaQuery = q;
            clearTimeout(temporizador);
            if (q.length < 2) {
                cerrarPanel();
                return;
            }
            temporizador = setTimeout(function () {
                if (input.value.trim() === q) buscar(q);
            }, DEBOUNCE_MS);
        });

        input.addEventListener('focus', function () {
            if (panel.innerHTML.trim() && input.value.trim().length >= 2) panel.classList.add('abierto');
        });

        input.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                cerrarPanel();
                input.blur();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                var primerResultado = panel.querySelector('.lista-resultado-busqueda a');
                if (primerResultado) window.location.href = primerResultado.getAttribute('href');
            }
        });

        document.addEventListener('click', function (e) {
            if (!contenedor.contains(e.target)) cerrarPanel();
        });
    });
})();
