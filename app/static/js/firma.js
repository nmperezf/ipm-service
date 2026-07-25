/*
 * Captura de firma digital en un <canvas>, pensado para tablet/celular
 * (eventos de puntero, funciona con dedo o mouse). Al enviar el formulario,
 * vuelca el dibujo a un input oculto como PNG en base64.
 */
function iniciarFirma(idCanvas, idInputOculto, idBotonLimpiar) {
    const canvas = document.getElementById(idCanvas);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#1A2233';

    let dibujando = false;
    let huboTrazo = false;

    function posicion(evento) {
        const rect = canvas.getBoundingClientRect();
        return { x: evento.clientX - rect.left, y: evento.clientY - rect.top };
    }

    canvas.addEventListener('pointerdown', function (e) {
        dibujando = true;
        huboTrazo = true;
        const p = posicion(e);
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener('pointermove', function (e) {
        if (!dibujando) return;
        const p = posicion(e);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
    });
    canvas.addEventListener('pointerup', function () { dibujando = false; });
    canvas.addEventListener('pointerleave', function () { dibujando = false; });

    const limpiar = document.getElementById(idBotonLimpiar);
    if (limpiar) {
        limpiar.addEventListener('click', function () {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            huboTrazo = false;
        });
    }

    const formulario = canvas.closest('form');
    if (formulario) {
        formulario.addEventListener('submit', function () {
            const input = document.getElementById(idInputOculto);
            if (input && huboTrazo) {
                input.value = canvas.toDataURL('image/png');
            }
        });
    }
}
