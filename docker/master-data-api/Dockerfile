FROM python:3.12.11-alpine3.22

# External OpenG2P library ref (not part of this repo). Override via build-arg /
# workflow input. The master-data code is installed from the LOCAL in-repo
# source, so the image always reflects the current branch.
ARG FASTAPI_COMMON_REF=1.2.1
# Pin iam-core to the IAM 1.4 line (data_policy lives here; 1.3 does not export it).
ARG IAM_CORE_REF=1.4.2

RUN apk add --no-cache --virtual .build-deps gcc libc-dev linux-headers make \
 && apk add --no-cache bash git gettext libpq-dev libmagic

WORKDIR /app

# External libs (openg2p-fastapi-common)
RUN pip install --no-cache-dir \
    "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-common" \
    "git+https://github.com/openg2p/iam@${IAM_CORE_REF}#subdirectory=iam-core"

# Local master-data source (build context = repo root). Remaining deps resolve
# from PyPI via the package's pyproject.
COPY master-data-api /src/master-data-api
RUN pip install --no-cache-dir /src/master-data-api

RUN apk del --no-network .build-deps

ENV PYTHONUNBUFFERED=1
ENV MASTER_DATA_API_WORKER_TYPE=gunicorn
ENV MASTER_DATA_API_HOST=0.0.0.0
ENV MASTER_DATA_API_PORT=8000
ENV MASTER_DATA_API_NO_OF_WORKERS=8

# Run DB migrations, then start Gunicorn with Uvicorn workers
CMD python3 -m openg2p_gen2_master_data.main migrate; \
    ${MASTER_DATA_API_WORKER_TYPE} "openg2p_gen2_master_data.main:app" --workers ${MASTER_DATA_API_NO_OF_WORKERS} --worker-class uvicorn.workers.UvicornWorker --bind ${MASTER_DATA_API_HOST}:${MASTER_DATA_API_PORT}
