from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.models import Usuario

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.inicio"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        usuario = Usuario.query.filter_by(username=username).first()

        if usuario and usuario.activo and usuario.check_password(password):
            login_user(usuario)
            flash(f"Bienvenido, {usuario.nombre_completo or usuario.username}.", "success")
            siguiente = request.args.get("next")
            partes = urlsplit(siguiente or "")
            if partes.scheme or partes.netloc or not (siguiente or "").startswith("/") or (siguiente or "").startswith("//"):
                siguiente = None
            return redirect(siguiente or url_for("dashboard.inicio"))

        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))
