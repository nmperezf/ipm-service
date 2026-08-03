"""
Modelos del núcleo de IPM Service.

Filosofía: el centro del sistema es la INSTALACIÓN, no el cliente.
Un cliente puede tener muchas instalaciones; cada instalación tiene
sus propios contratos, servicios, visitas y formularios.

Jerarquía:
    Cliente -> Instalacion -> Contrato -> ServicioContrato
                                  -> Visita -> ItemVisita (por servicio)
                                            -> Formulario / Foto (por item)

Un Contrato dura 1 año. Cada ServicioContrato tiene su propia frecuencia
(mensual, bimestral, trimestral, cuatrimestral, semestral o anual) y genera
sus propias fechas de ejecución dentro de ese año, acotadas por la duración
del contrato (una frecuencia anual genera una sola ejecución, al año
siguiente como máximo). Cuando varios servicios caen en la misma fecha,
se agrupan en una única Visita, y cada servicio se marca cumplido/pendiente
de forma independiente a través de su ItemVisita.
"""

from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db

# ---------------------------------------------------------------------------
# Catálogos / constantes de dominio
# ---------------------------------------------------------------------------

FRECUENCIAS_MESES = {
    "mensual": 1,
    "bimestral": 2,
    "trimestral": 3,
    "cuatrimestral": 4,
    "semestral": 6,
    "anual": 12,
}

FRECUENCIAS_DISPONIBLES = list(FRECUENCIAS_MESES.keys())

ESTADOS_VISITA = [
    "Pendiente",
    "Programado",
    "En proceso",
    "Realizado",
    "Vencido",
    "Cancelado",
    "Reprogramado",
]

ESTADOS_ITEM = ["Pendiente", "Cumplido", "Cancelado"]

ESTADOS_CONTRATO = ["Activo", "Vencido", "Renovado", "Cancelado"]

CLASIFICACIONES_OBSERVACION = [
    "Deficiencia crítica",
    "Deficiencia no crítica",
    "Desactivación",
    "Comentario",
]

# Cómo se traduce el estado interno de una visita a lo que se muestra en
# el calendario mensual (agrupa Pendiente/Programado/En proceso en "Pendientes")
ETIQUETA_CALENDARIO = {
    "Realizado": "Completado",
    "Pendiente": "Pendientes",
    "Programado": "Pendientes",
    "En proceso": "Pendientes",
    "Vencido": "Vencido",
    "Cancelado": "Cancelado",
    "Reprogramado": "Pendientes",
}

CLASE_CALENDARIO = {
    "Completado": "success",
    "Pendientes": "primary",
    "Vencido": "danger",
    "Cancelado": "secondary",
}

TIPOS_OT = ["Preventivo", "Inspección", "Mantenimiento", "Correctivo", "Predictivo", "Visita técnica"]

# Tipos elegibles al cargar una OT a mano (Preventivo queda reservado para
# las que se generan solas desde un contrato, ligadas a una visita).
# "Inspección" va primera: es el tipo de OT manual más común, y al no
# marcarse ninguna por defecto en el <select>, el navegador preselecciona
# la primera de la lista.
TIPOS_OT_MANUAL = ["Inspección", "Mantenimiento", "Correctivo", "Predictivo", "Visita técnica"]

ESTADOS_OT = ["Pendiente", "Asignada", "En proceso", "Pausada", "Finalizada", "Cancelada"]

PRIORIDADES_OT = ["Baja", "Media", "Alta", "Urgente"]

# Cómo entró una Foto al sistema: "Visita" para las que se sacan durante un
# servicio (flujo de siempre), "Carga manual" para las que alguien sube
# sueltas contra un equipo/instalación sin pasar por una visita, y
# "Migración" para las que vienen de una base de datos vieja.
ORIGENES_FOTO = ["Visita", "Carga manual", "Migración"]

# Orden preferido de las categorías de equipo en la navegación (portal de
# cliente, elegir equipo dentro de una visita). Las categorías que se creen
# a mano desde TipoEquipo y no estén en esta lista van al final, alfabético.
CATEGORIAS_EQUIPO_ORDEN = ["Sala de bombas", "Estaciones de control y alarma", "Bocas de incendio", "Otros equipos"]

# Tipos de equipo de sala de bombas que son la bomba principal del sistema
# (electro u motobomba) — los únicos que llevan ensayo de curva de caudal
# NFPA 25 (anual). La bomba jockey y la reserva de agua quedan afuera: no
# son la bomba principal, no llevan ese ensayo.
TIPOS_BOMBA_PRINCIPAL = ("Bomba", "Electrobomba", "Motobomba")

# Tipos que además muestran/guardan datos de placa y de motor en la ficha
# del equipo — los mismos de arriba más la bomba jockey (tiene motor propio
# aunque no lleve curva de caudal).
TIPOS_CON_DATOS_PLACA = TIPOS_BOMBA_PRINCIPAL + ("Bomba jockey",)

ESTADOS_CANERIA = [
    "Buen estado",
    "Corrosión superficial",
    "Corrosión avanzada",
    "Fuga visible",
    "Pintura descascarada",
    "Daño mecánico",
    "Soportería deficiente / floja",
    "Obstrucción visual",
]


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------


class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    direccion = db.Column(db.String(250))
    contacto = db.Column(db.String(150))
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(150))
    observaciones = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    instalaciones = db.relationship(
        "Instalacion", backref="cliente", lazy=True, cascade="all, delete-orphan"
    )
    empresa = db.relationship("Empresa", backref="clientes")

    def indicadores(self):
        """Indicadores agregados de todas las instalaciones del cliente."""
        items = [
            it
            for inst in self.instalaciones
            for c in inst.contratos
            for v in c.visitas
            for it in v.items
        ]
        total = len(items)
        cumplidos = sum(1 for it in items if it.estado == "Cumplido")
        pendientes = sum(1 for it in items if it.estado == "Pendiente")

        visitas = [v for inst in self.instalaciones for c in inst.contratos for v in c.visitas]
        vencidas = sum(1 for v in visitas if v.estado == "Vencido")
        cumplimiento = round((cumplidos / total) * 100, 1) if total else 0.0

        realizadas = [v.fecha for v in visitas if v.estado == "Realizado"]
        pendientes_fechas = [v.fecha for v in visitas if v.estado not in ("Realizado", "Cancelado")]
        ultima_visita = max(realizadas, default=None)
        proxima_visita = min(pendientes_fechas, default=None)

        return {
            "servicios_contratados": total,
            "servicios_realizados": cumplidos,
            "servicios_pendientes": pendientes,
            "servicios_vencidos": vencidas,
            "cumplimiento_pct": cumplimiento,
            "ultima_visita": ultima_visita,
            "proxima_visita": proxima_visita,
        }

    def deficiencias_abiertas(self):
        """Cuenta las observaciones sin resolver de este cliente, agrupadas
        por clasificación (para las tarjetas en la ficha del cliente)."""
        abiertas = [
            o for inst in self.instalaciones for o in inst.deficiencias if not o.resuelto
        ]
        return {
            clasif: sum(1 for o in abiertas if o.clasificacion == clasif)
            for clasif in CLASIFICACIONES_OBSERVACION
        }

    def deficiencias_abiertas_aprobadas(self):
        """Igual que deficiencias_abiertas(), pero solo cuenta las que ya
        pasaron el control de calidad del Jefe/Administrador — es lo único
        que puede ver el rol Cliente en su portal."""
        abiertas = [
            o
            for inst in self.instalaciones
            for o in inst.deficiencias
            if not o.resuelto and o.estado_revision == "Aprobada"
        ]
        return {
            clasif: sum(1 for o in abiertas if o.clasificacion == clasif)
            for clasif in CLASIFICACIONES_OBSERVACION
        }

    def cumplido_anual_pct(self):
        """% de servicios cumplidos dentro del año de cada contrato ACTIVO
        del cliente (no del año calendario). Si tiene varias instalaciones
        con contratos que arrancan en meses distintos, se combinan todos."""
        items = [
            it
            for inst in self.instalaciones
            for c in inst.contratos
            if c.activo
            for v in c.visitas
            for it in v.items
        ]
        total = len(items)
        cumplidos = sum(1 for it in items if it.estado == "Cumplido")
        return round((cumplidos / total) * 100, 1) if total else 0.0

    def tiene_historial_cumplimiento(self):
        """True si hay al menos un ítem de visita contado en
        cumplido_anual_pct() — para no confundir "0% de cumplimiento"
        (mal desempeño) con "todavía no hay visitas" (sin dato)."""
        return any(
            v.items
            for inst in self.instalaciones
            for c in inst.contratos
            if c.activo
            for v in c.visitas
        )

    def __repr__(self):
        return f"<Cliente {self.nombre}>"


