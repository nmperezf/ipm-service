"""Helpers para generar Notificacion. Todas agregan a la sesión (sin
commit) para que quede en la misma transacción que la acción que las
dispara — el caller ya hace su propio db.session.commit()."""

from app import db
from app.models import Notificacion, Usuario


def notificar_usuario(destinatario, tipo, titulo, empresa_id, cliente_id=None, enlace=None, remitente=None):
    """Notifica a un usuario puntual (ej: 'OT asignada' al técnico, 'Mensaje
    nuevo' al destinatario elegido). No notifica si el destinatario es
    quien generó el evento."""
    if remitente and destinatario.id == remitente.id:
        return
    db.session.add(
        Notificacion(
            empresa_id=empresa_id,
            destinatario_id=destinatario.id,
            remitente_id=remitente.id if remitente else None,
            cliente_id=cliente_id,
            tipo=tipo,
            titulo=titulo,
            enlace=enlace,
        )
    )


def notificar_gestion(empresa_id, tipo, titulo, cliente_id=None, enlace=None, remitente=None):
    """Notifica a todos los Administrador/Jefe de la empresa (menos a quien
    generó el evento, si fue uno de ellos) — para los eventos operativos
    que le interesan a la gestión: ensayo nuevo, visita a revisión,
    observación nueva, equipo nuevo, formulario cargado."""
    destinatarios = Usuario.query.filter(
        Usuario.empresa_id == empresa_id, Usuario.rol.in_(("Administrador", "Jefe"))
    )
    if remitente:
        destinatarios = destinatarios.filter(Usuario.id != remitente.id)
    for usuario in destinatarios.all():
        db.session.add(
            Notificacion(
                empresa_id=empresa_id,
                destinatario_id=usuario.id,
                remitente_id=remitente.id if remitente else None,
                cliente_id=cliente_id,
                tipo=tipo,
                titulo=titulo,
                enlace=enlace,
            )
        )
