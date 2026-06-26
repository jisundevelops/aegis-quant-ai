# Render.com / Heroku start command for Aegis Quant AI backend.
#
# CRITICAL: The module path is "backend.main:app" (NOT "main:app").
# The FastAPI app lives at backend/main.py, so uvicorn must import it
# as "backend.main:app". Using "main:app" will fail with:
#   ModuleNotFoundError: No module named 'main'
#
# --timeout-keep-alive 30: keeps idle connections alive for 30s
#   (prevents Render from killing the service on slow requests)
#
# $PORT is injected by Render — do not hardcode it.
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT --timeout-keep-alive 30
