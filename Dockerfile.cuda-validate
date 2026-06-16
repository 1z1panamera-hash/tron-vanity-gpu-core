ARG CUDA_BASE_IMAGE=nvidia/cuda:12.8.1-devel-ubuntu22.04
FROM ${CUDA_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV ALLOW_RUNTIME_NVCC=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY src /app/src
COPY tests/phase0_test_vectors.json /app/tests/phase0_test_vectors.json

RUN mkdir -p /app/build

CMD ["python3", "-u", "/app/app.py"]
