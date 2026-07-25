"""Utilidades de autorización.

Fase 2: además del control por rol, estas funciones acotan qué Clientes
(y todo lo que cuelga de un Cliente) puede ver cada usuario según su rol:
- Super Admin: todos, de cualquier empresa.
- Administrador / Técnico: solo los de su propia empresa.
- Cliente: solo el Cliente puntual al que está ligado su usuario.
"""

from functools import wraps

from flask import abort
from flask_login import current_user


def rol_requerido(*roles):
    """Exige sesión iniciada y que el rol del usuario esté entre los
    permitidos. Uso: @rol_requerido("Super Admin") o
    @rol_requerido("Administrador", "Super Admin")."""

    def decorador(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.rol not in roles:
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorador


def clientes_visibles():
    """Query de Cliente ya acotada según el rol de quien está logueado."""
    from app.models import Cliente

    if not current_user.is_authenticated:
        return Cliente.query.filter(db_false())
    if current_user.rol == "Super Admin":
        return Cliente.query
    if current_user.rol == "Cliente":
        return Cliente.query.filter_by(id=current_user.cliente_id)
    return Cliente.query.filter_by(empresa_id=current_user.empresa_id)


def db_false():
    """Condición SQL siempre falsa, para queries que no deben devolver
    nada (ej. un rol sin ningún cliente asociado todavía)."""
    from app import db

    return db.false()


def verificar_acceso_cliente(cliente):
    """Corta con 403 si el cliente pasado no es visible para el usuario
    logueado. Se usa en cada ruta que recibe un cliente_id o algo que
    cuelgue de un cliente (instalación, contrato, equipo, visita, etc)."""
    if not current_user.is_authenticated:
        abort(401)
    if current_user.rol == "Super Admin":
        return
    if current_user.rol == "Cliente":
        if cliente.id != current_user.cliente_id:
            abort(403)
        return
    if cliente.empresa_id != current_user.empresa_id:
        abort(403)


def verificar_acceso_empresa(empresa_id):
    """Corta con 403 si el recurso (Repuesto, Recordatorio) no pertenece
    a la empresa del usuario logueado."""
    if not current_user.is_authenticated:
        abort(401)
    if current_user.rol == "Super Admin":
        return
    if current_user.rol == "Cliente" or empresa_id != current_user.empresa_id:
        abort(403)


def clientes_asignados_tecnico():
    """IDs de clientes donde el usuario Técnico logueado tiene al menos
    una orden de trabajo asignada (de cualquier estado). Se usa para
    acotar la escritura del técnico — la lectura sigue siendo amplia
    (todos los clientes de su empresa)."""
    from app import db
    from app.models import Instalacion, OrdenTrabajo

    filas = (
        db.session.query(Instalacion.cliente_id)
        .join(OrdenTrabajo, OrdenTrabajo.instalacion_id == Instalacion.id)
        .filter(OrdenTrabajo.tecnico_id == current_user.id)
        .distinct()
        .all()
    )
    return {f[0] for f in filas}


def verificar_escritura_cliente(cliente):
    """Para crear/editar/eliminar (no para solo consultar): además de
    pertenecer a la empresa/cliente correcto, si el usuario es Técnico
    exige que tenga al menos una OT asignada en ese cliente puntual —
    puede ver cualquier cliente de su empresa, pero solo escribir en
    el/los que tiene asignados."""
    verificar_acceso_cliente(cliente)
    if current_user.rol == "Técnico" and cliente.id not in clientes_asignados_tecnico():
        abort(403)


def tecnicos_de_la_empresa(empresa_id=None):
    """Usuarios rol Técnico activos de una empresa (por defecto, la del
    usuario logueado) — para los desplegables de asignación."""
    from app.models import Usuario

    empresa_id = empresa_id or current_user.empresa_id
    return Usuario.query.filter_by(rol="Técnico", empresa_id=empresa_id, activo=True).order_by(
        Usuario.nombre_completo
    ).all()


def visita_bloqueada_para_tecnico(visita):
    """True si el Técnico ya no puede tocar nada de esta visita: la mandó
    a revisión (o ya está cerrada) — a partir de ahí, cualquier corrección
    la hace el Administrador/Jefe directamente."""
    return current_user.rol == "Técnico" and (visita.en_revision or visita.cerrada)


def verificar_visita_editable(visita):
    """Corta con 403 si un Técnico intenta modificar algo de una visita
    que ya mandó a revisión o que ya está cerrada."""
    if visita_bloqueada_para_tecnico(visita):
        abort(403)
