FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        docker.io \
        util-linux \
        e2fsprogs \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir docker

WORKDIR /opt/edge_node
COPY . /opt/edge_node
RUN chmod +x /opt/edge_node/entrypoint.sh

ENTRYPOINT ["/opt/edge_node/entrypoint.sh"]
