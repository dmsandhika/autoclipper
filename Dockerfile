FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY autoclipper ./autoclipper

RUN useradd -m app && mkdir -p /data /models && chown app /data /models
USER app

ENV AUTOCLIPPER_DATA_DIR=/data \
    AUTOCLIPPER_MODEL_DIR=/models \
    HF_HOME=/models \
    AUTOCLIPPER_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

VOLUME ["/data", "/models"]
EXPOSE 8765
CMD ["python", "-m", "autoclipper.web", "--no-browser"]
