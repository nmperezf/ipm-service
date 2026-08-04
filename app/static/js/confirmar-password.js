/*
 * Doble confirmación para eliminar registros de alto impacto: cualquier
 * <form class="form-confirmar-password"> intercepta su propio submit, pide
 * la contraseña en un modal compartido y recién ahí manda el POST real con
 * un campo oculto "password" agregado — el backend la valida de nuevo
 * (ver auth_utils.verificar_password_confirmacion).
 *
 * inicializarConfirmarPassword(root) queda expuesta globalmente para que los
 * formularios cargados dentro de una ventana flotante (ver modal-form.js)
 * también queden enganchados al modal compartido de confirmación.
 */
(function () {
    var modal = null;
    var mensajeEl, inputEl, formModal;
    var formPendiente = null;

    function asegurarModal() {
        if (modal) return true;
        var modalEl = document.getElementById('modal-confirmar-password');
        if (!modalEl) return false;
        modal = new bootstrap.Modal(modalEl);
        mensajeEl = document.getElementById('modal-confirmar-password-mensaje');
        inputEl = document.getElementById('modal-confirmar-password-input');
        formModal = document.getElementById('form-modal-confirmar-password');

        formModal.addEventListener('submit', function (e) {
            e.preventDefault();
            if (!formPendiente || !inputEl.value) return;
            var oculto = document.createElement('input');
            oculto.type = 'hidden';
            oculto.name = 'password';
            oculto.value = inputEl.value;
            formPendiente.appendChild(oculto);
            modal.hide();
            if (formPendiente.requestSubmit) formPendiente.requestSubmit();
            else formPendiente.submit();
        });
        return true;
    }

    window.inicializarConfirmarPassword = function (root) {
        if (!asegurarModal()) return;
        (root || document).querySelectorAll('form.form-confirmar-password').forEach(function (form) {
            if (form.dataset.confirmarPasswordListo === '1') return;
            form.dataset.confirmarPasswordListo = '1';
            form.addEventListener('submit', function (e) {
                e.preventDefault();
                formPendiente = form;
                mensajeEl.textContent = form.dataset.mensaje || '¿Confirmás esta acción? No se puede deshacer.';
                inputEl.value = '';
                modal.show();
                var modalEl = document.getElementById('modal-confirmar-password');
                modalEl.addEventListener('shown.bs.modal', function alFoco() {
                    inputEl.focus();
                    modalEl.removeEventListener('shown.bs.modal', alFoco);
                });
            });
        });
    };

    document.addEventListener('DOMContentLoaded', function () { window.inicializarConfirmarPassword(document); });
})();
