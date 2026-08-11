"""PDF técnico del checklist de una visita: cada punto cargado con su
valor, estado (Aprobado/Observado/Deficiencia/N-A) y nota -- pensado como
respaldo/registro de cumplimiento, a diferencia del PDF de devolución
(pdf_devolucion.py), que es el resumen ejecutivo para el cliente."""
import io

from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from app.models import ESTADOS_CHECKLIST_LABEL, categoria_de_tipo_equipo
from app.pdf_base import ACCENT_SOFT, construir, crear_documento, estilo_tabla_encabezado, estilos


def categoria_de_formulario(formulario):
    """La categoría (Sala de bombas, Bocas de incendio, etc) a la que
    pertenece un Formulario ya cargado -- del equipo si está ligado a
    uno, si no del tipo de equipo que declaró su TipoFormulario (ej.
    "Señales de supervisión y falla — Sala de bombas", que no se liga a
    un equipo puntual pero sí declara "Bomba jockey" como referencia).
    None si no se puede determinar (checklist realmente general)."""
    if formulario.equipo:
        return categoria_de_tipo_equipo(formulario.equipo.tipo)
    return categoria_de_tipo_equipo(formulario.tipo_formulario.tipo_equipo_aplicable)


def categorias_de_visita(visita):
    """Categorías con al menos un checklist cargado en esta visita, en el
    orden en que aparecen -- para armar los botones de PDF por categoría
    (ver visitas.checklist_tecnico_pdf_categoria)."""
    vistas = []
    for item in visita.items:
        for f in item.formularios:
            categoria = categoria_de_formulario(f)
            if categoria and categoria not in vistas:
                vistas.append(categoria)
    return vistas


def _fila_valores(valor, campo):
    """(texto del valor, label del estado, nota) de un campo ya cargado --
    unifica el campo simple (numero/texto sin estado, como los checklists
    de siempre) con el que tiene estado (con_estado=true o tipo='estado')."""
    con_estado = campo["tipo"] == "estado" or campo.get("con_estado")
    unidad = campo.get("unidad", "")

    def _fmt(v):
        if v is None or v == "":
            return "-"
        if isinstance(v, list):
            return ", ".join(v) if v else "-"
        return f"{v} {unidad}".strip()

    if not con_estado:
        return _fmt(valor), "-", ""
    if not valor:
        return "-", "-", ""
    estado = valor.get("estado") or ""
    estado_label = ESTADOS_CHECKLIST_LABEL.get(estado, "-" if not estado else estado)
    return _fmt(valor.get("valor")), estado_label, valor.get("nota") or ""


def generar_pdf_checklist_tecnico(visita, categoria=None):
    """categoria=None arma el documento completo, con todo lo cargado en
    la visita; con una categoría (ver categorias_de_visita) arma uno
    acotado a esa sala/sistema puntual (ej. "Sala de bombas" separado de
    "Bocas de incendio"), para archivar cada uno por su lado."""
    buffer = io.BytesIO()
    doc = crear_documento(buffer)
    styles = estilos()
    titulo, subtitulo, h2, normal, celda = (
        styles["titulo"], styles["subtitulo"], styles["h2"], styles["normal"], styles["celda"],
    )

    instalacion = visita.instalacion
    elementos = []
    elementos.append(Paragraph(f"Checklist técnico — {categoria}" if categoria else "Checklist técnico de la visita", titulo))
    elementos.append(
        Paragraph(
            f"{instalacion.cliente.nombre} &middot; {instalacion.nombre} &middot; "
            f"Visita del {visita.fecha.strftime('%d/%m/%Y')}",
            subtitulo,
        )
    )
    elementos.append(Spacer(1, 0.5 * cm))

    formularios = sorted(
        (
            f for item in visita.items for f in item.formularios
            if categoria is None or categoria_de_formulario(f) == categoria
        ),
        key=lambda f: ((f.equipo.nombre if f.equipo else ""), f.tipo_formulario.nombre),
    )

    if not formularios:
        elementos.append(Paragraph("No se cargaron checklists en esta visita.", normal))
        construir(doc, elementos, tipo_doc="Checklist técnico")
        return buffer.getvalue()

    por_equipo = {}
    for f in formularios:
        clave = f.equipo.nombre if f.equipo else "Checklist general"
        por_equipo.setdefault(clave, []).append(f)

    for nombre_equipo, lista in por_equipo.items():
        elementos.append(Paragraph(nombre_equipo, h2))
        referencias = {f.tipo_formulario.referencia_normativa for f in lista if f.tipo_formulario.referencia_normativa}
        for ref in referencias:
            elementos.append(Paragraph(ref, subtitulo))

        filas = [["Punto", "Valor", "Estado", "Nota"]]
        resaltado = []
        for f in lista:
            datos = f.datos()
            for campo in f.tipo_formulario.campos():
                texto_valor, estado_label, nota = _fila_valores(datos.get(campo["campo"]), campo)
                filas.append([
                    Paragraph(campo["label"], celda),
                    texto_valor,
                    estado_label,
                    Paragraph(nota, celda) if nota else "-",
                ])
                if estado_label == "Deficiencia":
                    resaltado.append(("BACKGROUND", (0, len(filas) - 1), (-1, len(filas) - 1), ACCENT_SOFT))

        tabla = Table(filas, colWidths=[6.4 * cm, 2.6 * cm, 2.6 * cm, 5.8 * cm])
        tabla.setStyle(estilo_tabla_encabezado())
        if resaltado:
            tabla.setStyle(TableStyle(resaltado))
        elementos.append(tabla)
        elementos.append(Spacer(1, 0.6 * cm))

    construir(doc, elementos, tipo_doc="Checklist técnico")
    return buffer.getvalue()
