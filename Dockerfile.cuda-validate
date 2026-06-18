ARG CUDA_BASE_IMAGE=nvidia/cuda:12.8.1-devel-ubuntu22.04
FROM ${CUDA_BASE_IMAGE}

ARG CUDA_ARCH=sm_120
ARG STEP_SIZE=4096

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV ALLOW_RUNTIME_NVCC=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        age \
        ca-certificates \
        git \
        g++ \
        make \
        python3 \
        python3-pip \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY src /app/src
COPY patches /app/patches
COPY scripts/build_vanitysearch_tron_worker.sh /app/scripts/build_vanitysearch_tron_worker.sh
COPY scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh /app/scripts/runpod_verify_vanitysearch_tron_gpu_address_layer.sh
COPY tests/phase0_test_vectors.json /app/tests/phase0_test_vectors.json

RUN mkdir -p /app/build
RUN ALLOW_BUILD_VANITYSEARCH_TRON_WORKER=1 \
    CUDA_ARCH="${CUDA_ARCH}" \
    STEP_SIZE="${STEP_SIZE}" \
    INSTALL_PATH=/app/build/vanitysearch_tron_worker \
    /app/scripts/build_vanitysearch_tron_worker.sh

CMD ["python3", "-u", "/app/app.py"]
