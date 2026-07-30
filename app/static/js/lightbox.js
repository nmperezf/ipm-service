/*
 * Visor de fotos en la misma página: cualquier <a class="foto-lightbox">
 * que envuelva una <img> abre la foto en grande sobre un fondo oscuro, en
 * vez de abrir una pestaña nueva. Cerrar con la X, click afuera o Escape.
 */
document.addEventListener('DOMContentLoaded', function () {
    const overlay = document.createElement('div');
    overlay.className = 'lightbox-doc';
    overlay.innerHTML = '<button type="button" class="lightbox-doc-cerrar" aria-label="Cerrar">&times;</button><img alt="">';
    document.body.appendChild(overlay);
    const img = overlay.querySelector('img');

    function abrir(href, alt) {
        img.src = href;
        img.alt = alt || '';
        overlay.classList.add('activo');
        document.body.style.overflow = 'hidden';
    }

    function cerrar() {
        overlay.classList.remove('activo');
        document.body.style.overflow = '';
        img.src = '';
    }

    document.addEventListener('click', function (ev) {
        const enlace = ev.target.closest('a.foto-lightbox');
        if (enlace) {
            ev.preventDefault();
            const miniatura = enlace.querySelector('img');
            abrir(enlace.href, miniatura ? miniatura.alt : '');
        }
    });

    overlay.addEventListener('click', function (ev) {
        if (ev.target === overlay || ev.target.classList.contains('lightbox-doc-cerrar')) cerrar();
    });

    document.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape' && overlay.classList.contains('activo')) cerrar();
    });
});
