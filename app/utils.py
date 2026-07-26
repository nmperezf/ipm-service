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


# ---------------------------------------------------------------------------
# Histórico/trazabilidad de un equipo — compartido entre la ficha interna
# (equipos.detalle, ve todo apenas se carga) y el portal de cliente
# (portal.equipo_detalle, solo ve lo de visitas Cerradas y con OT Finalizada).
# ---------------------------------------------------------------------------


def serie_numerica(formularios, nombre_campo):
    """(fecha, valor) para un campo numérico, en orden cronológico,
    ignorando los formularios donde ese campo quedó vacío o no numérico."""
    serie = []
    for f in formularios:
        valor = f.datos().get(nombre_campo)
        try:
            valor_float = float(valor)
        except (TypeError, ValueError):
            continue
        serie.append((f.fecha_creacion.date(), valor_float))
    return serie


def polilinea_svg(serie, ancho=520, alto=90, padding=12):
    """Puntos para un <polyline> de una gráfica simple, sin dependencias
    de JS: solo necesita al menos 2 valores numéricos para dibujar algo."""
    if len(serie) < 2:
        return None, None, None
    valores = [v for _, v in serie]
    minimo, maximo = min(valores), max(valores)
    rango = (maximo - minimo) or 1
    n = len(serie)
    puntos = []
    for i, (_, v) in enumerate(serie):
        x = padding + (ancho - 2 * padding) * (i / (n - 1))
        y = alto - padding - (alto - 2 * padding) * ((v - minimo) / rango)
        puntos.append(f"{x:.1f},{y:.1f}")
    return " ".join(puntos), minimo, maximo


def construir_secciones_historico(formularios):
    """A partir de una lista de Formulario (ya filtrada por quien llama —
    todos para la ficha interna, solo los de visitas Cerradas+Finalizadas
    para el portal), arma las secciones agrupadas por tipo de formulario
    con su gráfico/tabla de evolución por campo."""
    por_tipo = {}
    for formulario in formularios:
        por_tipo.setdefault(formulario.tipo_formulario, []).append(formulario)

    secciones = []
    for tipo_formulario, lista in por_tipo.items():
        campos_numericos = []
        campos_otros = []
        for campo in tipo_formulario.campos():
            if campo["tipo"] == "numero":
                serie = serie_numerica(lista, campo["campo"])
                puntos, minimo, maximo = polilinea_svg(serie)
                campos_numericos.append(
                    {"label": campo["label"], "serie": serie, "puntos": puntos, "minimo": minimo, "maximo": maximo}
                )
            else:
                historial = [(f.fecha_creacion, f.datos().get(campo["campo"])) for f in reversed(lista)]
                campos_otros.append({"label": campo["label"], "historial": historial})
        secciones.append(
            {"tipo_formulario": tipo_formulario, "campos_numericos": campos_numericos, "campos_otros": campos_otros}
        )
    return secciones


def checklists_aprobados_de_equipo(equipo):
    """Formularios de este equipo que ya pasaron el doble candado del
    portal: la visita que los generó está Cerrada y su OT Finalizada."""
    from app.models import Formulario

    formularios = Formulario.query.filter_by(equipo_id=equipo.id).order_by(Formulario.fecha_creacion).all()
    return [
        f
        for f in formularios
        if f.item_visita
        and f.item_visita.visita.cerrada
        and f.item_visita.visita.orden_trabajo
        and f.item_visita.visita.orden_trabajo.estado == "Finalizada"
    ]


# ---------------------------------------------------------------------------
# Constructor dinámico de campos — compartido entre TipoFormulario (por
# cliente) y ServicioTipo (catálogo por empresa, se importa a un cliente).
# ---------------------------------------------------------------------------

TIPOS_CAMPO = [
    ("texto", "Texto corto"),
    ("texto_largo", "Texto largo"),
    ("numero", "Número"),
    ("fecha", "Fecha"),
    ("booleano", "Sí / No"),
    ("seleccion", "Selección (una opción)"),
    ("multi_seleccion", "Checklist (varias opciones)"),
]


def slugify_campo(texto):
    """Convierte una etiqueta libre en una clave interna segura (sin
    acentos, espacios ni mayúsculas) para usar como nombre de campo."""
    import re
    import unicodedata

    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    return texto or "campo"


def armar_campos_desde_formulario(form):
    """Reconstruye la lista de campos (schema_json) a partir de los inputs
    repetidos del constructor dinámico."""
    labels = form.getlist("campo_label")
    tipos = form.getlist("campo_tipo")
    opciones_list = form.getlist("campo_opciones")

    campos = []
    usados = set()
    for label, tipo, opciones_str in zip(labels, tipos, opciones_list):
        label = (label or "").strip()
        if not label:
            continue
        slug_base = slugify_campo(label)
        slug = slug_base
        n = 1
        while slug in usados:
            n += 1
            slug = f"{slug_base}_{n}"
        usados.add(slug)

        campo = {"campo": slug, "tipo": tipo, "label": label}
        if tipo in ("seleccion", "multi_seleccion") and opciones_str.strip():
            campo["opciones"] = [o.strip() for o in opciones_str.split(",") if o.strip()]
        campos.append(campo)
    return campos
