"""Envío de push por Firebase Cloud Messaging (FCM), agrupado por
(tipo, cliente) -- reutiliza la misma clave de agrupación que
notificaciones._agrupar y el mismo criterio de título/cuerpo que ya usa
notificaciones/_resumen_modal.html, para no mandar un push por cada
Notificacion individual.

Se dispara desde el hook after_request de app/__init__.py, una vez que el
request que llamó a notificar_usuario/notificar_gestion ya hizo su propio
commit() -- ver app/notificaciones.py."""
import json

import firebase_admin
from firebase_admin import credentials, messaging
from flask import current_app, url_for

from app import db
from app.models import Notificacion, PushToken

# Color de la notificación según severidad -- mismo criterio que ya usa el
# dashboard (ver Notificacion.severidad y app/static/css/style.css:
# --accent/--bs-warning/--bs-success/--bs-info). El ícono en sí es siempre
# el mismo (silueta monocromática, ver mobile/android/.../ic_stat_notification):
# Android lo tiñe con este color, es el mecanismo nativo para esto.
COLOR_POR_SEVERIDAD = {
    "critico": "#EA580C",
    "alerta": "#B45309",
    "ok": "#16A34A",
    "info": "#2563EB",
}

_firebase_app = None


def _app_firebase():
    """Inicializa el SDK de Firebase Admin una sola vez, de forma perezosa
    -- así la app arranca igual si todavía no se configuró
    FIREBASE_CREDENTIALS_JSON (push es una funcionalidad opcional, no un
    requisito para levantar el server)."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    credenciales_json = current_app.config.get("FIREBASE_CREDENTIALS_JSON")
    if not credenciales_json:
        print("[push] FIREBASE_CREDENTIALS_JSON no está seteada")
        return None
    try:
        cred = credentials.Certificate(json.loads(credenciales_json))
        _firebase_app = firebase_admin.initialize_app(cred)
        print("[push] Firebase Admin SDK inicializado OK, project_id =", cred.project_id)
    except Exception as exc:  # noqa: BLE001 - visibilidad total del motivo mientras se depura en producción
        print(f"[push] ERROR inicializando Firebase Admin SDK: {exc!r}")
        return None
    return _firebase_app


def enviar_push_agrupado(destinatario_id, tipo, cliente_id):
    """Arma el payload agrupado y lo manda a cada dispositivo registrado del
    destinatario. No hace nada si Firebase no está configurado, si el
    usuario no tiene ningún token registrado, o si el grupo quedó vacío (por
    ejemplo, la transacción que iba a crear la Notificacion hizo rollback)."""
    print(f"[push] enviar_push_agrupado(destinatario_id={destinatario_id}, tipo={tipo!r}, cliente_id={cliente_id})")

    app_firebase = _app_firebase()
    if app_firebase is None:
        print("[push] abortado: FIREBASE_CREDENTIALS_JSON no configurado (o credenciales inválidas)")
        return

    tokens = PushToken.query.filter_by(usuario_id=destinatario_id).all()
    if not tokens:
        print(f"[push] abortado: usuario {destinatario_id} no tiene ningún PushToken registrado")
        return
    print(f"[push] {len(tokens)} token(s) encontrados para el usuario {destinatario_id}")

    grupo = (
        Notificacion.query.filter_by(
            destinatario_id=destinatario_id, tipo=tipo, cliente_id=cliente_id, leido=False
        )
        .order_by(Notificacion.fecha_carga.desc())
        .all()
    )
    if not grupo:
        print(f"[push] abortado: no hay Notificacion sin leer para ({destinatario_id}, {tipo}, {cliente_id})")
        return
    primera = grupo[0]

    if cliente_id:
        titulo = primera.cliente.nombre
        cuerpo = f"{len(grupo)} {primera.descripcion_tipo_plural}" if len(grupo) > 1 else primera.titulo
        etiqueta = f"{tipo}-{cliente_id}"
    else:
        titulo = "IPM Manager"
        cuerpo = primera.titulo
        etiqueta = f"{tipo}-{primera.id}"

    notification = messaging.Notification(title=titulo, body=cuerpo)
    android_config = messaging.AndroidConfig(
        notification=messaging.AndroidNotification(
            icon="ic_stat_notification",
            color=COLOR_POR_SEVERIDAD.get(primera.severidad, COLOR_POR_SEVERIDAD["info"]),
            tag=etiqueta,
        )
    )
    datos = {"url": primera.enlace or url_for("notificaciones.listar")}

    for push_token in tokens:
        _enviar_a_token(app_firebase, push_token, notification, android_config, datos)


def _enviar_a_token(app_firebase, push_token, notification, android_config, datos):
    mensaje = messaging.Message(
        notification=notification, android=android_config, data=datos, token=push_token.token,
    )
    try:
        resultado = messaging.send(mensaje, app=app_firebase)
        print(f"[push] enviado OK a token ...{push_token.token[-12:]}: {resultado}")
    except messaging.UnregisteredError:
        # El dispositivo desinstaló la app o el token venció -- se limpia
        # sola, sin cron aparte.
        print(f"[push] token ...{push_token.token[-12:]} vencido/desregistrado -- se borra")
        db.session.delete(push_token)
        db.session.commit()
    except Exception as exc:  # noqa: BLE001 - un push que falla no debe romper el request que lo disparó
        print(f"[push] ERROR enviando a token ...{push_token.token[-12:]}: {exc!r}")
        current_app.logger.warning("No se pudo enviar push a usuario %s: %s", push_token.usuario_id, exc)
