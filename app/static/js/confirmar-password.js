/*
 * Doble confirmación para eliminar registros de alto impacto: cualquier
 * <form class="form-confirmar-password"> intercepta su propio submit, pide
 * la contraseña en un modal compartido y recién ahí manda el POST real con
 * un campo oculto "password" agregado — el backend la valida de nuevo
 * (ver auth_utils.verificar_password_confirmacion).
 */
document.addEventListener('DOMContentLoaded', function () {
    var modalEl = document.getElementById('modal-confirmar-password');
    if (!modalEl) return;

    var modal = new bootstrap.Modal(modalEl);
    var mensajeEl = document.getElementById('modal-confirmar-password-mensaje');
    var inputEl = document.getElementById('modal-confirmar-password-input');
    var formModal = document.getElementById('form-modal-confirmar-password');
    var formPendiente = null;

    document.querySelectorAll('form.form-confirmar-password').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            formPendiente = form;
            mensajeEl.textContent = form.dataset.mensaje || '¿Confirmás esta acción? No se puede deshacer.';
            inputEl.value = '';
            modal.show();
            modalEl.addEventListener('shown.bs.modal', function alFoco() {
                inputEl.focus();
                modalEl.removeEventListener('shown.bs.modal', alFoco);
            });
        });
    });

    formModal.addEventListener('submit', function (e) {
        e.preventDefault();
        if (!formPendiente || !inputEl.value) return;
        var oculto = document.createElement('input');
        oculto.type = 'hidden';
        oculto.name = 'password';
        oculto.value = inputEl.value;
        formPendiente.appendChild(oculto);
        modal.hide();
        formPendiente.submit();
    });
});
