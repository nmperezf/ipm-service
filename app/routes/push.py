from flask import Blueprint, jsonify, request
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.models import PushToken

push_bp = Blueprint("push", __name__, url_prefix="/push")


@push_bp.route("/registrar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def registrar():
    """Guarda (o actualiza el dueño, si el token ya existía) el token FCM
    que acaba de generar la app Android para el usuario logueado. Un mismo
    usuario puede tener varios tokens -- uno por dispositivo."""
    datos = request.get_json(silent=True) or {}
    token = datos.get("token")
    if not token:
        return jsonify(error="Falta el token"), 400

    push_token = PushToken.query.filter_by(token=token).first()
    if push_token:
        push_token.usuario_id = current_user.id
    else:
        db.session.add(PushToken(usuario_id=current_user.id, token=token))
    db.session.commit()
    return jsonify(ok=True)


@push_bp.route("/desregistrar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def desregistrar():
    datos = request.get_json(silent=True) or {}
    token = datos.get("token")
    if token:
        PushToken.query.filter_by(token=token, usuario_id=current_user.id).delete()
        db.session.commit()
    return jsonify(ok=True)
