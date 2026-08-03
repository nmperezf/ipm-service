import os

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def _url_base_de_datos():
    """Railway (y otros) a veces entregan la URL de Postgres con el
    prefijo viejo 'postgres://', que SQLAlchemy moderno ya no acepta —
    hay que convertirlo a 'postgresql://'."""
    url = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(basedir, "ipm_service.db"))
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    """Configuración base. En producción, sobreescribir vía variables de entorno."""

    SQLALCHEMY_DATABASE_URI = _url_base_de_datos()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-cambiar-en-produccion")

    # Configurable por variable de entorno para poder apuntar a un volumen
    # persistente (o, el día de mañana, a otro host) sin tocar código.
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(basedir, "app", "static", "uploads"))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB por request
    EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "gif", "webp"}
