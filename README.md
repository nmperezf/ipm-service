# IPM Service

CMMS especializado en gestión técnica de mantenimiento e inspecciones de
sistemas de protección contra incendio.

## Filosofía del sistema

```
Cliente ──▶ Instalación ──▶ Contrato (1 año) ──▶ Servicio contratado (con su frecuencia)
                  │                 └──▶ Visita (agrupa servicios que coinciden en fecha)
                  │                         └──▶ Item de visita (por servicio, cumplido/pendiente)
                  │                                 ├──▶ Formulario (tipo dinámico)
                  │                                 ├──▶ Fotos (evidencia)
                  │                                 └──▶ Observaciones (deficiencias/desactivaciones)
                  └──▶ Observaciones cargadas a mano (migración de historial)
```

- Un **contrato dura 1 año**. Cada **servicio contratado** tiene su propia
  frecuencia y genera automáticamente sus fechas dentro del año, contando
  **desde su propio mes de inicio inclusive** (una frecuencia anual que
  arranca junto con el contrato genera una sola fecha, la de inicio).
- Servicios de distinta frecuencia que coinciden en fecha se **agrupan en
  una única visita**; cada servicio se marca cumplido/pendiente por separado.
- Cada visita se puede **editar o eliminar**. Cada servicio admite
  **formularios dinámicos**, **fotos** y **observaciones**.

## Pantallas principales

- **Inicio (dashboard, para Administrador/Jefe/Técnico):** tarjetas de
  deficiencias/comentarios aprobados por clasificación, visitas vencidas,
  visitas en revisión, OT pendientes, repuestos en nivel crítico, % de
  cumplimiento del mes, agenda de la semana, buscador de cliente y
  recordatorios (solo Administrador/Jefe).
- **Clientes → ficha del cliente:** tarjetas de deficiencias/comentarios
  scoped a ese cliente, hoja de ruta (todas sus visitas por mes), y acceso
  a "Formularios" (tipos de checklist propios de ese cliente).
- **Calendario:** grilla mensual, solo clientes con servicios contratados.
- **Órdenes de trabajo:** cola de trabajo (preventivo/correctivo/predictivo/
  visita técnica). El Técnico ve solo las suyas; Administrador/Jefe ven
  todas las de su empresa.
- **Inventario:** repuestos con stock actual/mínimo y aviso de nivel crítico.
- **Portal de cliente:** pantalla propia para el rol Cliente — ver la
  sección "Login, roles y multiempresa" más abajo.

## Observaciones (deficiencias / desactivaciones / comentarios)

Cuatro clasificaciones: **Deficiencia crítica**, **Deficiencia no crítica**,
**Desactivación** y **Comentario** (para lo que no encaja en las otras tres).
Se cargan por instalación — a mano (para migrar tu historial actual de
clientes) o ligadas a un servicio/equipo puntual dentro de una visita. Al
marcarse **resueltas, no se borran**: salen del conteo pero quedan
visibles en el histórico técnico, con fecha de carga y fecha de
resolución. Además tienen un **estado de revisión** (Pendiente/Aprobada)
como control de calidad — ver la sección "Login, roles y multiempresa"
para el detalle completo del circuito.

Independiente de ese control de calidad, cada observación tiene una
**visibilidad**: **Cliente** (default, sigue el circuito de siempre) o
**Interna** — para notas de manejo interno (ej. "avisar a compras",
"cliente complicado con el pago") que nunca deben llegar al cliente, ni
aunque se aprueben. El staff (Administrador/Jefe/Técnico) siempre ve
todo, con una etiqueta "Interna" para distinguirlas; se excluyen del
portal del cliente y del PDF de devolución.

## Órdenes de trabajo en PDF

Cada OT se puede descargar en PDF (botón "Descargar PDF" en su detalle):
datos generales, el checklist de servicios si es preventiva, los repuestos
usados, y espacio para firma de técnico y cliente. Se genera con
`reportlab` (ya incluido en `requirements.txt`), sin dependencias del
sistema operativo.

## Documentos sueltos (informes de alineación, trabajos especiales, etc.)

Para un informe puntual que ya tenés armado (alineación láser, trabajo
especial, certificado, u otro archivo que no corresponde a una visita con
checklist) — desde el menú "Más" de la ficha de instalación, "Cargar
documento": título, archivo (PDF/Word/Excel/imagen), fecha real del
documento y, opcionalmente, a qué equipo corresponde. No pasa por OT,
firma digital ni portal de cliente — es un adjunto liviano que aparece
como una fila más en el histórico técnico, con su propio link de
descarga.

