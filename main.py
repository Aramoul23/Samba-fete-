"""Samba Fête — Legacy entry point (all routes now in blueprints).

    Prefer: python run.py  (or gunicorn run:app)
"""
from app import create_app  # noqa: F401

app = create_app()

if __name__ == "__main__":
    import os
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
    )
