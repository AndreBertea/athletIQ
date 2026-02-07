# Dockerfile pour backend FastAPI - optimisé pour Render.com
FROM python:3.12-slim

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Créer utilisateur non-root
RUN adduser --disabled-password --gecos '' appuser

# Répertoire de travail
WORKDIR /app

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY . .

# Créer les répertoires nécessaires
RUN mkdir -p logs

# Changer les permissions
RUN chown -R appuser:appuser /app
USER appuser

# Port d'exposition
EXPOSE 8000

# Nombre de workers (gunicorn lit aussi WEB_CONCURRENCY automatiquement)
ENV WEB_CONCURRENCY=4

# Commande de démarrage : migrations Alembic puis gunicorn avec uvicorn workers
CMD ["sh", "-c", "alembic upgrade head && gunicorn app.main:app --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY} --worker-class uvicorn.workers.UvicornWorker --timeout 120 --graceful-timeout 30 --access-logfile -"]