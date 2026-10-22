# Microsite OCR Service: tiket → DMS-Cardsys → OCR API.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY microsite_ocr/ microsite_ocr/

RUN useradd --system --uid 10001 --no-create-home app
USER app

ENV HOST=0.0.0.0 \
    PORT=8090

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import json,os,urllib.request; r=urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=8); exit(0 if json.load(r)['status']=='ok' else 1)"

CMD ["python", "-m", "microsite_ocr.service"]