# ---------------------------------------------------------------------------
# Instalación
# ---------------------------------------------------------------------------


class Instalacion(db.Model):
    __tablename__ = "instalaciones"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    direccion = db.Column(db.String(250))
    fecha_alta = db.Column(db.Date, default=date.today, nullable=False)
    observaciones = db.Column(db.Text)

    contratos = db.relationship(
        "Contrato", backref="instalacion", lazy=True, cascade="all, delete-orphan"
    )
    deficiencias = db.relationship(
        "Observacion", backref="instalacion", lazy=True, cascade="all, delete-orphan"
    )
    equipos = db.relationship(
        "Equipo", backref="instalacion", lazy=True, cascade="all, delete-orphan"
    )

    def cumplido_anual_pct(self):
        """% de servicios cumplidos dentro del año de cada contrato ACTIVO
        de esta instalación — mismo criterio que Cliente.cumplido_anual_pct,
        acotado a una sola instalación (para la tarjeta en la ficha del
        cliente)."""
        items = [it for c in self.contratos if c.activo for v in c.visitas for it in v.items]
        total = len(items)
        cumplidos = sum(1 for it in items if it.estado == "Cumplido")
        return round((cumplidos / total) * 100, 1) if total else 0.0

    def proxima_visita(self):
        """Fecha de la próxima visita pendiente (de contrato o manual).
        None si no hay ninguna programada."""
        pendientes = [v.fecha for v in self.visitas if v.estado not in ("Realizado", "Cancelado")]
        return min(pendientes, default=None)

    def deficiencias_abiertas_count(self):
        return sum(1 for o in self.deficiencias if not o.resuelto)

    def __repr__(self):
        return f"<Instalacion {self.nombre}>"


# ---------------------------------------------------------------------------
# Contrato (anual) y Servicios contratados
# ---------------------------------------------------------------------------


class Contrato(db.Model):
    """Un contrato dura 1 año. Agrupa uno o más servicios, cada uno con su
    propia frecuencia. Al crearse, genera automáticamente todas las visitas
    del año, agrupando en una misma fecha los servicios que coincidan."""

    __tablename__ = "contratos"

    id = db.Column(db.Integer, primary_key=True)
    instalacion_id = db.Column(db.Integer, db.ForeignKey("instalaciones.id"), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)  # fecha_inicio + 1 año
    estado = db.Column(db.String(30), default="Activo", nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    servicios = db.relationship(
        "ServicioContrato", backref="contrato", lazy=True, cascade="all, delete-orphan"
    )
    visitas = db.relationship(
        "Visita", backref="contrato", lazy=True, cascade="all, delete-orphan"
    )

    @staticmethod
    def calcular_fecha_fin(fecha_inicio):
        return fecha_inicio + relativedelta(years=1)

    def generar_visitas(self):
        """Genera (o regenera) automáticamente todas las visitas del año de
        contrato, agrupando por fecha los servicios que coincidan. Se llama
        al crear el contrato o al agregar/quitar un servicio."""
        # Borra visitas futuras aún no realizadas para regenerar limpio;
        # conserva las ya realizadas o canceladas manualmente como historial.
        visitas_a_conservar = [v for v in self.visitas if v.estado in ("Realizado", "Cancelado")]
        fechas_conservadas = {v.fecha for v in visitas_a_conservar}

        for v in list(self.visitas):
            if v.estado not in ("Realizado", "Cancelado"):
                db.session.delete(v)
        db.session.flush()

        fechas_por_servicio = {
            s.id: s.fechas_ocurrencia() for s in self.servicios if s.activo
        }
        todas_fechas = sorted(set().union(*fechas_por_servicio.values())) if fechas_por_servicio else []

        for fecha in todas_fechas:
            if fecha in fechas_conservadas:
                continue  # ya hay una visita real/cancelada en esa fecha
            visita = Visita(
                instalacion_id=self.instalacion_id,
                contrato_id=self.id,
                fecha=fecha,
                estado="Pendiente",
            )
            db.session.add(visita)
            db.session.flush()
            for servicio_id, fechas in fechas_por_servicio.items():
                if fecha in fechas:
                    db.session.add(
                        ItemVisita(visita_id=visita.id, servicio_contrato_id=servicio_id, estado="Pendiente")
                    )

            # Cada visita planificada recibe su propia OT preventiva
            ot = OrdenTrabajo(
                instalacion_id=self.instalacion_id,
                visita_id=visita.id,
                tipo="Preventivo",
                prioridad="Media",
                estado="Pendiente",
                fecha_apertura=fecha,
            )
            db.session.add(ot)
            db.session.flush()
            ot.asignar_numero()
        db.session.commit()

    def actualizar_estado_por_vencimiento(self, hoy=None):
        hoy = hoy or date.today()
        if self.estado in ("Renovado", "Cancelado"):
            return
        self.estado = "Vencido" if self.fecha_fin < hoy else "Activo"

    def __repr__(self):
        return f"<Contrato {self.nombre} ({self.fecha_inicio} - {self.fecha_fin})>"


class ServicioContrato(db.Model):
    """Un servicio dentro de un contrato, con su propia frecuencia y,
    opcionalmente, su propio mes de inicio (si no se define, usa el inicio
    del contrato). Las fechas que genere siempre quedan acotadas al año de
    contrato (fecha_fin es fija, no se extiende por servicio)."""

    __tablename__ = "servicios_contrato"

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    frecuencia = db.Column(db.String(30), nullable=False)  # ver FRECUENCIAS_DISPONIBLES
    fecha_inicio = db.Column(db.Date, nullable=True)  # si es None, usa contrato.fecha_inicio
    activo = db.Column(db.Boolean, default=True, nullable=False)
    # Copiado de ServicioTipo.tipo_equipo_aplicable al agregar el servicio al
    # contrato (ver contratos.nuevo_servicio) — filtra el desplegable "Elegir
    # formulario" de la visita para que solo ofrezca los tipos de formulario
    # del mismo tipo de equipo (por categoría, ver categoria_de_tipo_equipo).
    tipo_equipo_aplicable = db.Column(db.String(40), nullable=True)

    items = db.relationship("ItemVisita", backref="servicio", lazy=True, cascade="all, delete-orphan")

    @property
    def fecha_base(self):
        return self.fecha_inicio or self.contrato.fecha_inicio

    def fechas_ocurrencia(self):
        """Todas las fechas de ejecución de este servicio, contadas desde
        fecha_base: la primera ejecución es el propio mes de inicio (n=0),
        luego +1*frecuencia, +2*frecuencia, ..., hasta (sin incluir) la
        fecha de fin del contrato. Se excluye el punto exacto de fecha_fin
        porque ese día es, en la práctica, el inicio del contrato siguiente
        (si se renueva) — incluirlo duplicaría una visita entre ambos.
        Con esto la cantidad total de ejecuciones no cambia respecto a
        contar desde +1*frecuencia: solo se corre la ventana un paso antes.
        Una frecuencia anual que arranca junto con el contrato genera
        entonces una sola fecha (la de inicio), no dos."""
        meses = FRECUENCIAS_MESES.get(self.frecuencia, 12)
        fechas = []
        n = 0
        while True:
            fecha = self.fecha_base + relativedelta(months=meses * n)
            if fecha >= self.contrato.fecha_fin:
                break
            fechas.append(fecha)
            n += 1
        return fechas

    def __repr__(self):
        return f"<ServicioContrato {self.nombre} ({self.frecuencia})>"


# ---------------------------------------------------------------------------
# Visita (agrupa uno o más servicios que coinciden en fecha)
# ---------------------------------------------------------------------------


class Visita(db.Model):
    __tablename__ = "visitas"

    id = db.Column(db.Integer, primary_key=True)
    instalacion_id = db.Column(db.Integer, db.ForeignKey("instalaciones.id"), nullable=False)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=True)
    fecha = db.Column(db.Date, default=date.today, nullable=False)
    tecnico = db.Column(db.String(150))
    observaciones = db.Column(db.Text)
    estado = db.Column(db.String(30), default="Pendiente", nullable=False)

    # Circuito de 3 pasos: Abierta -> En revisión -> Cerrada.
    # El técnico "envía a revisión" (congela su propia edición); recién el
    # Administrador/Jefe puede cerrarla de verdad (bloqueado si quedan
    # observaciones sin aprobar). notas_cierre las escribe el técnico al
    # enviar, el Jefe las puede editar antes de cerrar.
    en_revision = db.Column(db.Boolean, default=False, nullable=False)
    fecha_enviada_revision = db.Column(db.Date, nullable=True)
    enviada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    cerrada = db.Column(db.Boolean, default=False, nullable=False)
    fecha_cierre = db.Column(db.Date, nullable=True)
    notas_cierre = db.Column(db.Text)
    cerrada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    firma_cliente = db.Column(db.Text, nullable=True)  # imagen en base64 (data URI), capturada al enviar a revisión
    firma_tecnico = db.Column(db.Text, nullable=True)  # ídem, firma del técnico que hizo el servicio

    # Nota para el cliente: la carga el Administrador/Jefe, visible en el
    # portal del cliente junto a la fecha en que se escribió.
    nota_cliente = db.Column(db.Text, nullable=True)
    nota_cliente_fecha = db.Column(db.Date, nullable=True)

    items = db.relationship("ItemVisita", backref="visita", lazy=True, cascade="all, delete-orphan")

    instalacion = db.relationship("Instalacion", backref=db.backref("visitas", lazy=True))
    cerrada_por = db.relationship("Usuario", backref="visitas_cerradas", foreign_keys=[cerrada_por_id])
    enviada_por = db.relationship("Usuario", backref="visitas_enviadas_revision", foreign_keys=[enviada_por_id])

    @property
    def fase(self):
        if self.cerrada:
            return "Cerrada"
        if self.en_revision:
            return "En revisión"
        return "Abierta"

    def marcar_item_cumplido(self, item_id):
        for item in self.items:
            if item.id == item_id:
                item.estado = "Cumplido"
        self._sincronizar_estado_general()

    def marcar_item_pendiente(self, item_id):
        for item in self.items:
            if item.id == item_id:
                item.estado = "Pendiente"
        self._sincronizar_estado_general()

    def _sincronizar_estado_general(self):
        """El estado general de la visita refleja sus items: Realizado solo
        si todos están Cumplidos (o Cancelados)."""
        if not self.items:
            return
        estados = {it.estado for it in self.items}
        if estados <= {"Cumplido", "Cancelado"}:
            self.estado = "Realizado"
        elif "Cumplido" in estados:
            self.estado = "En proceso"

    def actualizar_estado_por_vencimiento(self, hoy=None):
        hoy = hoy or date.today()
        if self.estado in ("Realizado", "Cancelado"):
            return
        if self.fecha < hoy:
            self.estado = "Vencido"
        elif self.estado == "Vencido" and self.fecha >= hoy:
            self.estado = "Pendiente"

    @property
    def etiqueta_calendario(self):
        return ETIQUETA_CALENDARIO.get(self.estado, self.estado)

    @property
    def clase_calendario(self):
        return CLASE_CALENDARIO.get(self.etiqueta_calendario, "secondary")

    @property
    def observaciones_de_la_visita(self):
        """Todas las observaciones cargadas a través de esta visita (por
        cualquiera de sus servicios), sin importar su estado de revisión."""
        from app.models import Observacion

        ids_items = [it.id for it in self.items]
        if not ids_items:
            return []
        return Observacion.query.filter(Observacion.item_visita_id.in_(ids_items)).all()

    @property
    def observaciones_pendientes_de_revision(self):
        return [o for o in self.observaciones_de_la_visita if o.estado_revision == "Pendiente"]

    @property
    def nombre_tecnico(self):
        """El técnico de una visita se gestiona en su OT (un solo lugar,
        para que nunca quede desincronizado). 'tecnico' (texto libre)
        queda solo como resabio de visitas viejas sin OT asociada."""
        if self.orden_trabajo:
            return self.orden_trabajo.nombre_tecnico
        return self.tecnico or "-"

    def __repr__(self):
        return f"<Visita {self.fecha}>"