## Servicios tipo (catálogo por empresa)

Desde "Servicios tipo" en la barra de navegación (Administrador/Jefe), se
arma un catálogo reutilizable de servicios con su formulario base — mismo
constructor de campos que los tipos de formulario. Al agregar un servicio
nuevo a un contrato, ya no se escribe el nombre a mano: se elige de este
catálogo. Al elegirlo, se le "importa" el formulario base al cliente de ese
contrato — si el cliente ya tenía uno con ese nombre (lo había importado
antes, o lo cargó a mano), se reutiliza tal cual en vez de duplicar. De ahí
en más esa copia es independiente: el cliente la puede editar (agregar o
sacar campos) sin que le afecte a otros clientes ni al catálogo — y editar
el catálogo más adelante tampoco actualiza las copias ya importadas,
quedan congeladas tal como estaban en el momento de importarlas.

## Constructor de tipos de formulario (sin tocar código)

Desde "Formularios" en la barra de navegación se pueden crear checklists
nuevos: nombre, campos (texto, texto largo, número, fecha, sí/no, selección
única, checklist de opciones múltiples), y si el checklist se completa por
equipo (ej. una vez por cada BIE o ECA) en vez de una sola vez por servicio.
El checklist de BIE (Boca de Incendio Equipada) viene cargado como ejemplo:
prueba de válvula, presión estática, manguera y puntero, compatibilidad,
llave Storz, estado y cantidad de mangueras, identificación y última fecha
de prueba.

## Carga masiva (instalaciones con muchos equipos)

Para checklists "por equipo" con decenas o cientos de unidades (típico en
BIE), además de cargar equipo por equipo hay una vista de **carga masiva**:
una sola grilla con una fila por equipo y todas las columnas del checklist
editables ahí mismo, un solo botón para guardar todo. Las filas que se
dejan en blanco no se guardan; si un equipo ya tenía datos de esa visita,
se actualizan en vez de duplicarse. Desde la misma pantalla se descarga el
**reporte en PDF** con el detalle de cada equipo, listo para mandarle al
cliente.

## Órdenes de trabajo: tipos y navegación desde el calendario

Cada OT tiene un tipo: **Preventivo** (reservado para las que genera solo
un contrato, ligadas a una visita), **Correctivo**, **Predictivo** o
**Visita técnica** (estos tres últimos elegibles al cargar una OT a mano).
Desde el calendario, la pastilla de cada visita lleva directo a su OT (y
desde la OT se accede al detalle de la visita/servicio).

## Ficha de equipo (histórico y trazabilidad)

Cada equipo (ECA, BIE, Bomba) tiene su propia página con el historial de
cada campo de su checklist a través del tiempo — tabla para texto/fecha/
selección, gráfico de línea simple (SVG, sin dependencias) para campos
numéricos como presión. También muestra las deficiencias abiertas y
resueltas de ese equipo puntual. Se accede desde la carga masiva o desde
la lista de "elegir equipo".

## Formularios agrupados por sistema

Al completar formularios dentro de una visita, los checklists por equipo
se agrupan en tres categorías de navegación (no son tablas nuevas, es
solo cómo se organizan los tipos de equipo ya existentes): **Sala de
bombas** (Bomba), **Estaciones de control y alarma** (ECA y Manifold), y
**Bocas de incendio** (BIE). El acceso por defecto de cada categoría es la
carga masiva; cargar equipo por equipo sigue disponible como alternativa.

## Migraciones de base de datos (Alembic / Flask-Migrate)

El esquema ya no lo crea `db.create_all()` (ni los parches manuales que
vivían en `app/__init__.py`) — lo maneja Alembic vía Flask-Migrate, con
el historial de cambios versionado en `migrations/`.

**Flujo normal, cada vez que se cambia un modelo en `app/models.py`:**
```bash
flask --app run.py db migrate -m "descripción corta del cambio"
```
Revisá el archivo generado en `migrations/versions/` (Alembic no siempre
detecta bien renombres o cambios de tipo), commiteálo junto con el cambio
de modelo, y aplicalo con:
```bash
flask --app run.py db upgrade
```

