# master-data-service

Consolidated monorepo for the OpenG2P Gen2 **Master Data** service — Master /
Reference data (geo, partner, etc.) for PBMS, Registry, Bridge and SPAR.

This repo merges what were previously three separate repos:

| Was                                   | Now lives under        |
| ------------------------------------- | ---------------------- |
| `openg2p-gen2-master-data-api`        | `master-data-api/`     |
| `openg2p-gen2-master-data-docker`     | `docker/`              |
| `openg2p-gen2-master-data-deployment` | `deployments/`         |

## Layout

```
master-data-api/                      Python (FastAPI) source — package openg2p-gen2-master-data
docker/master-data-api/Dockerfile     Image build (build context = repo root; installs local source)
deployments/charts/openg2p-master-data  Helm chart
scripts/uninstall-master-data.sh      Full teardown (release, PVC/PV, secrets, DB, DB user)
.github/workflows/                    CI: docker build, helm publish, pre-commit, tag
```

## Versioning

- **Docker image** `openg2p/master-data-api` is tagged with the repo ref — a
  build on `develop` publishes `openg2p/master-data-api:develop`.
- **Helm chart** version is `0.0.0-develop`.

## CI/CD

- `docker-build-api.yml` — builds & pushes the API image, tag = branch/git ref.
- `helm-publish.yml` — packages `deployments/charts/*` and publishes to
  `openg2p/openg2p-helm` (`gh-pages`).
- `pre-commit.yml` — runs each area's pre-commit config scoped to that area
  (python uses the root config; `docker/` and `deployments/` use their own
  lightweight configs).
- `tag.yml` — manual release tagging via the shared `openg2p-packaging` workflow.

## Uninstall

`scripts/uninstall-master-data.sh` removes a release and everything it leaves
behind — Helm release, leftover hook Jobs/Pods, Secrets/ConfigMaps, the
PostgreSQL database and role inside `commons-postgresql`, and the PVCs/PVs.

```bash
# Preview only (no changes):
./scripts/uninstall-master-data.sh --namespace <ns> --dry-run

# For real (prompts for confirmation):
./scripts/uninstall-master-data.sh --namespace <ns> [--release master-data]
```

See the script header (`--help`) for all options.