class ItemVisita(db.Model):
    """Cada servicio contratado dentro de una visita agrupada; se marca
    cumplido/pendiente de forma independiente del resto."""

    __tablename__ = "items_visita"

    id = db.Column(db.Integer, primary_key=True)
    visita_id = db.Column(db.Integer, db.ForeignKey("visitas.id"), nullable=False)
    servicio_contrato_id = db.Column(db.Integer, db.ForeignKey("servicios_contrato.id"), nullable=False)
    estado = db.Column(db.String(30), default="Pendiente", nullable=False)
    observaciones = db.Column(db.Text)

    formularios = db.relationship("Formulario", backref="item_visita", lazy=True, cascade="all, delete-orphan")
    fotos = db.relationship("Foto", backref="item_visita", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ItemVisita {self.servicio.nombre if self.servicio else ''}>"


# ---------------------------------------------------------------------------
# Formularios (tipos dinámicos, sin modificar el núcleo)
# ---------------------------------------------------------------------------


class TipoFormulario(db.Model):
    """Define un tipo de formulario y su esquema de campos. Pertenece a un
    Cliente puntual (cada instalación es distinta) y lo puede crear y usar
    cualquier técnico/administrador de la empresa asignado a ese cliente.

    Si por_equipo=True, este formulario se completa una vez por cada equipo
    de la instalación (ej: un checklist de ECA se llena por cada ECA),
    en vez de una sola vez para toda la visita. tipo_equipo_aplicable filtra
    qué tipo de equipo corresponde (ej: "ECA")."""

    __tablename__ = "tipos_formulario"
    __table_args__ = (db.UniqueConstraint("cliente_id", "nombre", name="uq_tipo_formulario_cliente_nombre"),)

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    schema_json = db.Column(db.Text, nullable=False)  # lista de campos: [{campo, tipo, label, opciones?}]
    por_equipo = db.Column(db.Boolean, default=False, nullable=False)
    tipo_equipo_aplicable = db.Column(db.String(40), nullable=True)  # nombre de un TipoEquipo

    cliente = db.relationship("Cliente", backref=db.backref("tipos_formulario", cascade="all, delete-orphan"))

    def campos(self):
        import json

        return json.loads(self.schema_json) if self.schema_json else []

    def aplica_a_servicio(self, servicio_contrato):
        """True si este tipo de formulario debería ofrecerse para ese
        servicio de un contrato. Sin tipo de equipo propio (formulario
        general, ej. checklist mensual) aplica a cualquier servicio. Con
        tipo de equipo, solo aplica si cae en la misma categoría que el
        tipo de equipo del servicio (ver categoria_de_tipo_equipo) — si el
        servicio no tiene tipo de equipo asignado, no se filtra nada
        (comportamiento de siempre)."""
        if not self.tipo_equipo_aplicable:
            return True
        if not servicio_contrato.tipo_equipo_aplicable:
            return True
        return categoria_de_tipo_equipo(self.tipo_equipo_aplicable) == categoria_de_tipo_equipo(
            servicio_contrato.tipo_equipo_aplicable
        )

    def __repr__(self):
        return f"<TipoFormulario {self.nombre}>"


class ServicioTipo(db.Model):
    """Catálogo de servicios reutilizables a nivel Empresa (ej. 'Checklist
    de BIE', 'Inspección visual'), cada uno con su propio formulario base.
    Al elegirse desde el desplegable al agregar un servicio a un contrato,
    se 'importa' (copia) al Cliente correspondiente como un TipoFormulario
    propio — si el cliente ya tenía uno con ese nombre, se reutiliza en vez
    de duplicar. Esa copia queda independiente: editar el servicio tipo acá
    no actualiza las copias ya importadas, y viceversa."""

    __tablename__ = "servicios_tipo"
    __table_args__ = (db.UniqueConstraint("empresa_id", "nombre", name="uq_servicio_tipo_empresa_nombre"),)

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    schema_json = db.Column(db.Text, nullable=False)
    por_equipo = db.Column(db.Boolean, default=False, nullable=False)
    tipo_equipo_aplicable = db.Column(db.String(40), nullable=True)  # nombre de un TipoEquipo

    empresa = db.relationship("Empresa", backref="servicios_tipo")

    def campos(self):
        import json

        return json.loads(self.schema_json) if self.schema_json else []

    def __repr__(self):
        return f"<ServicioTipo {self.nombre}>"


class Formulario(db.Model):
    __tablename__ = "formularios"

    id = db.Column(db.Integer, primary_key=True)
    item_visita_id = db.Column(db.Integer, db.ForeignKey("items_visita.id"), nullable=False)
    tipo_formulario_id = db.Column(db.Integer, db.ForeignKey("tipos_formulario.id"), nullable=False)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=True)
    datos_json = db.Column(db.Text)  # respuestas, según el schema del tipo
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tipo_formulario = db.relationship("TipoFormulario")
    equipo = db.relationship("Equipo", backref="formularios")

    def datos(self):
        import json

        return json.loads(self.datos_json) if self.datos_json else {}

    def set_datos(self, dict_datos):
        import json

        self.datos_json = json.dumps(dict_datos)

    def __repr__(self):
        return f"<Formulario {self.tipo_formulario.nombre if self.tipo_formulario else ''}>"


