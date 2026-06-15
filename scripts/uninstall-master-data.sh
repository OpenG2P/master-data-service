#!/usr/bin/env bash
#
# uninstall-master-data.sh
# ------------------------
# Cleanly uninstall an OpenG2P Master Data (Gen 2) Helm release and every
# resource it touched, including the PostgreSQL database and role that live
# inside the commons-postgresql instance (which are NOT owned by the
# master-data Helm release and therefore survive `helm uninstall`).
#
# What it does, in order:
#   1. helm uninstall <release>            (master-data workloads, services,
#                                           helm-owned secrets & configmaps)
#   2. Delete leftover Jobs + their Pods   (helm hook jobs like postgres-init
#                                           keep themselves around via
#                                           hook-delete-policy: before-hook-creation)
#   3. Sweep leftover Secrets/ConfigMaps   (label: app.kubernetes.io/instance)
#   4. Drop Postgres database + role       (via `kubectl exec` into
#                                           commons-postgresql-0)
#   5. Delete PVCs by label                (app.kubernetes.io/instance)
#   6. Delete PVs still bound to those PVCs
#      (typically `Released` PVs created with reclaimPolicy=Retain)
#
# Requires: kubectl (cluster admin), helm, bash 4+.
#
# USAGE:
#   ./uninstall-master-data.sh \
#       --namespace <ns> \
#       [--release <name>]            (default: master-data)
#       [--postgres-release <name>]   (default: commons-postgresql)
#       [--postgres-namespace <ns>]   (default: same as --namespace)
#       [--keep-pvs]                  (delete PVCs but not PVs)
#       [--dry-run]                   (print actions, change nothing)
#       [--yes]                       (skip interactive confirmation)
#
# EXAMPLES:
#   # Dry run first — no changes made:
#   ./uninstall-master-data.sh --namespace master-data --dry-run
#
#   # For real, with confirmation prompt:
#   ./uninstall-master-data.sh --namespace master-data
#
#   # Non-interactive (CI / scripted):
#   ./uninstall-master-data.sh --namespace master-data --yes

set -euo pipefail

# ---------- defaults ----------
RELEASE="master-data"
NAMESPACE=""
POSTGRES_RELEASE="commons-postgresql"
POSTGRES_NAMESPACE=""
KEEP_PVS=false
DRY_RUN=false
ASSUME_YES=false

# ---------- cli ----------
usage() { sed -n '2,40p' "$0"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release)           RELEASE="$2";           shift 2 ;;
    --namespace|-n)      NAMESPACE="$2";         shift 2 ;;
    --postgres-release)  POSTGRES_RELEASE="$2";  shift 2 ;;
    --postgres-namespace) POSTGRES_NAMESPACE="$2"; shift 2 ;;
    --keep-pvs)          KEEP_PVS=true;          shift ;;
    --dry-run)           DRY_RUN=true;           shift ;;
    --yes|-y)            ASSUME_YES=true;        shift ;;
    -h|--help)           usage ;;
    *) echo "Unknown argument: $1"; usage ;;
  esac
done

[[ -z "$NAMESPACE" ]] && { echo "ERROR: --namespace is required"; exit 1; }
[[ -z "$POSTGRES_NAMESPACE" ]] && POSTGRES_NAMESPACE="$NAMESPACE"

# ---------- derived: DB / user names (templated exactly like values.yaml) ----------
# values.yaml:
#   masterDataDB:     '{{ if eq .Release.Name "master-data" }}master_data{{ else }}{{ printf "%s_master_data" .Release.Name | replace "-" "_" }}{{ end }}'
#   masterDataDBUser: '{{ if eq .Release.Name "master-data" }}master_data_user{{ else }}{{ printf "%s_master_data_user" .Release.Name | replace "-" "_" }}{{ end }}'
# i.e. when the release is literally "master-data" the names are NOT prefixed
# (avoids master_data_master_data); any other release name is prefixed.
if [[ "$RELEASE" == "master-data" ]]; then
  MASTERDATA_DB="master_data"
  MASTERDATA_USER="master_data_user"