**Probar contra Postgres antes de pushear** (no solo contra el SQLite
local): SQLite es permisivo con cosas que Postgres rechaza en seco — por
ejemplo `BOOLEAN DEFAULT 0` en vez de `DEFAULT false`, el bug exacto que
dejó producción con la migración sin aplicar el 14/08/2026. Con Docker:
```bash
docker compose up -d db_test
DATABASE_URL=postgresql://ipm:ipm@localhost:5433/ipm_test flask --app run.py db upgrade
```
Si el `upgrade` pasa ahí, va a pasar en Railway. `docker compose down -v`
para tirar la base descartable después.

**Despliegue (Railway):** el `Procfile` corre `python release.py` como
fase de `release`, antes de levantar el proceso `web`. Ese script no es
solo `flask db upgrade`: primero revisa si la base ya tiene tablas pero
todavía no tiene el historial de Alembic (`alembic_version`) — el caso de
la base de Railway ya desplegada — y si es así, la marca como "ya al día"
con la migración inicial sin tocar ni una tabla, antes de aplicar el
upgrade. En cualquier otro caso (base nueva, o una que ya tiene historial
de Alembic) simplemente aplica las migraciones pendientes.

El 14/08/2026 esa fase de `release` falló en silencio en producción (no
se pudo confirmar todavía por qué — Railway no bloqueó el deploy del
proceso `web` igual) y la app quedó sirviendo tráfico con un schema
desactualizado durante días, hasta que una query nueva pisó una columna
que no existía y empezó a tirar 500. Por eso el `Procfile` ahora tiene un
paso extra antes de `gunicorn`:
```
web: python verificar_schema.py && gunicorn run:app --bind 0.0.0.0:$PORT
```
`verificar_schema.py` compara la revisión de Alembic aplicada contra el
head de `migrations/`; si no coinciden, termina con código de salida
distinto de 0 y el `&&` corta la cadena — el deploy queda visiblemente
caído en vez de servir tráfico en silencio con el schema viejo. El mismo
chequeo corre en local al hacer `python run.py`.

**Variables obligatorias de producción:**

- `SECRET_KEY`: clave aleatoria larga y privada; la aplicación no arranca
  si falta.
- `UPLOAD_FOLDER`: directorio persistente fuera de `app/static`, por ejemplo
  un volumen montado en `/data/uploads`.
- `INITIAL_ADMIN_PASSWORD`: contraseña temporal para crear el primer Super
  Admin en una base sin usuarios. Se usa solo durante el primer arranque y
  no tiene un valor por defecto.
- `INITIAL_ADMIN_USERNAME`: opcional; por defecto es `admin`.

Después del primer arranque conviene quitar `INITIAL_ADMIN_PASSWORD` del
entorno y cambiar la contraseña desde **Mi cuenta**. Los archivos que ya
existían en `app/static/uploads` deben copiarse manualmente al directorio
persistente configurado en `UPLOAD_FOLDER`.

## Tablas ordenables y filtrables

Todas las tablas de listado de la app (clientes, contratos, visitas,
histórico, órdenes de trabajo, inventario, etc.) se pueden ordenar
haciendo clic en cualquier encabezado de columna (alterna ascendente/
descendente, entiende fechas dd/mm/yyyy, números y texto en español), y
filtrar con la fila de casillas que aparece debajo de cada encabezado
(cada casilla filtra su propia columna, en simultáneo con las demás).
Es un único script (`app/static/js/tablas.js`) que se aplica solo con
la clase `data-table` en el `<table>` — no requiere backend ni recarga
de página.

## Formato para tablet y celular

- **Todas las tablas** están envueltas en un contenedor de scroll horizontal
  controlado (evita el bug de encabezado en blanco al desplazarse en
  pantallas chicas).
- **Columna congelada** (`class="tabla-col-fija"`) en las listas más largas
  (Órdenes de trabajo, Clientes, Historial de visitas de una instalación):
  la primera columna queda siempre visible al hacer scroll horizontal.
- **Tarjetas apiladas en celular** (`class="tabla-tarjetas"`, con
  `data-label="..."` en cada `<td>`): por debajo de 576px, una tabla así
  marcada deja de tener scroll horizontal — cada fila se ve como una
  tarjeta con "etiqueta: valor". Aplicado por ahora a la lista de Órdenes
  de trabajo como caso de referencia; se puede sumar a otras tablas
  agregando esas dos cosas (la clase + el `data-label` en cada celda).
- **Prevención de doble-toque**: cualquier formulario deshabilita su botón
  de guardar (con spinner) al enviarse, para evitar cargas duplicadas con
  mala señal. No afecta a los botones con `confirm()` (como "Eliminar") si
  se cancela el diálogo.
