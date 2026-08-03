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
 *
 * Cada foto elegida se recomprime acá mismo (canvas, redimensionar +
 * reexportar como JPEG) antes de quedar lista para subir — las fotos de
 * cámara de celular suelen pesar 8-15MB, y los técnicos suben varias por
 * visita desde señal de campo débil. Si algo falla en el camino (formato
 * raro, canvas no disponible), se sube la foto original tal cual: nunca
 * bloquea la carga por un error de compresión.
 */
document.addEventListener('DOMContentLoaded', function () {
    var MAX_DIMENSION = 1920;
    var JPEG_QUALITY = 0.8;
    var UMBRAL_OMITIR_BYTES = 500 * 1024; // ya viene chica, no vale la pena reprocesarla

    function formatearTamano(bytes) {
        if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function comprimirImagen(file) {
        if (!file.type || file.type.indexOf('image/') !== 0 || file.size <= UMBRAL_OMITIR_BYTES) {
            return Promise.resolve(file);
        }
        return new Promise(function (resolve) {
            var url = URL.createObjectURL(file);
            var img = new Image();
            img.onload = function () {
                URL.revokeObjectURL(url);
                try {
                    var width = img.naturalWidth;
                    var height = img.naturalHeight;
                    if (width > MAX_DIMENSION || height > MAX_DIMENSION) {
                        if (width > height) {
                            height = Math.round(height * (MAX_DIMENSION / width));
                            width = MAX_DIMENSION;
                        } else {
                            width = Math.round(width * (MAX_DIMENSION / height));
                            height = MAX_DIMENSION;
                        }
                    }
                    var canvas = document.createElement('canvas');
                    canvas.width = width;
                    canvas.height = height;
                    var ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);
                    canvas.toBlob(function (blob) {
                        if (!blob || blob.size >= file.size) {
                            resolve(file);
                            return;
                        }
                        var nombre = file.name.replace(/\.\w+$/, '') + '.jpg';
                        resolve(new File([blob], nombre, { type: 'image/jpeg' }));
                    }, 'image/jpeg', JPEG_QUALITY);
                } catch (err) {
                    resolve(file);
                }
            };
            img.onerror = function () {
                URL.revokeObjectURL(url);
                resolve(file);
            };
            img.src = url;
        });
    }

    document.querySelectorAll('.selector-foto-doc').forEach(function (selector) {
        var inputs = Array.from(selector.querySelectorAll('input[type="file"]'));
        var texto = selector.querySelector('.texto-seleccion-doc');
        var multiple = selector.hasAttribute('data-multiple');
        var form = selector.closest('form');
        var procesando = null; // Promise en curso, para que el submit espere si hace falta

        function actualizarTexto(mensaje) {
            if (!texto) return;
            if (mensaje) {
                texto.textContent = mensaje;
                return;
            }
            var nombres = [];
            inputs.forEach(function (input) {
                Array.from(input.files).forEach(function (f) {
                    nombres.push(f.name + ' (' + formatearTamano(f.size) + ')');
                });
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
                if (!input.files.length) {
                    actualizarTexto();
                    return;
                }
                var archivos = Array.from(input.files);
                actualizarTexto(archivos.length > 1 ? 'Comprimiendo ' + archivos.length + ' fotos…' : 'Comprimiendo foto…');
                procesando = Promise.all(archivos.map(comprimirImagen)).then(function (comprimidas) {
                    var dt = new DataTransfer();
                    comprimidas.forEach(function (f) { dt.items.add(f); });
                    input.files = dt.files;
                    actualizarTexto();
                    procesando = null;
                });
            });
        });

        // Campo de una sola foto: si mandamos los dos <input name="foto">
        // tal cual, el que quedó vacío viaja igual en el POST (como un
        // archivo sin nombre) y el server puede terminar leyendo ese en
        // vez del que sí tiene la foto. Lo sacamos del envío recién al
        // mandar el formulario — así los dos siguen siendo clickeables
        // en todo momento mientras el técnico elige.
        if (form) {
            form.addEventListener('submit', function (ev) {
                if (!procesando) {
                    if (!multiple) {
                        inputs.forEach(function (input) {
                            if (!input.files.length) input.disabled = true;
                        });
                    }
                    return;
                }
                // Todavía comprimiendo (envío rápido en conexión lenta) —
                // frenamos este intento y lo reintentamos apenas termine.
                // form.submit() no dispara el evento 'submit' de nuevo (así
                // que evitar-doble-envio.js no llega a mostrar su propio
                // spinner acá) — por eso lo mostramos nosotros mismos.
                ev.preventDefault();
                if (form.dataset.reenvioProgramado === '1') return;
                form.dataset.reenvioProgramado = '1';
                var boton = form.querySelector('button[type="submit"], input[type="submit"]');
                if (boton) {
                    boton.disabled = true;
                    boton.innerHTML =
                        '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Comprimiendo...';
                }
                procesando.then(function () {
                    if (!multiple) {
                        inputs.forEach(function (input) {
                            if (!input.files.length) input.disabled = true;
                        });
                    }
                    form.submit();
                });
            });
        }
    });
});
