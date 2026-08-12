"""
Se corre en la fase "release" de cada deploy (ver Procfile), antes de
levantar el proceso web. Aplica las migraciones pendientes.

La primera vez que corre sobre la base de Railway ya desplegada (creada
con el viejo db.create_all() + los parches manuales que vivían en
app/__init__.py -- _migrar_columnas_faltantes/_corregir_servicio_
contrato_id_nullable, ya retirados de ahí), marca esa base como si ya
tuviera aplicada la migración "Esquema inicial" -- la que representa
exactamente ese mismo esquema ya parchado, sin índices -- y NO el último
head. Así, el upgrade() de abajo todavía tiene que recorrer (y aplicar de
verdad) cualquier migración posterior a esa, como la de índices. Si se
marcara directo al head, esas migraciones posteriores quedarían marcadas
como aplicadas sin haberse ejecutado nunca.
En cualquier otro caso (base nueva, o base que ya tiene historial de
Alembic) es un upgrade normal.
"""

from flask_migrate import stamp, upgrade
from sqlalchemy import inspect

from app import create_app, db

ESQUEMA_INICIAL = "e6b4f82e9468"

app = create_app()

with app.app_context():
    tablas = inspect(db.engine).get_table_names()
    if "alembic_version" not in tablas and "usuarios" in tablas:
        print("Base existente sin historial de Alembic detectada — marcando como al día con el esquema inicial (sin tocar tablas), antes de aplicar el resto de las migraciones.")
        stamp(revision=ESQUEMA_INICIAL)
    upgrade()
