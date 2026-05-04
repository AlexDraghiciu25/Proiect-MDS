FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# Forțăm Playwright să instaleze browserele într-o locație fixă și accesibilă
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/bin/playwright-browsers

WORKDIR /app

# 1. Instalăm dependințele de sistem (am adăugat curl pentru siguranță)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 2. INSTALARE PLAYWRIGHT ȘI BROWSERE (Pune-le exact aici, după pip install)
# Instalăm dependințele de sistem necesare pentru a rula Chromium în mod headless
RUN playwright install-deps chromium
# Descărcăm executabilul Chromium
RUN playwright install chromium

COPY . /app/

COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]