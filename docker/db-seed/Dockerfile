# Master Data DB-seed image.
#
# Postgres-client image that ships a Python geo loader and clones the
# openg2p-data repo (shared reference data) at build time. At container-run time
# it loads the geo hierarchy + level values from openg2p-data/geo/*.csv into the
# master-data Postgres (g2p_geo_levels, g2p_geo_level_values).
#
# Unlike the registry db-seed images there is no MinIO / images / templates / AWE
# / meta-data SQL — geo is pure CSV loaded into two tables.
#
# Build context = repo root (so docker/db-seed/ is reachable).

FROM postgres:16-alpine

ARG GIT_COMMIT=dev
ARG BUILD_TIME=dev
ARG OPENG2P_DATA_REPO=https://github.com/openg2p/openg2p-data.git
ARG OPENG2P_DATA_BRANCH=2.0

ENV GIT_COMMIT=${GIT_COMMIT} \
    BUILD_TIME=${BUILD_TIME} \
    OPENG2P_DATA_DIR=/openg2p-data

RUN apk add --no-cache python3 py3-pip git

COPY docker/db-seed/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Clone openg2p-data (shared geo reference CSVs).
RUN git clone --depth 1 -b ${OPENG2P_DATA_BRANCH} ${OPENG2P_DATA_REPO} /openg2p-data \
    && rm -rf /openg2p-data/.git

COPY docker/db-seed/entrypoint.sh /seed/entrypoint.sh
COPY docker/db-seed/load_geo_data.py /seed/load_geo_data.py
RUN chmod +x /seed/entrypoint.sh /seed/load_geo_data.py

ENTRYPOINT ["/seed/entrypoint.sh"]