else
  RELEASE_UNDERSCORED="${RELEASE//-/_}"
  MASTERDATA_DB="${RELEASE_UNDERSCORED}_master_data"
  MASTERDATA_USER="${RELEASE_UNDERSCORED}_master_data_user"
fi

# ---------- helpers ----------
_red()   { printf "\033[31m%s\033[0m\n" "$*"; }
_green() { printf "\033[32m%s\033[0m\n" "$*"; }
_yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
_blue()  { printf "\033[34m%s\033[0m\n" "$*"; }

run() {
  # Print + execute, or just print if --dry-run.
  # Never aborts the script on non-zero exit — cleanup commands must be
  # idempotent. Already-deleted resources produce a notice and we move on.
  echo "  \$ $*"
  if [[ "$DRY_RUN" == false ]]; then
    eval "$@" || _yellow "  (command returned non-zero — continuing)"
  fi
}

kexec_psql() {
  # Run SQL as postgres superuser inside the commons-postgresql pod.
  # Uses PGPASSWORD from the pod's env so no secret reads are needed on
  # the admin's machine. Tolerant of failure — script continues.
  local sql="$1"
  local cmd=(kubectl exec -n "$POSTGRES_NAMESPACE" "$PG_POD" -c postgresql -- \
             bash -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U postgres -v ON_ERROR_STOP=0 -c \"$sql\"")
  echo "  \$ psql -U postgres -c \"$sql\""
  if [[ "$DRY_RUN" == false ]]; then
    "${cmd[@]}" || _yellow "  (psql returned non-zero — continuing)"
  fi
}

# ---------- pre-flight ----------
_blue "==> Pre-flight checks"

command -v kubectl >/dev/null || { _red "kubectl not found"; exit 1; }
command -v helm    >/dev/null || { _red "helm not found";    exit 1; }

if kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
  NAMESPACE_EXISTS=true
  _green "  Namespace '$NAMESPACE' exists"
else
  NAMESPACE_EXISTS=false
  _yellow "  Namespace '$NAMESPACE' does not exist — namespace-scoped cleanup will be skipped"
fi

