"""Se corre como paso previo a levantar gunicorn (ver Procfile). Si el
schema de la base no está al día con las migraciones de migrations/, termina
con código de salida != 0 -- el "&&" del Procfile corta la cadena ahí y
gunicorn nunca arranca. Preferible un deploy visiblemente caído en Railway a
que la app siga sirviendo tráfico con un schema desactualizado en silencio
(lo que pasó el 14/08/2026 con la migración de "visibilidad")."""

import sys

from app import create_app, verificar_schema_al_dia

app = create_app()

with app.app_context():
    try:
        verificar_schema_al_dia()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

print("Schema al día, arrancando el proceso web.")
