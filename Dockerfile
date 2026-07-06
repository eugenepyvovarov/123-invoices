# Multi-stage build for Django invoices app with baked static assets
FROM python:3.13-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apk add --no-cache \
    build-base \
    libffi-dev \
    cairo-dev \
    pango-dev \
    gdk-pixbuf-dev \
    libjpeg-turbo-dev \
    zlib-dev \
    freetype-dev \
    fontconfig \
    ttf-dejavu \
    bash \
    curl

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DEBUG=0 \
    SECRET_KEY=dummy \
    DATABASE_URL=sqlite:////tmp/db.sqlite3 \
    DB_PATH=/tmp/db.sqlite3

RUN python manage.py collectstatic --noinput

FROM builder AS test

RUN pip install --no-cache-dir coverage

ENV DEBUG=1 \
    SECRET_KEY=opencode-ci-secret \
    DATABASE_URL=sqlite:////tmp/db.sqlite3 \
    DB_PATH=/tmp/db.sqlite3 \
    ALLOWED_HOSTS=127.0.0.1,localhost

FROM python:3.13-alpine AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INVOICES_CONTAINERIZED=1

WORKDIR /app

RUN apk add --no-cache \
    libffi \
    cairo \
    pango \
    gdk-pixbuf \
    libjpeg-turbo \
    zlib \
    freetype \
    fontconfig \
    ttf-dejavu \
    su-exec \
    bash \
    curl

RUN addgroup -S app && adduser -S app -G app \
    && install -d -o app -g app /app /app/db /app/media

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder --chown=app:app /app /app

EXPOSE 8000 8765

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "app.wsgi:application", "--bind", "0.0.0.0:8000"]