# Locate commons-postgresql pod. Bitnami's chart gives it these labels.
PG_POD=""
if kubectl get ns "$POSTGRES_NAMESPACE" >/dev/null 2>&1; then
  PG_POD=$(kubectl get pod -n "$POSTGRES_NAMESPACE" \
    -l "app.kubernetes.io/instance=$POSTGRES_RELEASE,app.kubernetes.io/name=postgresql" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

  # Fallback: by name.
  if [[ -z "$PG_POD" ]]; then
    if kubectl get pod -n "$POSTGRES_NAMESPACE" "${POSTGRES_RELEASE}-0" >/dev/null 2>&1; then
      PG_POD="${POSTGRES_RELEASE}-0"
    fi
  fi
fi

if [[ -z "$PG_POD" ]]; then
  PG_POD_FOUND=false
  _yellow "  commons-postgresql pod not found — DB / role drop step will be skipped"
  _yellow "  (tried label app.kubernetes.io/instance=$POSTGRES_RELEASE and pod name ${POSTGRES_RELEASE}-0 in namespace '$POSTGRES_NAMESPACE')"
else
  PG_POD_FOUND=true
  _green "  Found Postgres pod: $PG_POD (namespace: $POSTGRES_NAMESPACE)"
fi

# Helm release presence is not strictly required (user may have already uninstalled
# and is now running the cleanup half). Note it but don't abort.
if helm -n "$NAMESPACE" status "$RELEASE" >/dev/null 2>&1; then
  _green "  Helm release '$RELEASE' found in namespace '$NAMESPACE'"
  HELM_RELEASE_EXISTS=true
else
  _yellow "  Helm release '$RELEASE' not found — will skip helm uninstall step"
  HELM_RELEASE_EXISTS=false
fi

# ---------- show the blast radius ----------
_blue "==> Resources to be deleted"

echo
echo "Helm release:       $RELEASE (namespace: $NAMESPACE)"
echo "Postgres database:  $MASTERDATA_DB"
echo "Postgres role:      $MASTERDATA_USER"
echo "Postgres pod:       ${PG_POD:-<not found — will skip DB drop>} ($POSTGRES_NAMESPACE)"
echo

if [[ "$NAMESPACE_EXISTS" == true ]]; then
  echo "Jobs (label app.kubernetes.io/instance=$RELEASE):"
  kubectl -n "$NAMESPACE" get job -l "app.kubernetes.io/instance=$RELEASE" \
    --no-headers 2>/dev/null | awk '{print "  - " $1}' || echo "  (none)"

  echo "Secrets (label app.kubernetes.io/instance=$RELEASE):"
  kubectl -n "$NAMESPACE" get secret -l "app.kubernetes.io/instance=$RELEASE" \
    --no-headers 2>/dev/null | awk '{print "  - " $1}' || echo "  (none)"

  echo "ConfigMaps (label app.kubernetes.io/instance=$RELEASE):"
  kubectl -n "$NAMESPACE" get configmap -l "app.kubernetes.io/instance=$RELEASE" \
    --no-headers 2>/dev/null | awk '{print "  - " $1}' || echo "  (none)"

  echo "PVCs (label app.kubernetes.io/instance=$RELEASE):"
  kubectl -n "$NAMESPACE" get pvc -l "app.kubernetes.io/instance=$RELEASE" \
    --no-headers 2>/dev/null | awk '{print "  - " $1}' || echo "  (none)"
else
  echo "(namespace '$NAMESPACE' does not exist — no namespace-scoped resources to preview)"
fi

if [[ "$KEEP_PVS" == false ]]; then
  echo "PVs (bound to above PVCs):"
  if [[ "$NAMESPACE_EXISTS" == true ]]; then
    PVC_NAMES=$(kubectl -n "$NAMESPACE" get pvc -l "app.kubernetes.io/instance=$RELEASE" \
                  -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
    if [[ -n "$PVC_NAMES" ]]; then
      for pvc in $PVC_NAMES; do
        kubectl get pv -o json 2>/dev/null | \
          jq -r --arg ns "$NAMESPACE" --arg n "$pvc" \
            '.items[] | select(.spec.claimRef.namespace==$ns and .spec.claimRef.name==$n) | "  - " + .metadata.name' \
          2>/dev/null || true
      done
    else
      echo "  (no PVCs; will still check for orphaned PVs claimed by namespace '$NAMESPACE' or labeled with release)"
    fi
  fi
  # Orphaned / Released PVs — show regardless of namespace existence.
  kubectl get pv -o json 2>/dev/null | \
    jq -r --arg ns "$NAMESPACE" --arg rel "$RELEASE" \
      '.items[] | select((.spec.claimRef.namespace==$ns) or (.metadata.labels["app.kubernetes.io/instance"]==$rel)) | "  - " + .metadata.name + " (" + .status.phase + ")"' \
    2>/dev/null | sort -u || true
fi
echo

# ---------- confirmation ----------
if [[ "$DRY_RUN" == true ]]; then
  _yellow "DRY-RUN: no changes will be made."
fi

if [[ "$ASSUME_YES" == false && "$DRY_RUN" == false ]]; then
  _red "This is destructive. Type the release name ('$RELEASE') to confirm:"
  read -r CONFIRM
  if [[ "$CONFIRM" != "$RELEASE" ]]; then
    _red "Confirmation did not match. Aborting."
    exit 1
  fi
fi

# ========== STEP 1: helm uninstall ==========
_blue "==> [1/6] Helm uninstall"
if [[ "$HELM_RELEASE_EXISTS" == true ]]; then
  run "helm uninstall '$RELEASE' -n '$NAMESPACE' --wait --timeout 5m || true"
else
  echo "  (skipped — release not present)"
fi

# ========== STEP 2: delete leftover Jobs (and their Pods) ==========
# Helm hook Jobs (e.g. postgres-init) are created with
# `helm.sh/hook-delete-policy: before-hook-creation`, which means they are NOT
# cleaned up by `helm uninstall`. We delete them explicitly here — BEFORE
# dropping the DB, so their Pods close their Postgres connections cleanly.
_blue "==> [2/6] Delete leftover Jobs and their Pods"
if [[ "$NAMESPACE_EXISTS" == true ]]; then
  run "kubectl -n '$NAMESPACE' delete job -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found --wait=true --timeout=2m"
  # Orphan pods (completed/failed) that a Job left behind after TTL etc.
  run "kubectl -n '$NAMESPACE' delete pod -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found --field-selector=status.phase!=Running"
else
  echo "  (skipped — namespace '$NAMESPACE' not present)"
fi

# ========== STEP 3: sweep leftover Secrets & ConfigMaps ==========
_blue "==> [3/6] Sweep leftover Secrets / ConfigMaps"
if [[ "$NAMESPACE_EXISTS" == true ]]; then
  run "kubectl -n '$NAMESPACE' delete secret    -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found"
  run "kubectl -n '$NAMESPACE' delete configmap -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found"
else
  echo "  (skipped — namespace '$NAMESPACE' not present)"
fi

# ========== STEP 4: drop Postgres DB & role ==========
_blue "==> [4/6] Drop Postgres database and role"
if [[ "$PG_POD_FOUND" == true ]]; then
  echo "  - Database: $MASTERDATA_DB"
  kexec_psql "REVOKE CONNECT ON DATABASE \\\"$MASTERDATA_DB\\\" FROM PUBLIC;"
  kexec_psql "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$MASTERDATA_DB' AND pid <> pg_backend_pid();"
  kexec_psql "DROP DATABASE IF EXISTS \\\"$MASTERDATA_DB\\\";"

  echo "  - Role: $MASTERDATA_USER"
  # Reassign/drop stray ownership outside the dropped DB (roles can own cluster-wide objects).
  kexec_psql "REASSIGN OWNED BY \\\"$MASTERDATA_USER\\\" TO postgres;"
  kexec_psql "DROP OWNED BY \\\"$MASTERDATA_USER\\\";"
  kexec_psql "DROP ROLE IF EXISTS \\\"$MASTERDATA_USER\\\";"
else
  echo "  (skipped — commons-postgresql pod not reachable; if Postgres is already gone, the DB is gone too)"
fi

# ========== STEP 5: PVCs ==========
_blue "==> [5/6] Delete PVCs"
if [[ "$NAMESPACE_EXISTS" == true ]]; then
  run "kubectl -n '$NAMESPACE' delete pvc -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found"
else
  echo "  (skipped — namespace '$NAMESPACE' not present; any orphan PVs handled in step 6)"
fi

# ========== STEP 6: PVs ==========
_blue "==> [6/6] Delete PVs"
if [[ "$KEEP_PVS" == true ]]; then
  _yellow "  (skipped — --keep-pvs)"
else
  # Any PV that still references a PVC in $NAMESPACE labeled with our release.
  # After step 5 the PVCs are gone, so rely on claimRef.
  pv_list=$(kubectl get pv -o json 2>/dev/null | \
    jq -r --arg ns "$NAMESPACE" --arg rel "$RELEASE" \
      '.items[] | select(.spec.claimRef.namespace==$ns) | select(.status.phase=="Released" or .status.phase=="Failed") | .metadata.name' \
    2>/dev/null || true)
  # Also pick up PVs that were labeled at creation time.
  pv_labeled=$(kubectl get pv -l "app.kubernetes.io/instance=$RELEASE" \
                 -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
  pv_all=$(echo "$pv_list $pv_labeled" | tr ' ' '\n' | sort -u | tr '\n' ' ' | sed 's/^ *//;s/ *$//')

  if [[ -z "$pv_all" ]]; then
    echo "  (no PVs to delete)"
  else
    for pv in $pv_all; do
      run "kubectl delete pv '$pv' --ignore-not-found"
    done
  fi
fi

echo
_green "==> Done."
if [[ "$DRY_RUN" == true ]]; then
  _yellow "    (dry-run — nothing was actually changed)"
fi
