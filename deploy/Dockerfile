FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd -m -u 1000 user
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY --chown=user backend/ backend/
COPY --chown=user deploy/start.sh start.sh
RUN chmod +x start.sh && mkdir -p backend/data && chown user backend/data

USER user
EXPOSE 8000
CMD ["./start.sh"]
