# Render.com / Heroku start command for Aegis Quant AI backend.
#
# CRITICAL: The module path is "backend.main:app" (NOT "main:app").
# The FastAPI app lives at backend/main.py, so uvicorn must import it
# as "backend.main:app". Using "main:app" will fail with:
#   ModuleNotFoundError: No module named 'main'
#
# $PORT is injected by Render — do not hardcode it.
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
