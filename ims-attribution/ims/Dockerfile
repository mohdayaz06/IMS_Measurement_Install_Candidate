FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && useradd -u 10001 -m ims \
    && mkdir -p /data \
    && chown -R ims:ims /data

COPY --chown=ims:ims ims/ ./ims/
COPY --chown=ims:ims web/ ./web/
COPY --chown=ims:ims integrations/ ./integrations/

USER ims

ENV IMS_DB=/data/ims.sqlite3

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "120", "ims.app:application_factory()"]
