from datetime import date

from app import db
from app.models import Contrato, Visita


def actualizar_vencimientos(hoy=None):
    """Recorre visitas y contratos y actualiza su estado si vencieron.
    Se llama al entrar a cualquier vista de planificación/dashboard, así
    el estado siempre refleja la realidad sin intervención manual."""
    hoy = hoy or date.today()
    for visita in Visita.query.all():
        visita.actualizar_estado_por_vencimiento(hoy=hoy)
    for contrato in Contrato.query.filter_by(activo=True).all():
        contrato.actualizar_estado_por_vencimiento(hoy=hoy)
    db.session.commit()
