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

        function refrescar(textoExtra) {
            PushNotifications.checkPermissions().then(function (res) {
                var activo = res.receive === 'granted';
                boton.textContent = activo ? 'Notificaciones activadas' : 'Activar notificaciones';
                if (estadoTexto) {
                    estadoTexto.textContent = textoExtra || (activo
                        ? 'Activadas en este dispositivo.'
                        : 'Desactivadas en este dispositivo.');
                }
            });
        }

        refrescar();

        PushNotifications.addListener('registration', function (token) {
            llamarApi('/push/registrar', { token: token.value }).then(function (r) {
                if (!r.ok) throw new Error('registro-fallido');
                if (modalOnboardingEl && localStorage.getItem('ipm-push-onboarded') !== '1') {
                    localStorage.setItem('ipm-push-onboarded', '1');
                    new bootstrap.Modal(modalOnboardingEl).show();
                }
                refrescar('Activadas y confirmadas con el servidor.');
            }).catch(function () {
                refrescar('El permiso está dado, pero no se pudo confirmar con el servidor. Probá tocar el botón de nuevo.');
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

        // Siempre reintenta el registro contra el servidor al tocar el
        // botón, aunque el permiso del sistema ya esté concedido -- si el
        // permiso se dio en un momento en que el servidor no respondía (o
        // el registro falló por cualquier otro motivo), esta es la única
        // forma de reintentarlo sin desinstalar la app.
        boton.addEventListener('click', function () {
            boton.disabled = true;
            PushNotifications.requestPermissions().then(function (res) {
                if (res.receive !== 'granted') throw new Error('permiso-denegado');
                return PushNotifications.register();
            }).catch(function (e) {
                if (!e || e.message !== 'permiso-denegado') {
                    alert('No se pudieron activar las notificaciones. Probá de nuevo.');
                } else {
                    alert('Bloqueaste las notificaciones para esta app -- para activarlas, habilitalas desde Configuración > Apps > IPM Manager > Notificaciones.');
                }
            }).finally(function () {
                boton.disabled = false;
                refrescar();
            });
        });
    });
})();
