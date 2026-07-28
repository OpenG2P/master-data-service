# Master Data Service — db-seed image.
#
# Seeds the geo hierarchy at MDS install. Geography is master data, so MDS seeds
# its own: previously the only geo loader in the platform shipped with the
# registry db-seed image, which meant master data was populated as a side effect
# of installing a registry.
#
# Country packs (hierarchy, official P-codes, simplified boundary geometry) are
# built by openg2p-data/scripts/fetch_country_pack.py from OCHA COD-AB and live
# in that repo, which is cloned in below. Which pack a deployment loads is chosen
# by geoSeed.countryPack in the chart — this image carries all of them.
FROM python:3.11-slim

ARG OPENG2P_DATA_REPO=https://github.com/openg2p/openg2p-data.git
# Tracks the matching line of openg2p-data, mirroring the registry db-seed
# image. Release builds should pass a tag or commit SHA — the fetch+checkout
# below takes either, whereas `git clone -b` would accept only a branch name.
ARG OPENG2P_DATA_BRANCH=develop

ENV OPENG2P_DATA_DIR=/openg2p-data \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir psycopg2-binary boto3

RUN mkdir -p ${OPENG2P_DATA_DIR} \
    && cd ${OPENG2P_DATA_DIR} \
    && git init -q \
    && git remote add origin ${OPENG2P_DATA_REPO} \
    && git fetch -q --depth 1 origin ${OPENG2P_DATA_BRANCH} \
    && git checkout -q FETCH_HEAD \
    && rm -rf ${OPENG2P_DATA_DIR}/.git

COPY docker/db-seed/load_geo_pack.py /seed/load_geo_pack.py
RUN chmod +x /seed/load_geo_pack.py

WORKDIR /seed
