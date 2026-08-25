import os

from app import create_app, verificar_schema_al_dia

app = create_app()

if __name__ == "__main__":
    # Mismo chequeo que corre verificar_schema.py antes de gunicorn en
    # producción (ver Procfile) -- no se pone a nivel de módulo porque
    # "flask db migrate/upgrade" también importa este archivo (por
    # FLASK_APP=run.py) y ahí el schema todavía no está al día a propósito.
    with app.app_context():
        verificar_schema_al_dia()
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", host="0.0.0.0", port=5000)
