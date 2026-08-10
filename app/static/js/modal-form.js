/*
 * Ventana flotante para formularios de alta/edición rápida (nuevo cliente,
 * nueva instalación, cargar observación, nuevo equipo, visita manual...):
 * evita navegar a una pantalla aparte para una acción de un paso.
 *
 * Cualquier <a data-modal-form href="/ruta-del-form"> abre esa ruta dentro
 * del modal en lugar de navegar. Contrato con el backend (ver
 * app.utils.es_ajax):
 *   - GET  con header X-Requested-With: XMLHttpRequest -> el fragmento del
 *     <form>, sin el layout de base.html.
 *   - POST con ese mismo header, guardado exitoso -> JSON {ok, mensaje}.
 * Al guardar: cierra el modal, muestra un toast y refresca en el lugar el
 * contenedor #contenido-refrescable de la página (si existe), sin recargar.
 */
(function () {
    var backdrop, titulo, cuerpo;

    function ejecutarScripts(contenedor) {
        contenedor.querySelectorAll('script').forEach(function (viejo) {
            var nuevo = document.createElement('script');
            Array.from(viejo.attributes).forEach(function (attr) { nuevo.setAttribute(attr.name, attr.value); });
            nuevo.textContent = viejo.textContent;
            viejo.replaceWith(nuevo);
        });
    }

    function reinicializarAyudantes(contenedor) {
        // Orden importa: fotos-input debe engancharse antes que
        // evitar-doble-envio (ver comentario en fotos-input.js) para que un
        // envío con fotos todavía comprimiéndose no quede bloqueado.
        window.inicializarSelectorFotos && window.inicializarSelectorFotos(contenedor);
        window.inicializarEvitarDobleEnvio && window.inicializarEvitarDobleEnvio(contenedor);
        window.inicializarConfirmarPassword && window.inicializarConfirmarPassword(contenedor);
        // tablas.js no usa delegación de eventos (a diferencia de
        // lightbox.js, que sí y no necesita nada acá): cualquier
        // <table class="data-table"> nueva necesita este init explícito.
        if (window.initTabla) contenedor.querySelectorAll('table.data-table').forEach(window.initTabla);
    }

    function mostrarToast(mensaje) {
        var cont = document.getElementById('toast-contenedor-doc');
        if (!cont || !mensaje) return;
        var toast = document.createElement('div');
        toast.className = 'toast-doc';
        toast.textContent = mensaje;
        cont.appendChild(toast);
        requestAnimationFrame(function () { toast.classList.add('mostrado'); });
        setTimeout(function () {
            toast.classList.remove('mostrado');
            setTimeout(function () { toast.remove(); }, 300);
        }, 3200);
    }

    function refrescarContenido() {
        // El contenedor en sí no se reemplaza (solo su innerHTML), así que
        // cualquier dato que la página haya guardado en su propio dataset
        // (ej. qué cliente estaba seleccionado) sigue disponible después del
        // refresh para que el init de la página lo restaure si quiere.
        var cont = document.getElementById('contenido-refrescable');
        if (!cont || !cont.dataset.fragmentoUrl) return;
        fetch(cont.dataset.fragmentoUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.text(); })
            .then(function (html) {
                cont.innerHTML = html;
                ejecutarScripts(cont);
                reinicializarAyudantes(cont);
                enlazarDisparadores(cont);
                cont.dispatchEvent(new CustomEvent('contenido-refrescado'));
            });
    }

    function cerrarModal() {
        backdrop.classList.remove('abierta');
        cuerpo.innerHTML = '';
    }

    function inyectarFormulario(url, html) {
        cuerpo.innerHTML = html;
        var tituloEl = cuerpo.querySelector('[data-modal-titulo]');
        titulo.textContent = tituloEl ? tituloEl.dataset.modalTitulo : '';
        ejecutarScripts(cuerpo);
        reinicializarAyudantes(cuerpo);

        cuerpo.querySelectorAll('a.btn-link').forEach(function (a) {
            a.addEventListener('click', function (e) { e.preventDefault(); cerrarModal(); });
        });

        var form = cuerpo.querySelector('form');
        if (!form) return;
        form.addEventListener('submit', function (e) {
            if (e.defaultPrevented) return; // otro handler (ej. fotos-input comprimiendo) ya lo frenó
            e.preventDefault();
            var boton = form.querySelector('button[type="submit"], input[type="submit"]');
            var accion = form.getAttribute('action') || url;
            fetch(accion, {
                method: 'POST',
                body: new FormData(form),
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            }).then(function (r) {
                if (r.status === 400) {
                    return r.text().then(function (html) {
                        inyectarFormulario(accion, html);
                        throw 'validacion';
                    });
                }
                if (!r.ok) throw new Error('error de red');
                return r.json();
            }).then(function (data) {
                cerrarModal();
                mostrarToast(data && data.mensaje);
                refrescarContenido();
            }).catch(function (err) {
                if (err === 'validacion') return; // ya se reinyectó el form con sus errores
                if (boton) { boton.disabled = false; boton.innerHTML = boton.dataset.textoOriginal || boton.innerHTML; }
                mostrarToast('No se pudo guardar. Probá de nuevo.');
            });
        });
    }

    function cargarFormulario(url) {
        titulo.textContent = '';
        cuerpo.innerHTML = '<p class="text-muted mb-0">Cargando…</p>';
        backdrop.classList.add('abierta');
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.text(); })
            .then(function (html) { inyectarFormulario(url, html); })
            .catch(function () {
                cuerpo.innerHTML = '<p class="text-danger mb-0">No se pudo cargar el formulario.</p>';
            });
    }

    function enlazarDisparadores(root) {
        (root || document).querySelectorAll('[data-modal-form]').forEach(function (el) {
            if (el.dataset.modalFormListo === '1') return;
            el.dataset.modalFormListo = '1';
            el.addEventListener('click', function (e) {
                if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
                e.preventDefault();
                cargarFormulario(el.dataset.modalForm || el.getAttribute('href'));
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        backdrop = document.getElementById('modal-form-backdrop');
        if (!backdrop) return;
        titulo = document.getElementById('modal-form-titulo');
        cuerpo = document.getElementById('modal-form-cuerpo');

        window.cerrarModalFormulario = cerrarModal;
        window.abrirModalFormulario = cargarFormulario;
        window.mostrarToast = mostrarToast;
        backdrop.addEventListener('click', function (e) { if (e.target === backdrop) cerrarModal(); });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && backdrop.classList.contains('abierta')) cerrarModal();
        });

        enlazarDisparadores(document);
    });
})();
