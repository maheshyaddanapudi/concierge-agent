#!/usr/bin/env bash
# Backup (M53, docs/operations/backup-restore.md): a logical dump of the
# database plus a tarball of the workspace volume, timestamped, under
# ./backups. The database is the whole application state; the workspace
# holds files runs wrote through the filesystem MCP server. Secrets live in
# .env and are NOT captured here — back that file up separately, as the
# secret it is.
#
#   ./backup.sh                 → backups/concierge-<UTC timestamp>.dump + .workspace.tar
#   BACKUP_DIR=/mnt/backups ./backup.sh
set -euo pipefail
cd "$(dirname "$0")"

BACKUP_DIR="${BACKUP_DIR:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
USER_NAME="${POSTGRES_USER:-concierge}"
DB_NAME="${POSTGRES_DB:-concierge}"
mkdir -p "$BACKUP_DIR"

DUMP="$BACKUP_DIR/concierge-$STAMP.dump"
WS="$BACKUP_DIR/concierge-$STAMP.workspace.tar"

start=$(date +%s)
docker compose exec -T db pg_dump -U "$USER_NAME" -d "$DB_NAME" -Fc > "$DUMP"
docker compose exec -T backend tar -C /workspace -cf - . > "$WS" 2>/dev/null || : > "$WS"
end=$(date +%s)

echo "database  $DUMP ($(du -h "$DUMP" | cut -f1))"
echo "workspace $WS ($(du -h "$WS" | cut -f1))"
echo "took $((end - start)) s"
