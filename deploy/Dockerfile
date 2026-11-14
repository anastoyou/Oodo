FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    fonts-dejavu-core \
    git \
    libjpeg62-turbo-dev \
    libldap2-dev \
    libmagic1 \
    libpq-dev \
    libsasl2-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    postgresql-client \
    wkhtmltopdf \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY odoo/requirements.txt /tmp/odoo-requirements.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python3 -m pip install --no-cache-dir -r /tmp/odoo-requirements.txt \
    && rm -f /tmp/odoo-requirements.txt

COPY deploy/entrypoint.sh /usr/local/bin/odoo-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/odoo-entrypoint.sh \
    && chmod +x /usr/local/bin/odoo-entrypoint.sh

RUN useradd --create-home --home-dir /opt/app --shell /bin/bash odoo \
    && mkdir -p /opt/app/data /opt/app/backups \
    && chown -R odoo:odoo /opt/app

WORKDIR /opt/app
USER odoo

EXPOSE 8069 8072
ENTRYPOINT ["/usr/local/bin/odoo-entrypoint.sh"]

