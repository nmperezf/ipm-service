"""Helpers para generar Notificacion. Todas agregan a la sesión (sin
commit) para que quede en la misma transacción que la acción que las
dispara — el caller ya hace su propio db.session.commit()."""

from flask import g, url_for

from app import db
from app.models import Notificacion, Usuario


def _marcar_pendiente_de_push(destinatario_id, tipo, cliente_id):
    """Registra en g (vive solo durante este request) qué grupo (destinatario,
    tipo, cliente) acaba de recibir una Notificacion nueva. Un hook
    after_request en app/__init__.py revisa esto una vez terminada la vista
    -- ahí ya corrió el commit() del caller -- y dispara el push agrupado
    por FCM (ver app/push.py). Así ninguno de los ~11 sitios que llaman a
    notificar_usuario/notificar_gestion necesita saber que el push existe."""
    g.setdefault("_push_pendientes", []).append((destinatario_id, tipo, cliente_id))


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
    _marcar_pendiente_de_push(destinatario.id, tipo, cliente_id)


def notificar_gestion(empresa_id, tipo, titulo, cliente_id=None, enlace=None, remitente=None):
    """Notifica a todos los Administrador/Jefe de la empresa (menos a quien
    generó el evento, si fue uno de ellos) — para los eventos operativos
    que le interesan a la gestión: ensayo nuevo, visita a revisión,
    observación nueva, equipo nuevo."""
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
        _marcar_pendiente_de_push(usuario.id, tipo, cliente_id)


def notificar_tecnico_asignado(ot, remitente):
    """Avisa al técnico/Jefe que quedó a cargo de una OT. Si la OT viene de
    una visita, el aviso y el link apuntan a LA VISITA -- ahí es donde
    completa el trabajo (ver visitas.enviar_revision), no en la ficha de la
    OT. Las correctivas (sin visita) siguen apuntando a la OT, que ahí sí
    es donde se completa todo."""
    if not ot.tecnico_id:
        return
    if ot.visita_id:
        notificar_usuario(
            ot.tecnico_usuario,
            tipo="visita_asignada",
            titulo=f"Visita asignada — {ot.instalacion.nombre} ({ot.visita.fecha.strftime('%d/%m/%Y')})",
            empresa_id=remitente.empresa_id,
            cliente_id=ot.instalacion.cliente_id,
            enlace=url_for("visitas.detalle", visita_id=ot.visita_id),
            remitente=remitente,
        )
    else:
        notificar_usuario(
            ot.tecnico_usuario,
            tipo="ot_asignada",
            titulo=f"OT {ot.numero} asignada — {ot.instalacion.nombre}",
            empresa_id=remitente.empresa_id,
            cliente_id=ot.instalacion.cliente_id,
            enlace=url_for("ordenes.detalle", ot_id=ot.id),
            remitente=remitente,
        )