# ---------------------------------------------------------------------------
# Fotos (evidencia fotográfica por servicio realizado)
# ---------------------------------------------------------------------------


class Foto(db.Model):
    """Evidencia fotográfica. Puede venir de un servicio puntual dentro de
    una visita (item_visita_id, el flujo de siempre) o cargarse suelta
    contra un equipo/instalación (item_visita_id=None) — para una foto
    fuera de una visita o para migrar fotos de un sistema anterior.

    instalacion_id/equipo_id quedan completos siempre que se pueda (incluso
    para las que sí vienen de una visita), para poder armar el banco de
    fotos por cliente/instalación/equipo sin depender de la cadena
    item_visita -> visita -> instalación. equipo_id queda en None cuando la
    foto no es de un equipo puntual (ej. una foto general de la sala)."""

    __tablename__ = "fotos"

    id = db.Column(db.Integer, primary_key=True)
    item_visita_id = db.Column(db.Integer, db.ForeignKey("items_visita.id"), nullable=True)
    instalacion_id = db.Column(db.Integer, db.ForeignKey("instalaciones.id"), nullable=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=True)
    observacion_id = db.Column(db.Integer, db.ForeignKey("observaciones.id"), nullable=True)
    nombre_archivo = db.Column(db.String(300), nullable=False)  # ruta relativa dentro de UPLOAD_FOLDER
    descripcion = db.Column(db.String(250))
    origen = db.Column(db.String(20), default="Visita", nullable=False)  # ver ORIGENES_FOTO
    fecha_toma = db.Column(db.Date, nullable=True)  # cuándo se sacó, no cuándo se cargó al sistema
    fecha_subida = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    subido_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    instalacion = db.relationship("Instalacion", backref="fotos")
    equipo = db.relationship("Equipo", backref="fotos")
    observacion = db.relationship("Observacion", backref="fotos")
    subido_por = db.relationship("Usuario", foreign_keys=[subido_por_id])

    def __repr__(self):
        return f"<Foto {self.nombre_archivo}>"


# ---------------------------------------------------------------------------
# Observaciones (deficiencias / desactivaciones) — dashboard de novedades
# ---------------------------------------------------------------------------


class Observacion(db.Model):
    """Registro de una deficiencia, deficiencia crítica o desactivación
    detectada en una instalación. Puede originarse en un servicio puntual
    (item_visita_id) o cargarse a mano (para migrar historial existente).

    Al resolverse, NO se borra: se marca resuelto=True y se completa
    fecha_resolucion, saliendo del conteo del dashboard pero quedando
    visible en el histórico técnico de la instalación.

    estado_revision: control de calidad antes de que algo se considere
    "listo para el cliente". El técnico la carga como Pendiente; el
    Administrador (Jefe técnico) la aprueba, la edita y aprueba, o la
    elimina. Una vez Aprobada, deja de poder editarse (si hace falta
    corregirla, el Administrador la borra y se carga una nueva). El
    cierre de una visita queda bloqueado mientras tenga observaciones
    Pendientes.

    ultima_visita_confirmada_id / fecha_ultima_confirmacion: rastro de que
    la deficiencia se siguió viendo en visitas posteriores a la que la
    detectó, sin ser un paso extra para el técnico — se completa solo al
    guardar un checklist de ese equipo mientras siga abierta (ver
    Observacion.confirmar_vigencia y formularios.nuevo)."""

    __tablename__ = "observaciones"

    id = db.Column(db.Integer, primary_key=True)
    instalacion_id = db.Column(db.Integer, db.ForeignKey("instalaciones.id"), nullable=False)
    item_visita_id = db.Column(db.Integer, db.ForeignKey("items_visita.id"), nullable=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=True)
    clasificacion = db.Column(db.String(40), nullable=False)  # ver CLASIFICACIONES_OBSERVACION
    descripcion = db.Column(db.Text, nullable=False)
    fecha_carga = db.Column(db.Date, default=date.today, nullable=False)
    resuelto = db.Column(db.Boolean, default=False, nullable=False)
    fecha_resolucion = db.Column(db.Date, nullable=True)
    estado_revision = db.Column(db.String(20), default="Pendiente", nullable=False)  # Pendiente / Aprobada
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    aprobado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    fecha_aprobacion = db.Column(db.Date, nullable=True)
    resuelto_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    reabierto_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    fecha_reapertura = db.Column(db.Date, nullable=True)
    # Se completan solos (sin que el técnico haga nada aparte) cada vez que
    # guarda un checklist de un equipo con esta deficiencia todavía
    # abierta — deja rastro de que se la volvió a ver en esa visita, sin
    # sumarle un paso más al flujo de carga (ver formularios.nuevo).
    ultima_visita_confirmada_id = db.Column(db.Integer, db.ForeignKey("visitas.id"), nullable=True)
    fecha_ultima_confirmacion = db.Column(db.Date, nullable=True)
    confirmada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    # Solo tiene sentido para Deficiencia crítica/no crítica (se valida en
    # observaciones.nueva) — dispara la creación de un Presupuesto para no
    # depender de que el mail de solicitud le llegue a quien presupuesta.
    requiere_presupuesto = db.Column(db.Boolean, default=False, nullable=False)

    item_visita = db.relationship("ItemVisita", backref="observaciones_registradas")
    equipo = db.relationship("Equipo", backref="deficiencias")
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    aprobado_por = db.relationship("Usuario", foreign_keys=[aprobado_por_id])
    resuelto_por = db.relationship("Usuario", foreign_keys=[resuelto_por_id])
    reabierto_por = db.relationship("Usuario", foreign_keys=[reabierto_por_id])
    ultima_visita_confirmada = db.relationship("Visita", foreign_keys=[ultima_visita_confirmada_id])
    confirmada_por = db.relationship("Usuario", foreign_keys=[confirmada_por_id])

    @property
    def editable(self):
        """Mismo criterio que observaciones._verificar_editable, para
        poder ocultar el link de Editar en los templates sin duplicar la
        condición en cada uno."""
        if self.estado_revision == "Aprobada":
            return False
        if self.presupuesto and self.presupuesto.estado != "Pendiente":
            return False
        return True

    @property
    def visita(self):
        """La visita en la que se cargó, si vino de un servicio puntual
        (None para observaciones cargadas a mano, sin item_visita)."""
        return self.item_visita.visita if self.item_visita_id else None

    def confirmar_vigencia(self, visita_id, usuario_id=None, fecha=None):
        self.ultima_visita_confirmada_id = visita_id
        self.fecha_ultima_confirmacion = fecha or date.today()
        self.confirmada_por_id = usuario_id

    def marcar_resuelta(self, usuario_id=None, fecha=None):
        self.resuelto = True
        self.fecha_resolucion = fecha or date.today()
        self.resuelto_por_id = usuario_id

    def reabrir(self, usuario_id=None):
        self.resuelto = False
        self.fecha_resolucion = None
        self.resuelto_por_id = None
        self.reabierto_por_id = usuario_id
        self.fecha_reapertura = date.today()

    def aprobar(self, usuario_id=None):
        self.estado_revision = "Aprobada"
        self.aprobado_por_id = usuario_id
        self.fecha_aprobacion = date.today()

    def __repr__(self):
        return f"<Observacion {self.clasificacion} - {self.instalacion_id}>"


