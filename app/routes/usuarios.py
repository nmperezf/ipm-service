from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.models import Cliente, Usuario

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")

# El Administrador puede crear cualquier rol de su empresa (incluidos otros
# Administradores y Jefes). El Jefe tiene el mismo permiso operativo que el
# Administrador en todo lo demás, pero NO puede crear Administradores ni
# otros Jefes — solo Técnicos y Clientes.
ROLES_CREABLES = {
    "Administrador": ["Administrador", "Jefe", "Técnico", "Cliente"],
    "Jefe": ["Técnico", "Cliente"],
}


@usuarios_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Super Admin")
def listar():
    # El Super Admin ve y administra los usuarios de todas las empresas
    # (para poder resetear una contraseña ante un problema puntual); el
    # Administrador/Jefe solo ve los de la suya.
    if current_user.rol == "Super Admin":
        usuarios = Usuario.query.order_by(Usuario.empresa_id, Usuario.rol, Usuario.username).all()
    else:
        usuarios = (
            Usuario.query.filter_by(empresa_id=current_user.empresa_id)
            .order_by(Usuario.rol, Usuario.username)
            .all()
        )
    return render_template("usuarios/list.html", usuarios=usuarios)


@usuarios_bp.route("/nuevo", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def nuevo():
    # Solo clientes de la propia empresa, para no poder ligar un usuario
    # Cliente a un cliente de otra empresa.
    clientes = Cliente.query.filter_by(empresa_id=current_user.empresa_id).order_by(Cliente.nombre).all()
    roles_disponibles = ROLES_CREABLES[current_user.rol]

    if request.method == "POST":
        nombre_usuario = request.form["username"].strip()
        rol = request.form["rol"]
        if rol not in roles_disponibles:
            abort(403)
        if Usuario.query.filter_by(username=nombre_usuario).first():
            flash(f"Ya existe un usuario con el nombre '{nombre_usuario}'.", "danger")
            return render_template("usuarios/form.html", usuario=None, clientes=clientes, roles=roles_disponibles)

        cliente_id = request.form.get("cliente_id")
        cliente_seleccionado = None
        if rol == "Cliente" and cliente_id:
            cliente_seleccionado = Cliente.query.get(int(cliente_id))
            if not cliente_seleccionado or cliente_seleccionado.empresa_id != current_user.empresa_id:
                abort(403)

        usuario = Usuario(
            username=nombre_usuario,
            nombre_completo=request.form.get("nombre_completo"),
            rol=rol,
            empresa_id=current_user.empresa_id if rol in ("Administrador", "Jefe", "Técnico") else None,
            cliente_id=cliente_seleccionado.id if cliente_seleccionado else None,
        )
        usuario.set_password(request.form["password"])
        db.session.add(usuario)
        db.session.commit()
        flash(f"Usuario '{usuario.username}' creado como {rol}.", "success")
        return redirect(url_for("usuarios.listar"))

    return render_template("usuarios/form.html", usuario=None, clientes=clientes, roles=roles_disponibles)


def _validar_pertenencia(usuario):
    """Un Administrador/Jefe solo puede tocar usuarios de su propia
    empresa; el Super Admin puede tocar cualquiera (para poder resetear
    una contraseña ante un problema puntual, sin depender de la empresa)."""
    if current_user.rol == "Super Admin":
        return
    if usuario.rol in ("Administrador", "Jefe", "Técnico") and usuario.empresa_id != current_user.empresa_id:
        abort(403)


@usuarios_bp.route("/<int:usuario_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Super Admin")
def editar(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    _validar_pertenencia(usuario)

    if request.method == "POST":
        usuario.nombre_completo = request.form.get("nombre_completo")
        usuario.activo = bool(request.form.get("activo"))
        password_nueva = request.form.get("password")
        if password_nueva:
            usuario.set_password(password_nueva)
        db.session.commit()
        flash(f"Usuario '{usuario.username}' actualizado.", "success")
        return redirect(url_for("usuarios.listar"))

    return render_template("usuarios/form.html", usuario=usuario, clientes=[])
