from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.models import Cliente, Empresa, Usuario

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")

# El Super Admin puede crear cualquier rol, para cualquier empresa (incluido
# otro Super Admin — es quien administra la plataforma entera). El
# Administrador puede crear cualquier rol de su propia empresa (incluidos
# otros Administradores y Jefes). El Jefe tiene el mismo permiso operativo
# que el Administrador en todo lo demás, pero NO puede crear Administradores
# ni otros Jefes — solo Técnicos y Clientes.
ROLES_CREABLES = {
    "Super Admin": ["Super Admin", "Administrador", "Jefe", "Técnico", "Cliente"],
    "Administrador": ["Administrador", "Jefe", "Técnico", "Cliente"],
    "Jefe": ["Técnico", "Cliente"],
}


@usuarios_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Super Admin")
def listar():
    # El Super Admin ve y administra los usuarios de todas las empresas
    # (para poder resetear una contraseña o resolver algo puntual sin
    # depender de esa empresa); el Administrador/Jefe solo ve los suyos.
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
@rol_requerido("Administrador", "Jefe", "Super Admin")
def nuevo():
    es_super_admin = current_user.rol == "Super Admin"
    roles_disponibles = ROLES_CREABLES[current_user.rol]

    empresas = Empresa.query.order_by(Empresa.nombre).all() if es_super_admin else []
    if es_super_admin:
        # El Super Admin puede ligar un usuario Cliente al cliente de
        # cualquier empresa — se lista todo, agrupado visualmente por
        # empresa en el desplegable.
        clientes = Cliente.query.order_by(Cliente.empresa_id, Cliente.nombre).all()
    else:
        clientes = Cliente.query.filter_by(empresa_id=current_user.empresa_id).order_by(Cliente.nombre).all()

    if request.method == "POST":
        nombre_usuario = request.form["username"].strip()
        rol = request.form["rol"]
        if rol not in roles_disponibles:
            abort(403)
        if Usuario.query.filter_by(username=nombre_usuario).first():
            flash(f"Ya existe un usuario con el nombre '{nombre_usuario}'.", "danger")
            return render_template(
                "usuarios/form.html", usuario=None, clientes=clientes, roles=roles_disponibles,
                empresas=empresas, es_super_admin=es_super_admin,
            )

        # Empresa a la que queda ligado el usuario nuevo (no aplica a
        # Super Admin ni a Cliente, que se ligan por cliente_id en cambio).
        empresa_id = None
        if rol in ("Administrador", "Jefe", "Técnico"):
            if es_super_admin:
                empresa_id = request.form.get("empresa_id", type=int)
                if not empresa_id or not Empresa.query.get(empresa_id):
                    flash("Elegí una empresa válida para este usuario.", "danger")
                    return render_template(
                        "usuarios/form.html", usuario=None, clientes=clientes, roles=roles_disponibles,
                        empresas=empresas, es_super_admin=es_super_admin,
                    )
            else:
                empresa_id = current_user.empresa_id

        cliente_seleccionado = None
        if rol == "Cliente":
            cliente_id = request.form.get("cliente_id")
            if cliente_id:
                cliente_seleccionado = Cliente.query.get(int(cliente_id))
                if not cliente_seleccionado:
                    abort(403)
                if not es_super_admin and cliente_seleccionado.empresa_id != current_user.empresa_id:
                    abort(403)

        usuario = Usuario(
            username=nombre_usuario,
            nombre_completo=request.form.get("nombre_completo"),
            matricula_profesional=request.form.get("matricula_profesional", "").strip() or None,
            rol=rol,
            empresa_id=empresa_id,
            cliente_id=cliente_seleccionado.id if cliente_seleccionado else None,
        )
        usuario.set_password(request.form["password"])
        db.session.add(usuario)
        db.session.commit()
        flash(f"Usuario '{usuario.username}' creado como {rol}.", "success")
        return redirect(url_for("usuarios.listar"))

    return render_template(
        "usuarios/form.html", usuario=None, clientes=clientes, roles=roles_disponibles,
        empresas=empresas, es_super_admin=es_super_admin,
    )


def _validar_pertenencia(usuario):
    """Un Administrador/Jefe solo puede tocar usuarios de su propia
    empresa (incluidos los Cliente ligados a un cliente de esa empresa);
    el Super Admin puede tocar cualquiera."""
    if current_user.rol == "Super Admin":
        return
    if usuario.rol == "Cliente":
        if not usuario.cliente or usuario.cliente.empresa_id != current_user.empresa_id:
            abort(403)
        return
    if usuario.empresa_id != current_user.empresa_id:
        abort(403)


@usuarios_bp.route("/<int:usuario_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Super Admin")
def editar(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    _validar_pertenencia(usuario)

    if request.method == "POST":
        usuario.nombre_completo = request.form.get("nombre_completo")
        usuario.matricula_profesional = request.form.get("matricula_profesional", "").strip() or None
        usuario.activo = bool(request.form.get("activo"))
        password_nueva = request.form.get("password")
        if password_nueva:
            usuario.set_password(password_nueva)
        db.session.commit()
        flash(f"Usuario '{usuario.username}' actualizado.", "success")
        return redirect(url_for("usuarios.listar"))

    return render_template("usuarios/form.html", usuario=usuario, clientes=[])


@usuarios_bp.route("/<int:usuario_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Super Admin")
def eliminar(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    _validar_pertenencia(usuario)

    if usuario.id == current_user.id:
        flash("No te podés eliminar a vos mismo.", "danger")
        return redirect(url_for("usuarios.listar"))

    nombre = usuario.username
    try:
        db.session.delete(usuario)
        db.session.commit()
        flash(f"Usuario '{nombre}' eliminado.", "info")
    except Exception:
        db.session.rollback()
        flash(
            f"No se pudo eliminar '{nombre}': tiene OT, visitas u otros registros ligados a su nombre. "
            "Desactivalo en cambio (editalo y destildá 'Activo').",
            "danger",
        )
    return redirect(url_for("usuarios.listar"))