- **Botón de acción fijo abajo en celular** (`class="barra-accion-fija"`,
  con un `<div class="barra-accion-fija-relleno d-sm-none">` antes para
  no tapar contenido): aplicado en el cierre de visita y los dos
  constructores de formulario (tipos de formulario y servicios tipo).
- **Barra de navegación inferior en celular**, con accesos distintos según
  el rol — visible solo por debajo de 576px, la navegación de escritorio
  (arriba) sigue igual en pantallas más grandes.
- **Íconos consistentes** (Bootstrap Icons) en vez de emoji sueltos.

## Arquitectura

- **Backend:** Python + Flask + SQLAlchemy
- **Base de datos:** SQLite en desarrollo (migrable a PostgreSQL cambiando
  la variable de entorno `DATABASE_URL`)
- **Frontend:** HTML + Bootstrap 5 (server-rendered con Jinja2)
- **Patrón:** MVC con blueprints desacoplados por módulo

```
app/
  models.py               -> Cliente, Instalacion, Contrato, ServicioContrato,
                              Visita, ItemVisita, TipoFormulario, Formulario,
                              Foto, Documento, Observacion, Equipo,
                              OrdenTrabajo, Repuesto, RepuestoUsado, Recordatorio
  utils.py                 -> actualización compartida de estados vencidos
  routes/
    dashboard.py            -> pantalla principal
    clientes.py              -> CRUD + hoja de ruta + deficiencias por cliente
    instalaciones.py
    equipos.py                -> ECA / manifolds / bombas por instalación
    contratos.py                -> motor de planificación (genera visitas + OT)
    visitas.py                   -> editar/eliminar, marcar items cumplido/pendiente
    formularios.py                 -> formularios dinámicos por servicio/equipo
    fotos.py                        -> evidencia fotográfica
    documentos.py                    -> documentos sueltos (informes puntuales)
    observaciones.py                 -> deficiencias/desactivaciones
    historial.py                      -> histórico técnico por instalación + export CSV
    planificacion.py                   -> calendario mensual
    ordenes_trabajo.py                  -> cola de OT preventivas y correctivas
    inventario.py                        -> repuestos y niveles críticos
    recordatorios.py                      -> notas rápidas del dashboard
  templates/
  static/uploads/           -> fotos subidas (no versionar en git)
run.py
seed_demo.py                -> carga cliente/contrato/OT/repuestos de ejemplo
```

## Login, roles y multiempresa (Fases 1 a 4, completas)

Sistema de usuario/contraseña simple (sin email obligatorio), con 5 roles,
y aislamiento real de datos por empresa:

- **Super Admin**: crea empresas y su primer usuario Administrador
  ("Empresas" en la navbar). Ve los datos de cualquier empresa, y tiene
  acceso a "Usuarios" de todas las empresas (para resetear una contraseña
  ante un problema puntual). No ve el dashboard operativo — su "Inicio"
  redirige directo a "Empresas".
- **Administrador**: puede haber **varios por empresa** — cualquier
  Administrador puede crear a otro. Gestiona los usuarios de su empresa
  en "Usuarios" (contraseña puesta a mano, reset manual — sin
  recuperación por mail todavía). Crea/edita Clientes, Instalaciones,
  Contratos, Equipos, tipos de formulario. Asigna técnico y repuestos a
  cada OT, aprueba observaciones, cierra visitas.
- **Jefe**: mismo permiso operativo que Administrador en todo (aprueba
  observaciones, asigna OT/repuestos, cierra visitas, etc.) — la única
  diferencia es que **no puede crear Administradores ni otros Jefes**,
  solo Técnicos y Clientes.
- **Técnico**: ve **solo las OT que tiene asignadas**. Puede **consultar**
  (solo lectura) instalaciones, históricos, contratos, equipos, visitas,
  formularios, fotos y tipos de formulario de cualquier cliente de su
  empresa, para buscar información en campo aunque no sea suyo. Pero solo
  puede **crear, editar o eliminar** dentro del/los cliente(s) donde
  tiene una OT asignada. El calendario le muestra las visitas de todos
  los clientes del mes, sin el link (Administrador/Jefe sí lo tienen).
- **Cliente**: un usuario por Cliente, con su propio **portal** de solo
  lectura (ver más abajo).

### Circuito de una visita: Abierta → En revisión → Cerrada