# ---------------------------------------------------------------------------
# Presupuestos — trazabilidad de una deficiencia que necesita presupuestarse
# ---------------------------------------------------------------------------

ESTADOS_PRESUPUESTO = ["Pendiente", "Cotizado", "Aprobado", "Rechazado", "Cerrado"]


class Presupuesto(db.Model):
    """Trazabilidad de una solicitud de presupuesto disparada por una
    deficiencia (crítica o no crítica) marcada 'requiere presupuesto' al
    cargarla. No es facturación ni cotización en sí — es el seguimiento de
    que la solicitud no se pierda entre el técnico en terreno y quien
    presupuesta, con un código único para que el cliente lo mencione en su
    mail de solicitud formal.

    Al aprobarse, genera automáticamente la OT correctiva que ejecuta el
    trabajo (mismo criterio que ya usa Contrato.generar_visitas() para no
    depender de que alguien se acuerde de crearla a mano). Al finalizar esa
    OT (ver ordenes_trabajo.editar), el presupuesto pasa solo a Cerrado y
    la deficiencia queda resuelta — ver auto-cierre en ese mismo lugar."""

    __tablename__ = "presupuestos"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)  # PRESUP-2026-0001
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    observacion_id = db.Column(db.Integer, db.ForeignKey("observaciones.id"), nullable=False)
    ot_correctiva_id = db.Column(db.Integer, db.ForeignKey("ordenes_trabajo.id"), nullable=True)
    estado = db.Column(db.String(20), default="Pendiente", nullable=False)  # ver ESTADOS_PRESUPUESTO
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    empresa = db.relationship("Empresa", backref="presupuestos")
    observacion = db.relationship("Observacion", backref=db.backref("presupuesto", uselist=False))
    ot_correctiva = db.relationship("OrdenTrabajo", backref=db.backref("presupuesto_origen", uselist=False))
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    auditoria = db.relationship(
        "PresupuestoAudit",
        backref="presupuesto",
        cascade="all, delete-orphan",
        order_by="PresupuestoAudit.fecha_cambio",
    )

    @property
    def dias_abierto(self):
        return (datetime.utcnow() - self.fecha_creacion).days

    def cambiar_estado(self, nuevo_estado, usuario_id, nota=None):
        """Cambia de estado y deja rastro en el audit log. Al pasar a
        Aprobado, genera la OT correctiva si todavía no existe — no
        depende de que un humano se acuerde de crearla."""
        estado_anterior = self.estado
        self.estado = nuevo_estado

        if nuevo_estado == "Aprobado" and not self.ot_correctiva_id:
            ot = OrdenTrabajo(
                instalacion_id=self.observacion.instalacion_id,
                tipo="Correctivo",
                prioridad="Media",
                estado="Pendiente",
                descripcion=f"Ejecución presupuesto {self.codigo}: {self.observacion.descripcion}",
                fecha_apertura=date.today(),
            )
            db.session.add(ot)
            db.session.flush()
            ot.asignar_numero()
            self.ot_correctiva_id = ot.id

        db.session.add(
            PresupuestoAudit(
                presupuesto_id=self.id,
                estado_anterior=estado_anterior,
                estado_nuevo=nuevo_estado,
                usuario_id=usuario_id,
                nota=nota,
            )
        )

    def __repr__(self):
        return f"<Presupuesto {self.codigo} ({self.estado})>"


class PresupuestoAudit(db.Model):
    """Un renglón por cada cambio de estado de un Presupuesto — de solo
    consulta, nunca se edita ni se borra un renglón ya cargado."""

    __tablename__ = "presupuestos_audit"

    id = db.Column(db.Integer, primary_key=True)
    presupuesto_id = db.Column(db.Integer, db.ForeignKey("presupuestos.id"), nullable=False)
    estado_anterior = db.Column(db.String(20), nullable=True)
    estado_nuevo = db.Column(db.String(20), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    nota = db.Column(db.Text, nullable=True)
    fecha_cambio = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    usuario = db.relationship("Usuario")

    def __repr__(self):
        return f"<PresupuestoAudit {self.presupuesto_id} -> {self.estado_nuevo}>"


# ---------------------------------------------------------------------------
# Tipos de equipo (catálogo editable) — ECA, manifold, bomba, etc.
# ---------------------------------------------------------------------------


class TipoEquipo(db.Model):
    """Catálogo de tipos de equipo disponibles al cargar un Equipo nuevo y
    al definir a qué tipo de equipo aplica un TipoFormulario/ServicioTipo
    (tipo_equipo_aplicable). Arranca con ECA/Manifold/Bomba/BIE/Otro (ver
    _seed_tipos_equipo en app/__init__.py), pero cualquier Administrador,
    Jefe o Técnico puede sumar tipos nuevos desde la pantalla de equipos.

    categoria agrupa los tipos en la navegación del portal de cliente y al
    elegir equipo dentro de una visita (ver categorias_equipo_agrupadas)."""

    __tablename__ = "tipos_equipo"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(40), unique=True, nullable=False)
    categoria = db.Column(db.String(80), nullable=False, default="Otros equipos")

    def __repr__(self):
        return f"<TipoEquipo {self.nombre}>"


def nombres_tipos_equipo():
    """Nombres de tipo de equipo disponibles, para los desplegables de
    Equipo.tipo y de tipo_equipo_aplicable (TipoFormulario/ServicioTipo)."""
    return [t.nombre for t in TipoEquipo.query.order_by(TipoEquipo.nombre).all()]


def categorias_equipo_agrupadas():
    """Tipos de equipo agrupados por categoría: las categorías base
    (CATEGORIAS_EQUIPO_ORDEN) primero, en ese orden, y cualquier categoría
    nueva escrita a mano al final, en orden alfabético."""
    grupos = {}
    for t in TipoEquipo.query.order_by(TipoEquipo.nombre).all():
        grupos.setdefault(t.categoria, []).append(t.nombre)
    orden = [c for c in CATEGORIAS_EQUIPO_ORDEN if c in grupos]
    orden += sorted(c for c in grupos if c not in CATEGORIAS_EQUIPO_ORDEN)
    return [(categoria, grupos[categoria]) for categoria in orden]


