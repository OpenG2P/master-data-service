#!/usr/bin/env bash
#
# run-pre-commit.sh
# -----------------
# Run pre-commit across all consolidated areas exactly like the CI
# (.github/workflows/pre-commit.yml) does: each area is checked with its own
# config, scoped to ONLY that area's files. The python package uses the root
# config; docker/ and deployments/ use their own lightweight configs so the
# python hooks (black/ruff) never run over Dockerfiles or Helm templates.
#
# Usage:
#   ./scripts/run-pre-commit.sh
#
# Run this before pushing to catch what CI would flag. The git pre-commit hook
# (installed via `pre-commit install`) only covers the python area on commit;
# this script covers everything.

set -uo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# area:config pairs — keep in sync with .github/workflows/pre-commit.yml
AREAS=(
  "master-data-api:.pre-commit-config.yaml"
  "docker:docker/.pre-commit-config.yaml"
  "deployments:deployments/.pre-commit-config.yaml"
)

rc=0
for entry in "${AREAS[@]}"; do
  area="${entry%%:*}"
  config="${entry##*:}"
  echo "==> pre-commit: ${area} (config: ${config})"
  if [ -z "$(git ls-files -- "${area}/")" ]; then
    echo "    No tracked files under ${area}/ — nothing to check."
    continue
  fi
  git ls-files -z -- "${area}/" | xargs -0 pre-commit run \
    --config "${config}" \
    --show-diff-on-failure --files || rc=1
done

exit "$rc"