El técnico completa checklists, fotos y observaciones normalmente
mientras la visita está **Abierta**. Cuando termina, la manda a
**"Enviar a revisión"** — esto funciona aunque haya observaciones sin
aprobar (es justamente lo que dispara que el Jefe las mire). A partir de
ahí la visita queda **congelada para el técnico**: no puede tocar nada
más. Si el Jefe/Administrador encuentra algo para corregir, lo edita él
mismo directamente (lo discute con el técnico aparte, no hay botón de
devolución).

Solo Administrador/Jefe puede **"Cerrar visita"** — bloqueado si quedan
observaciones sin aprobar. Ahí también se captura la **firma digital del
cliente** (canvas táctil, funciona con el dedo en tablet/celular), que
queda embebida en el PDF de devolución. Recién con la visita **Cerrada**
el cliente puede verla en su portal.

### Observaciones: control de calidad antes de mostrarlas al cliente

Cada observación que carga un técnico queda **Pendiente de revisión**.
Mientras esté así, el técnico la puede editar. El Administrador/Jefe la
aprueba tal cual, la edita y aprueba, o la elimina — una vez **Aprobada**,
ya nadie la puede editar (si hace falta corregirla, se borra y se carga
de nuevo). Solo lo Aprobado llega al portal del cliente.

### Dos PDF distintos, para momentos distintos

- **PDF de la OT** (botón en el detalle de la orden de trabajo): para
  imprimir/entregar en el momento, sin depender de ningún cierre. Tiene
  una columna "Completado" con casilleros ☐Sí/☐No por servicio, y espacio
  para la firma del técnico únicamente.
- **PDF de devolución** (botón en la visita, solo cuando está Cerrada):
  resumen ejecutivo por área + deficiencias aprobadas de esa visita +
  notas de cierre + firma del técnico y del cliente (embebida).

### Portal de cliente

Con "Inicio" y "Histórico técnico" en la navbar (visibles solo para el
rol Cliente). Muestra:
- Las mismas 4 tarjetas de deficiencias/comentarios, pero contando **solo
  lo Aprobado** por el Jefe/Administrador.
- Próximas visitas: fecha, servicios de cada una, y la "Nota para el
  cliente" que haya dejado el Administrador/Jefe (con fecha de escritura,
  para que quede registro de cuándo se avisó).
- Histórico técnico: solo observaciones **Aprobadas** y solo visitas
  **Cerradas** — nada que todavía esté en revisión o pendiente de
  aprobación.

Cada Cliente pertenece a una Empresa; el Inventario de repuestos y los
Recordatorios pertenecen directo a la Empresa; los tipos de formulario
pertenecen a un Cliente puntual (cada instalación es distinta — se cargan
desde "Formularios" dentro de la ficha del cliente, ya no hay una lista
global).

**Usuario por defecto** (se crea solo la primera vez que arranca la app, si no hay ningún usuario todavía):
```
usuario: admin
contraseña: admin123
```
Cambiala apenas entres. Si corrés `seed_demo.py`, además se cargan una
empresa de ejemplo y un usuario de cada rol (`jefe`, `tecnico1`,
`cliente1`, todos con contraseña `demo123`).

## Instalación

**Windows (CMD):**
```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
flask --app run.py db upgrade
python seed_demo.py
python run.py
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
flask --app run.py db upgrade
python seed_demo.py
python run.py
```

`flask db upgrade` aplica las migraciones y crea el esquema (reemplaza al
viejo `db.create_all()` automático). Hace falta correrlo una sola vez por
base de datos nueva, y de nuevo cada vez que haya una migración nueva.

Abrí http://localhost:5000

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Corren contra un SQLite temporal propio (esquema creado directo desde los
modelos, sin tocar la base real ni las migraciones) — no hace falta nada
más levantado. Cubre la lógica de negocio más sensible a romperse
silenciosamente: fechas de ocurrencia de un servicio contratado, cambios
de estado por vencimiento, validación NFPA 25, permisos por rol, y las
rutas de login/errores/paginación.

> En macOS, si el puerto 5000 aparece ocupado por AirPlay Receiver, cambiá
> el puerto en `run.py` (`port=5001`) o desactivá AirPlay Receiver en
> Preferencias del Sistema → General → AirDrop y Handoff.

## Qué falta (a propósito, para no romper la base actual)

- Autenticación y roles (técnico / supervisor / administrador)
- Firmas digitales, informes/PDF automáticos, notificaciones, app móvil, QR
- Exportación a PDF del histórico (por ahora solo CSV, sin dependencias extra)

La arquitectura actual (blueprints desacoplados, servicios basados en
esquema, contratos independientes por instalación) está pensada para
incorporar todo esto sin rehacer lo existente.