def categoria_de_tipo_equipo(nombre_tipo_equipo):
    """La categoría (Sala de bombas, Bocas de incendio, etc) a la que
    pertenece un nombre de tipo de equipo. None si no está cargado en el
    catálogo (ej. quedó huérfano tras eliminarse el TipoEquipo)."""
    if not nombre_tipo_equipo:
        return None
    for categoria, tipos in categorias_equipo_agrupadas():
        if nombre_tipo_equipo in tipos:
            return categoria
    return None


# ---------------------------------------------------------------------------
# Equipos (ECA, manifolds, bombas) — registro físico por instalación
# ---------------------------------------------------------------------------


class Equipo(db.Model):
    """Equipo físico fijo de una instalación (ECA, manifold, bomba, etc).
    No tiene frecuencia de mantenimiento propia (eso lo maneja ServicioContrato);
    existe para poder ligar checklists puntuales (ej. checklist de ECA) a
    un equipo concreto, y para modelar arreglos reales: ECA sueltos en
    distintos puntos, o agrupados bajo un manifold general."""

    __tablename__ = "equipos"

    id = db.Column(db.Integer, primary_key=True)
    instalacion_id = db.Column(db.Integer, db.ForeignKey("instalaciones.id"), nullable=False)
    tipo = db.Column(db.String(40), nullable=False)  # nombre de un TipoEquipo
    nombre = db.Column(db.String(150), nullable=False)  # ej: "ECA 3° piso ala norte"
    ubicacion = db.Column(db.String(250))
    manifold_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    # Datos de placa, solo aplican para tipo in TIPOS_CON_DATOS_PLACA (ver
    # módulo de curva de caudal). Quedan nullable porque no tienen sentido
    # para el resto de los tipos de equipo.
    modelo = db.Column(db.String(150), nullable=True)
    serie = db.Column(db.String(150), nullable=True)
    caudal_nominal = db.Column(db.Float, nullable=True)  # GPM
    presion_diseno = db.Column(db.Float, nullable=True)  # PSI
    rpm_nominal = db.Column(db.Integer, nullable=True)
    anio_fabricacion = db.Column(db.Integer, nullable=True)
    otros_datos_placa = db.Column(db.Text, nullable=True)

    # Datos de motor, también solo para tipo in TIPOS_CON_DATOS_PLACA. Campos
    # fijos en vez de un formulario dinámico: son bastante estándar en la
    # industria (NFPA 20), así que no hace falta que cada cliente los redefina.
    tipo_motor = db.Column(db.String(20), nullable=True)  # "Eléctrico" / "Diesel"
    motor_potencia_hp = db.Column(db.Float, nullable=True)  # común a los dos tipos
    # Solo si tipo_motor == "Eléctrico"
    motor_voltaje = db.Column(db.Float, nullable=True)
    motor_amperaje = db.Column(db.Float, nullable=True)
    motor_fases = db.Column(db.Integer, nullable=True)
    # Solo si tipo_motor == "Diesel"
    motor_marca_modelo = db.Column(db.String(150), nullable=True)
    motor_combustible_litros = db.Column(db.Float, nullable=True)
    motor_horas_uso = db.Column(db.Float, nullable=True)
    motor_estado_bateria = db.Column(db.String(100), nullable=True)

    equipos_hijos = db.relationship(
        "Equipo", backref=db.backref("manifold", remote_side=[id]), lazy=True
    )

    def __repr__(self):
        return f"<Equipo {self.tipo}: {self.nombre}>"


# ---------------------------------------------------------------------------
# Curva de caudal — ensayo de bombas contra incendio según NFPA 25
# ---------------------------------------------------------------------------


class CurvaFabrica(db.Model):
    """Curva de referencia del fabricante para una bomba puntual (Equipo con
    tipo='Bomba'): presión neta a 0/50/100/150% del caudal nominal, todas
    medidas a la misma RPM (rpm_nominal). Es 1 a 1 con el equipo — cargarla
    de nuevo sobrescribe la anterior, no se versiona."""

    __tablename__ = "curvas_fabrica"

    id = db.Column(db.Integer, primary_key=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), unique=True, nullable=False)
    rpm_nominal = db.Column(db.Integer, nullable=False)
    punto_0_presion = db.Column(db.Float, nullable=False)
    punto_50_presion = db.Column(db.Float, nullable=False)
    punto_100_presion = db.Column(db.Float, nullable=False)
    punto_150_presion = db.Column(db.Float, nullable=False)
    # Potencia de placa del fabricante en cada punto — opcional (no todos
    # los fabricantes la publican por punto de caudal).
    punto_0_potencia_kw = db.Column(db.Float, nullable=True)
    punto_50_potencia_kw = db.Column(db.Float, nullable=True)
    punto_100_potencia_kw = db.Column(db.Float, nullable=True)
    punto_150_potencia_kw = db.Column(db.Float, nullable=True)
    fecha_ingreso = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    equipo = db.relationship(
        "Equipo", backref=db.backref("curva_fabrica", uselist=False, cascade="all, delete-orphan")
    )

    def puntos(self):
        """([0, 50, 100, 150], [presiones netas]) — mismo orden que
        EnsayoCaudal.puntos_netos(), para poder comparar índice a índice."""
        return (
            [0, 50, 100, 150],
            [self.punto_0_presion, self.punto_50_presion, self.punto_100_presion, self.punto_150_presion],
        )

    def potencias(self):
        """Potencia de placa por punto (kW), puede tener None sueltos si no
        se cargó para ese punto."""
        return [self.punto_0_potencia_kw, self.punto_50_potencia_kw, self.punto_100_potencia_kw, self.punto_150_potencia_kw]

    def __repr__(self):
        return f"<CurvaFabrica equipo={self.equipo_id}>"


