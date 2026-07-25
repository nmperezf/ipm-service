"""
Carga datos de ejemplo para probar el sistema rápidamente.
Uso: python seed_demo.py
"""

import json
from datetime import date

from app import create_app, db
from app.models import (
    Cliente,
    Contrato,
    Empresa,
    Equipo,
    Instalacion,
    Observacion,
    OrdenTrabajo,
    Recordatorio,
    Repuesto,
    RepuestoUsado,
    ServicioContrato,
    TipoFormulario,
    Usuario,
    Visita,
)

app = create_app()

with app.app_context():
    if Cliente.query.first():
        print("Ya existen datos. No se cargó nada para evitar duplicar.")
    else:
        # Empresa demo + un usuario de cada rol (además del Super Admin ya
        # sembrado automáticamente). Todo lo demás cuelga de esta empresa.
        empresa_demo = Empresa(nombre="Andrés Wittenberger SA")
        db.session.add(empresa_demo)
        db.session.flush()

        admin_demo = Usuario(username="admin1", nombre_completo="Nicolás (Administrador)", rol="Administrador", empresa_id=empresa_demo.id)
        admin_demo.set_password("demo123")

        jefe_demo = Usuario(username="jefe1", nombre_completo="María (Jefa técnica)", rol="Jefe", empresa_id=empresa_demo.id)
        jefe_demo.set_password("demo123")

        tecnico_demo = Usuario(username="tecnico1", nombre_completo="Carlos Gómez (Técnico)", rol="Técnico", empresa_id=empresa_demo.id)
        tecnico_demo.set_password("demo123")

        db.session.add_all([admin_demo, jefe_demo, tecnico_demo])
        db.session.commit()

        cliente = Cliente(
            empresa_id=empresa_demo.id,
            nombre="Shopping Costa Azul",
            direccion="Av. Principal 1234",
            contacto="Juan Pérez",
            telefono="099123456",
            email="mantenimiento@costaazul.com",
        )
        db.session.add(cliente)
        db.session.flush()

        cliente_demo = Usuario(username="cliente1", nombre_completo="Contacto Shopping Costa Azul", rol="Cliente", cliente_id=cliente.id)
        cliente_demo.set_password("demo123")
        db.session.add(cliente_demo)
        db.session.commit()
        print("Empresa y usuarios demo cargados: admin/admin123 (Super Admin), admin1/demo123 (Administrador), jefe1/demo123 (Jefe), tecnico1/demo123 (Técnico), cliente1/demo123 (Cliente).")

        instalacion = Instalacion(
            cliente_id=cliente.id,
            nombre="Edificio Central",
            direccion="Av. Principal 1234, Torre A",
        )
        db.session.add(instalacion)
        db.session.flush()

        fecha_inicio = date(2026, 3, 1)
        contrato = Contrato(
            instalacion_id=instalacion.id,
            nombre="Contrato 2026",
            fecha_inicio=fecha_inicio,
            fecha_fin=Contrato.calcular_fecha_fin(fecha_inicio),
            estado="Activo",
        )
        db.session.add(contrato)
        db.session.flush()

        # Tres servicios de distinta frecuencia: se agruparán solos en las
        # fechas donde coincidan (mes 3, 6, 9 y 12 desde el inicio).
        servicios = [
            ServicioContrato(contrato_id=contrato.id, nombre="Inspección visual de sprinklers", frecuencia="mensual"),
            ServicioContrato(contrato_id=contrato.id, nombre="Prueba de señales ECAS", frecuencia="trimestral"),
            ServicioContrato(contrato_id=contrato.id, nombre="Curva de bombas", frecuencia="semestral"),
        ]
        db.session.add_all(servicios)
        db.session.commit()

        # Genera automáticamente todas las visitas del año, agrupando por fecha
        contrato.generar_visitas()

        print(f"Datos de ejemplo cargados. Se generaron {len(contrato.visitas)} visitas para el contrato.")

        # Observación de ejemplo, para ver el dashboard funcionando
        observacion = Observacion(
            instalacion_id=instalacion.id,
            clasificacion="Deficiencia crítica",
            descripcion="Extintor del hall principal sin carga vigente.",
            fecha_carga=date(2026, 6, 15),
        )
        db.session.add(observacion)
        db.session.commit()
        print("Observación de ejemplo cargada.")

        # Equipos de ejemplo: un manifold con dos ECA colgando, y un ECA suelto
        manifold = Equipo(instalacion_id=instalacion.id, tipo="Manifold", nombre="Manifold general PB", ubicacion="Planta baja, sala de bombas")
        db.session.add(manifold)
        db.session.flush()

        eca1 = Equipo(instalacion_id=instalacion.id, tipo="ECA", nombre="ECA Torre A", ubicacion="Torre A, subsuelo", manifold_id=manifold.id)
        eca2 = Equipo(instalacion_id=instalacion.id, tipo="ECA", nombre="ECA Torre B", ubicacion="Torre B, subsuelo", manifold_id=manifold.id)
        eca_suelto = Equipo(instalacion_id=instalacion.id, tipo="ECA", nombre="ECA depósito", ubicacion="Depósito ala este")
        db.session.add_all([eca1, eca2, eca_suelto])
        db.session.commit()
        print("Equipos de ejemplo cargados (1 manifold con 2 ECA, 1 ECA suelto).")

        # Repuestos de ejemplo (uno en nivel crítico a propósito, para ver el aviso)
        repuesto1 = Repuesto(empresa_id=empresa_demo.id, nombre="Rociador estándar 68°C", codigo="ROC-68", unidad="unidad", stock_actual=25, stock_minimo=10)
        repuesto2 = Repuesto(empresa_id=empresa_demo.id, nombre="Sello de válvula ECA", codigo="SEL-ECA", unidad="unidad", stock_actual=2, stock_minimo=5)
        db.session.add_all([repuesto1, repuesto2])
        db.session.commit()
        print("Repuestos de ejemplo cargados (1 en nivel crítico a propósito).")

        # OT correctiva de ejemplo, con un repuesto consumido
        ot_correctiva = OrdenTrabajo(
            instalacion_id=instalacion.id,
            tipo="Correctivo",
            prioridad="Alta",
            estado="Finalizada",
            tecnico_id=tecnico_demo.id,
            descripcion="Reemplazo de sello de válvula con pérdida en ECA Torre A.",
            fecha_apertura=date(2026, 6, 10),
            fecha_cierre=date(2026, 6, 10),
        )
        db.session.add(ot_correctiva)
        db.session.flush()
        ot_correctiva.asignar_numero()
        db.session.add(RepuestoUsado(orden_trabajo_id=ot_correctiva.id, repuesto_id=repuesto2.id, cantidad=1))
        repuesto2.stock_actual -= 1
        db.session.commit()
        print(f"OT correctiva de ejemplo cargada ({ot_correctiva.numero}), con 1 repuesto consumido.")

        # Recordatorio de ejemplo
        db.session.add(Recordatorio(
            empresa_id=empresa_demo.id,
            cliente_id=cliente.id,
            titulo="Coordinar con el cliente la renovación del contrato antes de marzo",
            prioridad="Urgente",
        ))
        db.session.commit()
        print("Recordatorio de ejemplo cargado.")

        # Checklist de BIE de ejemplo (creado como cualquier tipo de formulario
        # se crearía desde la pantalla "Formularios" — se puede editar ahí mismo)
        # Tipos de formulario base, a modo de ejemplo (antes eran globales;
        # ahora cada cliente tiene los suyos, se crean/editan desde
        # "Formularios" dentro de la ficha del cliente)
        tipos_base = [
            TipoFormulario(
                cliente_id=cliente.id,
                nombre="Inspección visual",
                descripcion="Chequeo visual general de equipos contra incendio",
                schema_json=json.dumps([
                    {"campo": "equipos_verificados", "tipo": "texto", "label": "Equipos verificados"},
                    {"campo": "anomalias", "tipo": "texto_largo", "label": "Anomalías detectadas"},
                    {"campo": "conforme", "tipo": "booleano", "label": "¿Conforme?"},
                ]),
            ),
            TipoFormulario(
                cliente_id=cliente.id,
                nombre="Curva hidráulica",
                descripcion="Prueba de curva de bombas contra incendio",
                schema_json=json.dumps([
                    {"campo": "presion_succion", "tipo": "numero", "label": "Presión de succión (PSI)"},
                    {"campo": "presion_descarga", "tipo": "numero", "label": "Presión de descarga (PSI)"},
                    {"campo": "caudal", "tipo": "numero", "label": "Caudal (GPM)"},
                    {"campo": "observaciones", "tipo": "texto_largo", "label": "Observaciones"},
                ]),
            ),
            TipoFormulario(
                cliente_id=cliente.id,
                nombre="Checklist de ECA",
                descripcion="Inspección de ECA: válvula, manómetros y estado de cañería",
                por_equipo=True,
                tipo_equipo_aplicable="ECA",
                schema_json=json.dumps([
                    {"campo": "valvula_abierta", "tipo": "booleano", "label": "¿Válvula abierta?"},
                    {"campo": "valvula_sellada", "tipo": "booleano", "label": "¿Válvula sellada (cadena/candado)?"},
                    {"campo": "manometro_1", "tipo": "numero", "label": "Presión manómetro 1 (PSI)"},
                    {"campo": "manometro_2", "tipo": "numero", "label": "Presión manómetro 2 (PSI)"},
                    {"campo": "manometros_funcionan", "tipo": "booleano", "label": "¿Manómetros funcionan correctamente?"},
                    {
                        "campo": "estado_caneria", "tipo": "multi_seleccion",
                        "label": "Estado de cañería (marcá todas las que apliquen)",
                        "opciones": ["Buen estado", "Corrosión superficial", "Corrosión avanzada", "Fuga visible", "Pintura descascarada", "Daño mecánico", "Soportería deficiente / floja", "Obstrucción visual"],
                    },
                    {"campo": "senalizacion_visible", "tipo": "booleano", "label": "¿Señalización/rotulado visible?"},
                    {"campo": "observaciones", "tipo": "texto_largo", "label": "Observaciones"},
                ]),
            ),
        ]
        db.session.add_all(tipos_base)
        db.session.commit()
        print("Tipos de formulario base cargados como ejemplo, ligados al cliente demo.")

        tipo_bie = TipoFormulario(
            cliente_id=cliente.id,
            nombre="Checklist de BIE",
            descripcion="Inspección de boca de incendio equipada",
            por_equipo=True,
            tipo_equipo_aplicable="BIE",
            schema_json=json.dumps([
                {"campo": "prueba_valvula", "tipo": "booleano", "label": "Prueba de válvula"},
                {"campo": "presion_estatica", "tipo": "numero", "label": "Presión estática (PSI)"},
                {"campo": "equipada", "tipo": "booleano", "label": "Equipada con manguera y puntero"},
                {"campo": "compatibles", "tipo": "booleano", "label": "Manguera y puntero compatibles"},
                {"campo": "llave_storz", "tipo": "booleano", "label": "Cuenta con llave Storz"},
                {
                    "campo": "estado_manguera", "tipo": "seleccion", "label": "Estado de la manguera",
                    "opciones": ["Buena", "Regular", "Mala"],
                },
                {"campo": "cantidad_mangueras", "tipo": "numero", "label": "Cantidad de mangueras"},
                {"campo": "id_manguera", "tipo": "texto", "label": "N° de identificación de la manguera"},
                {"campo": "ultima_prueba_manguera", "tipo": "fecha", "label": "Última fecha de prueba de la manguera"},
            ]),
        )
        db.session.add(tipo_bie)
        db.session.commit()

        for i in range(1, 6):
            db.session.add(Equipo(
                instalacion_id=instalacion.id, tipo="BIE",
                nombre=f"BIE-{i:03d}", ubicacion=f"Piso {i}",
            ))
        db.session.commit()
        print("Checklist de BIE y 5 BIE de ejemplo cargados (una instalación real puede tener cientos).")
