/*
 * Selector de foto con dos caminos explícitos: "Tomar foto" (dispara la
 * cámara vía capture="environment") y "Elegir de galería" (input normal,
 * sin capture). Se aplica a cualquier <div class="selector-foto-doc"> que
 * envuelva uno o más <input type="file">, sin necesidad de ids.
 *
 * data-multiple en el wrapper: si está, elegir por un camino no borra lo
 * ya elegido por el otro (se puede sumar cámara + galería). Si no está,
 * es un campo de una sola foto: elegir por un camino limpia el otro para
 * que no quede ambigüedad de cuál se termina mandando.
 */
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.selector-foto-doc').forEach(function (selector) {
        const inputs = Array.from(selector.querySelectorAll('input[type="file"]'));
        const texto = selector.querySelector('.texto-seleccion-doc');
        const multiple = selector.hasAttribute('data-multiple');
        const form = selector.closest('form');

        function actualizarTexto() {
            if (!texto) return;
            const nombres = [];
            inputs.forEach(function (input) {
                Array.from(input.files).forEach(function (f) { nombres.push(f.name); });
            });
            texto.textContent = nombres.length ? nombres.length + ' foto(s) elegida(s): ' + nombres.join(', ') : '';
        }

        inputs.forEach(function (input) {
            input.addEventListener('change', function () {
                if (!multiple) {
                    inputs.forEach(function (otro) {
                        if (otro !== input) otro.value = '';
                    });
                }
                actualizarTexto();
            });
        });

        // Campo de una sola foto: si mandamos los dos <input name="foto">
        // tal cual, el que quedó vacío viaja igual en el POST (como un
        // archivo sin nombre) y el server puede terminar leyendo ese en
        // vez del que sí tiene la foto. Lo sacamos del envío recién al
        // mandar el formulario — así los dos siguen siendo clickeables
        // en todo momento mientras el técnico elige.
        if (form && !multiple) {
            form.addEventListener('submit', function () {
                inputs.forEach(function (input) {
                    if (!input.files.length) input.disabled = true;
                });
            });
        }
    });
});