class EnsayoCaudal(db.Model):
    """Un ensayo de caudal puntual (una fecha) de una bomba: 4 puntos
    (0/50/100/150% del caudal nominal), cada uno con su propia RPM medida en
    campo (puede no coincidir con la RPM de la curva de fábrica — por eso se
    corrige con la ley de afinidad antes de comparar, ver
    utils.calcular_presion_ajustada). Se guarda un registro por año/ensayo,
    para armar el histórico de tendencia de la bomba."""

    __tablename__ = "ensayos_caudal"
    __table_args__ = (db.UniqueConstraint("equipo_id", "fecha_ensayo", name="uq_ensayo_equipo_fecha"),)

    id = db.Column(db.Integer, primary_key=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=False)
    fecha_ensayo = db.Column(db.Date, nullable=False)

    rpm_punto_0 = db.Column(db.Integer, nullable=False)
    presion_descarga_punto_0 = db.Column(db.Float, nullable=False)
    presion_succion_punto_0 = db.Column(db.Float, nullable=False)
    presion_neta_punto_0 = db.Column(db.Float, nullable=False)  # descarga - succión
    caudal_gpm_punto_0 = db.Column(db.Float, nullable=True)  # medido en campo; si falta, se estima desde equipo.caudal_nominal
    potencia_absorbida_punto_0 = db.Column(db.Float, nullable=True)  # kW — opcional (ej. motor diésel sin instrumentar)

    rpm_punto_50 = db.Column(db.Integer, nullable=False)
    presion_descarga_punto_50 = db.Column(db.Float, nullable=False)
    presion_succion_punto_50 = db.Column(db.Float, nullable=False)
    presion_neta_punto_50 = db.Column(db.Float, nullable=False)
    caudal_gpm_punto_50 = db.Column(db.Float, nullable=True)
    potencia_absorbida_punto_50 = db.Column(db.Float, nullable=True)

    rpm_punto_100 = db.Column(db.Integer, nullable=False)
    presion_descarga_punto_100 = db.Column(db.Float, nullable=False)
    presion_succion_punto_100 = db.Column(db.Float, nullable=False)
    presion_neta_punto_100 = db.Column(db.Float, nullable=False)
    caudal_gpm_punto_100 = db.Column(db.Float, nullable=True)
    potencia_absorbida_punto_100 = db.Column(db.Float, nullable=True)

    rpm_punto_150 = db.Column(db.Integer, nullable=False)
    presion_descarga_punto_150 = db.Column(db.Float, nullable=False)
    presion_succion_punto_150 = db.Column(db.Float, nullable=False)
    presion_neta_punto_150 = db.Column(db.Float, nullable=False)
    caudal_gpm_punto_150 = db.Column(db.Float, nullable=True)
    potencia_absorbida_punto_150 = db.Column(db.Float, nullable=True)

    # Condiciones de prueba — contexto del ensayo, todas opcionales.
    temperatura_ambiente = db.Column(db.Float, nullable=True)  # °C
    presion_atmosferica_mbar = db.Column(db.Float, nullable=True)
    presion_succion_estatica = db.Column(db.Float, nullable=True)  # PSI, condición general (no por punto)
    normativa_aplicable = db.Column(db.Text, nullable=True)

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Firma del Jefe/Administrador, independiente del cálculo NFPA25 (ver
    # resultado_nfpa25): el técnico carga el ensayo como Pendiente, y solo
    # Administrador/Jefe puede validarlo o rechazarlo — mismo patrón que
    # Observacion.estado_revision.
    estado_revision = db.Column(db.String(20), default="Pendiente", nullable=False)  # Pendiente/Validado/Rechazado
    validado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    fecha_validacion = db.Column(db.DateTime, nullable=True)

    comentarios = db.Column(db.Text, nullable=True)

    # Resultado NFPA25 fijado a mano por el Administrador/Jefe, independiente
    # del cálculo (ver resultado_nfpa25) — None/"Aprobado"/"Rechazado". Sirve
    # para los casos donde el criterio de ingeniería difiere del cálculo
    # estricto de los 3 puntos; resultado_final() es el que hay que usar en
    # toda la app para mostrar/decidir el resultado.
    resultado_manual = db.Column(db.String(20), nullable=True)

    equipo = db.relationship(
        "Equipo",
        backref=db.backref(
            "ensayos_caudal", lazy=True, cascade="all, delete-orphan", order_by="EnsayoCaudal.fecha_ensayo"
        ),
    )
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    validado_por = db.relationship("Usuario", foreign_keys=[validado_por_id])

    def validar(self, usuario_id):
        self.estado_revision = "Validado"
        self.validado_por_id = usuario_id
        self.fecha_validacion = datetime.utcnow()

    def rechazar(self, usuario_id):
        self.estado_revision = "Rechazado"
        self.validado_por_id = usuario_id
        self.fecha_validacion = datetime.utcnow()

    def puntos_netos(self):
        return [self.presion_neta_punto_0, self.presion_neta_punto_50, self.presion_neta_punto_100, self.presion_neta_punto_150]

    def puntos_rpm(self):
        return [self.rpm_punto_0, self.rpm_punto_50, self.rpm_punto_100, self.rpm_punto_150]

    def puntos_gpm(self):
        """Caudal medido por punto; si no se cargó (None), se estima como
        el % nominal del caudal de placa del equipo (0/50/100/150%)."""
        medidos = [self.caudal_gpm_punto_0, self.caudal_gpm_punto_50, self.caudal_gpm_punto_100, self.caudal_gpm_punto_150]
        nominal = self.equipo.caudal_nominal if self.equipo else None
        porcentajes = [0, 0.5, 1, 1.5]
        return [
            medido if medido is not None else (nominal * pct if nominal else None)
            for medido, pct in zip(medidos, porcentajes)
        ]

    def puntos_potencia_absorbida(self):
        return [
            self.potencia_absorbida_punto_0, self.potencia_absorbida_punto_50,
            self.potencia_absorbida_punto_100, self.potencia_absorbida_punto_150,
        ]

    def puntos_ajustados(self, rpm_nominal_fabrica):
        """Presión neta de cada punto, corregida a la RPM de la curva de
        fábrica — lo que realmente se compara contra ella."""
        from app.utils import calcular_presion_ajustada

        return [
            calcular_presion_ajustada(neta, rpm, rpm_nominal_fabrica)
            for neta, rpm in zip(self.puntos_netos(), self.puntos_rpm())
        ]

    def validacion_nfpa25(self):
        """dict de validar_nfpa25(), o None si el equipo todavía no tiene
        curva de fábrica cargada (no hay contra qué comparar)."""
        if not self.equipo.curva_fabrica:
            return None
        from app.utils import validar_nfpa25

        ajustadas = self.puntos_ajustados(self.equipo.curva_fabrica.rpm_nominal)
        _, presiones_fabrica = self.equipo.curva_fabrica.puntos()
        return validar_nfpa25(ajustadas, presiones_fabrica)

    def resultado_nfpa25(self):
        """True (aprobado) / False (rechazado) / None (sin curva de fábrica
        para comparar) — solo el cálculo automático de los 3 criterios."""
        validacion = self.validacion_nfpa25()
        if validacion is None:
            return None
        return all(criterio["paso"] for criterio in validacion.values())

    def resultado_final(self):
        """El resultado a mostrar/usar en toda la app: si el Administrador/
        Jefe fijó un resultado manual, ese manda por sobre el cálculo."""
        if self.resultado_manual == "Aprobado":
            return True
        if self.resultado_manual == "Rechazado":
            return False
        return self.resultado_nfpa25()

    def __repr__(self):
        return f"<EnsayoCaudal equipo={self.equipo_id} {self.fecha_ensayo}>"


# ---------------------------------------------------------------------------
# Órdenes de trabajo — unifican visitas planificadas y trabajo correctivo
# ---------------------------------------------------------------------------


class OrdenTrabajo(db.Model):
    """Formato de orden de trabajo (OT):

    - numero: identificador visible (OT-00001), autogenerado.
    - tipo: 'Preventivo' si viene de una visita planificada (contrato/
      servicio), 'Correctivo' si es trabajo suelto sin contrato de por medio
      (reparación puntual, llamado de cliente, etc).
    - visita_id: solo se completa en las OT preventivas — la visita
      planificada que le dio origen. Las correctivas quedan sin visita.
    - tecnico / tecnico_id: las OT nuevas asignan un Usuario real (rol
      Técnico) vía tecnico_id — así el técnico puede ver "mis OT
      asignadas". El campo de texto 'tecnico' queda solo como resabio de
      antes de tener usuarios reales; ya no se completa en OT nuevas.
    - Toda OT pertenece a una instalación, tiene prioridad,
      estado, fechas de apertura/cierre, descripción del trabajo y
      observaciones, y puede tener repuestos consumidos (RepuestoUsado),
      que descuentan stock del inventario automáticamente.

    Cada Visita generada automáticamente por un contrato recibe su propia
    OT preventiva (ver Contrato.generar_visitas). El trabajo correctivo se
    carga directamente como una OT nueva, sin pasar por contrato ni
    servicio."""

    __tablename__ = "ordenes_trabajo"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True)
    instalacion_id = db.Column(db.Integer, db.ForeignKey("instalaciones.id"), nullable=False)
    visita_id = db.Column(db.Integer, db.ForeignKey("visitas.id"), nullable=True)
    tipo = db.Column(db.String(20), nullable=False)  # ver TIPOS_OT
    prioridad = db.Column(db.String(20), default="Media", nullable=False)  # ver PRIORIDADES_OT
    estado = db.Column(db.String(20), default="Pendiente", nullable=False)  # ver ESTADOS_OT
    tecnico = db.Column(db.String(150))  # resabio de antes de tener usuarios reales
    tecnico_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    descripcion = db.Column(db.Text)
    observaciones = db.Column(db.Text)
    fecha_apertura = db.Column(db.Date, default=date.today, nullable=False)
    fecha_cierre = db.Column(db.Date, nullable=True)

    instalacion = db.relationship("Instalacion", backref="ordenes_trabajo")
    tecnico_usuario = db.relationship("Usuario", backref="ordenes_trabajo_asignadas")
    visita = db.relationship(
        "Visita", backref=db.backref("orden_trabajo", uselist=False, cascade="all, delete-orphan", single_parent=True)
    )
    repuestos_usados = db.relationship(
        "RepuestoUsado", backref="orden_trabajo", lazy=True, cascade="all, delete-orphan"
    )

    def asignar_numero(self):
        """Se llama después del primer flush, cuando ya existe self.id."""
        self.numero = f"OT-{self.id:05d}"

    @property
    def nombre_tecnico(self):
        if self.tecnico_usuario:
            return self.tecnico_usuario.nombre_completo or self.tecnico_usuario.username
        return self.tecnico or "-"

    def __repr__(self):
        return f"<OrdenTrabajo {self.numero}>"


