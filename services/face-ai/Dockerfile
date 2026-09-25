# ============================================================
# face-ai service Docker image (Jetson Orin Nano + JetPack 6.2.2)
#
# NOTE: For DeepStream GPU work the container must use the NVIDIA
# container runtime and a DeepStream base image (later phase). This
# Dockerfile is a structural placeholder for the Python service.
# ============================================================
FROM nvcr.io/nvidia/deepstream:6.4-samples AS deepstream_base
# Placeholder base - a JetPack DeepStream image pins JetPack 6.2.2.

FROM deepstream_base

ARG POSTGRES_HOST=localhost
ENV POSTGRES_HOST=${POSTGRES_HOST}

WORKDIR /app

# Copy Python service
COPY services/face-ai /app/services/face-ai
COPY scripts /app/scripts
COPY configs /app/configs
COPY database /app/database
COPY models /app/models

# Install dependencies
RUN pip install --no-cache-dir -r /app/services/face-ai/requirements.txt \
    && pip install --no-cache-dir psycopg2-binary onnxruntime-gpu PyYAML

ENV PYTHONPATH="/app/services/face-ai:${PYTHONPATH}"

ENTRYPOINT ["python", "-m", "app.main", "--import-flag"]
