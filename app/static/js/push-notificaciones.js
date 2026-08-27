// Activación de notificaciones push (Firebase Cloud Messaging) -- solo
// tiene efecto dentro de la app Android empaquetada con Capacitor (ver
// mobile/): en un navegador normal, window.Capacitor no existe y el botón
// queda deshabilitado con una explicación.
(function () {
    'use strict';

    function llamarApi(url, cuerpo) {
        return fetch(url, {
            method: 'POST',
            headers: Object.assign({ 'Content-Type': 'application/json' }, window.ipmFetchHeaders()),
            body: JSON.stringify(cuerpo || {})
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var boton = document.getElementById('btn-notif-push');
        if (!boton) return;
        var estadoTexto = document.getElementById('notif-push-estado');
        var modalOnboardingEl = document.getElementById('modal-push-onboarding');

        var esApp = window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform();
        var PushNotifications = esApp && window.Capacitor.Plugins && window.Capacitor.Plugins.PushNotifications;

        if (!PushNotifications) {
            boton.disabled = true;
            if (estadoTexto) {
                estadoTexto.textContent = 'Las notificaciones push solo están disponibles desde la app instalada en el celular (no en el navegador).';
            }
            return;
        }

        function refrescar() {
            PushNotifications.checkPermissions().then(function (res) {
                var activo = res.receive === 'granted';
                boton.textContent = activo ? 'Notificaciones activadas' : 'Activar notificaciones';
                if (estadoTexto) {
                    estadoTexto.textContent = activo
                        ? 'Activadas en este dispositivo.'
                        : 'Desactivadas en este dispositivo.';
                }
            });
        }

        refrescar();

        PushNotifications.addListener('registration', function (token) {
            llamarApi('/push/registrar', { token: token.value }).then(function () {
                if (modalOnboardingEl && localStorage.getItem('ipm-push-onboarded') !== '1') {
                    localStorage.setItem('ipm-push-onboarded', '1');
                    new bootstrap.Modal(modalOnboardingEl).show();
                }
            });
        });

        PushNotifications.addListener('registrationError', function (err) {
            console.warn('Error registrando push:', err);
            alert('No se pudieron activar las notificaciones. Probá de nuevo.');
        });

        // Tocar la notificación (con la app en segundo plano o cerrada)
        // navega directo a la pantalla correspondiente.
        PushNotifications.addListener('pushNotificationActionPerformed', function (accion) {
            var url = accion.notification && accion.notification.data && accion.notification.data.url;
            if (url) window.location.href = url;
        });

        boton.addEventListener('click', function () {
            boton.disabled = true;
            PushNotifications.checkPermissions().then(function (res) {
                if (res.receive === 'granted') {
                    alert('Ya están activadas. Para desactivarlas: Configuración del celular > Apps > IPM Manager > Notificaciones.');
                    return null;
                }
                return PushNotifications.requestPermissions().then(function (res2) {
                    if (res2.receive !== 'granted') throw new Error('permiso-denegado');
                    return PushNotifications.register();
                });
            }).catch(function (e) {
                if (!e || e.message !== 'permiso-denegado') {
                    alert('No se pudieron activar las notificaciones. Probá de nuevo.');
                }
            }).finally(function () {
                boton.disabled = false;
                refrescar();
            });
        });
    });
})();