# ---------------------------------------------------------------------------
# Inventario de repuestos
# ---------------------------------------------------------------------------


class Repuesto(db.Model):
    __tablename__ = "repuestos"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    codigo = db.Column(db.String(60))
    unidad = db.Column(db.String(30), default="unidad")
    stock_actual = db.Column(db.Integer, default=0, nullable=False)
    stock_minimo = db.Column(db.Integer, default=0, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    usos = db.relationship("RepuestoUsado", backref="repuesto", lazy=True)
    empresa = db.relationship("Empresa", backref="repuestos")

    @property
    def en_nivel_critico(self):
        return self.stock_actual <= self.stock_minimo

    def __repr__(self):
        return f"<Repuesto {self.nombre}>"


class RepuestoUsado(db.Model):
    """Repuesto consumido en una orden de trabajo. Al crearse, descuenta
    stock_actual del repuesto; al eliminarse, lo repone."""

    __tablename__ = "repuestos_usados"

    id = db.Column(db.Integer, primary_key=True)
    orden_trabajo_id = db.Column(db.Integer, db.ForeignKey("ordenes_trabajo.id"), nullable=False)
    repuesto_id = db.Column(db.Integer, db.ForeignKey("repuestos.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.Date, default=date.today, nullable=False)

    def __repr__(self):
        return f"<RepuestoUsado {self.cantidad} x {self.repuesto.nombre if self.repuesto else ''}>"


# ---------------------------------------------------------------------------
# Mensajes — chat interno acotado (Administrador/Jefe <-> Técnico)
# ---------------------------------------------------------------------------


class Mensaje(db.Model):
    """Nota dirigida de un usuario a otro (ej. Jefe -> Técnico o
    Técnico -> Jefe), con destinatario explícito — no es un tablón
    compartido. Puede asociarse a un cliente opcionalmente, con una
    prioridad (misma escala que las OT). Antes 'Recordatorio': ese nombre
    ya no describe bien que ahora tiene remitente y destinatario."""

    __tablename__ = "mensajes"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    remitente_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    destinatario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=True)
    titulo = db.Column(db.String(200), nullable=False)
    prioridad = db.Column(db.String(20), default="Media", nullable=False)  # ver PRIORIDADES_OT
    leido = db.Column(db.Boolean, default=False, nullable=False)
    resuelto = db.Column(db.Boolean, default=False, nullable=False)
    fecha_carga = db.Column(db.Date, default=date.today, nullable=False)

    cliente = db.relationship("Cliente", backref="mensajes")
    empresa = db.relationship("Empresa", backref="mensajes")
    remitente = db.relationship("Usuario", backref="mensajes_enviados", foreign_keys=[remitente_id])
    destinatario = db.relationship("Usuario", backref="mensajes_recibidos", foreign_keys=[destinatario_id])

    def __repr__(self):
        return f"<Mensaje {self.titulo}>"


# ---------------------------------------------------------------------------
# Notificaciones — avisos de eventos del sistema (y de mensajes nuevos)
# ---------------------------------------------------------------------------

TIPOS_NOTIFICACION = {
    "ensayo_nuevo": "Nuevo ensayo de curva de caudal",
    "visita_revision": "Visita enviada a revisión",
    "observacion_nueva": "Observación nueva",
    "equipo_nuevo": "Equipo nuevo",
    "formulario_cargado": "Formulario cargado",
    "mensaje_nuevo": "Mensaje nuevo",
    "ot_asignada": "Orden de trabajo asignada",
    "ensayo_validado": "Ensayo validado",
    "ensayo_rechazado": "Ensayo rechazado",
    "observacion_aprobada": "Observación aprobada",
    "cliente_nuevo": "Cliente nuevo registrado en campo",
}


class Notificacion(db.Model):
    """Aviso dirigido a un usuario puntual, generado por el sistema (un
    evento operativo) o por otro usuario (un Mensaje nuevo). Se agrupan en
    pantalla por (tipo, cliente) — ver notificaciones.listar."""

    __tablename__ = "notificaciones"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    destinatario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    remitente_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)  # None = sistema
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=True)
    tipo = db.Column(db.String(30), nullable=False)  # ver TIPOS_NOTIFICACION
    titulo = db.Column(db.String(250), nullable=False)
    enlace = db.Column(db.String(300), nullable=True)
    leido = db.Column(db.Boolean, default=False, nullable=False)
    fecha_carga = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    destinatario = db.relationship("Usuario", backref="notificaciones", foreign_keys=[destinatario_id])
    remitente = db.relationship("Usuario", foreign_keys=[remitente_id])
    cliente = db.relationship("Cliente")

    @property
    def descripcion_tipo(self):
        return TIPOS_NOTIFICACION.get(self.tipo, self.tipo)

    def __repr__(self):
        return f"<Notificacion {self.tipo} -> {self.destinatario_id}>"


# ---------------------------------------------------------------------------
# Empresas y usuarios (multiempresa) — Fase 1: login y roles.
# La Fase 2 agrega el aislamiento real de datos por empresa (empresa_id en
# Cliente/Repuesto/Recordatorio y permisos aplicados ruta por ruta).
# ---------------------------------------------------------------------------

ROLES = ["Super Admin", "Administrador", "Jefe", "Técnico", "Cliente"]

# Roles con permiso operativo "de gestión" equivalente (aprueban observaciones,
# asignan OT/repuestos, cierran visitas) — Jefe tiene todo lo mismo que
# Administrador salvo poder crear otros Administradores/Jefes.
ROLES_GESTION = ["Administrador", "Jefe"]


class Empresa(db.Model):
    """Una compañía de servicio técnico que usa el sistema. Cada Empresa
    tiene sus propios usuarios (Administrador, Técnicos). Más adelante
    (Fase 2) sus propios Clientes, Repuestos y Recordatorios quedan
    aislados del resto de las empresas."""

    __tablename__ = "empresas"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<Empresa {self.nombre}>"


class Usuario(UserMixin, db.Model):
    """Login simple por usuario/contraseña (sin email obligatorio).

    Según el rol:
    - Super Admin: sin empresa ni cliente asociado. Ve y administra todas
      las empresas (soporte remoto).
    - Administrador: pertenece a una Empresa. Crea/gestiona sus propios
      técnicos y clientes, clientes/instalaciones/contratos/equipos, tipos
      de formulario, y las órdenes de trabajo de su empresa.
    - Técnico: pertenece a una Empresa. Ve todos los clientes de su
      empresa, pero solo edita/crea dentro del cliente de su OT asignada
      (esa restricción se aplica en la Fase 2).
    - Cliente: ligado a un registro Cliente puntual (uno por Cliente). Ve
      solo lo de su propia instalación (pantallas de la Fase 4)."""

    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre_completo = db.Column(db.String(150))
    rol = db.Column(db.String(30), nullable=False)  # ver ROLES
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    empresa = db.relationship("Empresa", backref="usuarios")
    cliente = db.relationship("Cliente", backref=db.backref("usuario", uselist=False))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        # Sobreescribe el default de UserMixin: un usuario desactivado por
        # el administrador no puede iniciar sesión aunque tenga la
        # contraseña correcta.
        return self.activo

    def __repr__(self):
        return f"<Usuario {self.username} ({self.rol})>"
