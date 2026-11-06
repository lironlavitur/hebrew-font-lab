FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY requirements.txt requirements-hosting.txt ./
RUN pip install --no-cache-dir -r requirements-hosting.txt && useradd --create-home appuser
COPY core.py hosted.py ./
COPY web/index.html web/app.js web/style.css ./web/
USER appuser
EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn --workers 1 --threads 2 --timeout 180 --bind 0.0.0.0:${PORT:-10000} hosted:app"]
