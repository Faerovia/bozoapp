#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
# backup.sh — denní pg_dump + upload do Hetzner Object Storage (S3-compatible).
#
# Crontab:
#   0 2 * * * /opt/bozoapp/scripts/backup.sh >> /var/log/bozoapp_backup.log 2>&1
#
# Required env (v /etc/bozoapp/backup.env):
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE  — Postgres connection
#   S3_BUCKET, S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY  — Hetzner Object Storage
#   GPG_PASSPHRASE  — symmetric encryption (2nd layer over TLS upload)
#   RETENTION_DAYS  — default 30
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# Načti secrets
if [[ -f /etc/bozoapp/backup.env ]]; then
    # shellcheck disable=SC1091
    source /etc/bozoapp/backup.env
else
    echo "ERROR: /etc/bozoapp/backup.env nenalezen" >&2
    exit 1
fi

RETENTION_DAYS=${RETENTION_DAYS:-30}
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
FILE="bozoapp_${PGDATABASE}_${TIMESTAMP}.sql.gz.gpg"
TMP="/tmp/${FILE}"

echo "[$(date -Is)] Starting backup: ${FILE}"

# 1) pg_dump → gzip → gpg symmetric
pg_dump --no-owner --no-acl --clean --if-exists \
    -h "${PGHOST}" -p "${PGPORT:-5432}" -U "${PGUSER}" "${PGDATABASE}" \
    | gzip -9 \
    | gpg --batch --yes --symmetric --cipher-algo AES256 \
          --passphrase "${GPG_PASSPHRASE}" --output "${TMP}"

SIZE=$(stat -c%s "${TMP}")
echo "[$(date -Is)] Dump size: ${SIZE} bytes"

# 2) Upload do Object Storage přes aws CLI (kompatibilní s Hetzner)
AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY}" \
aws --endpoint-url "${S3_ENDPOINT}" \
    s3 cp "${TMP}" "s3://${S3_BUCKET}/daily/${FILE}"

echo "[$(date -Is)] Uploaded to s3://${S3_BUCKET}/daily/${FILE}"

# 3) Smaž lokální kopii
rm -f "${TMP}"

# 4) Retention: smaž objekty starší než RETENTION_DAYS
CUTOFF=$(date -u -d "${RETENTION_DAYS} days ago" +"%Y%m%d")
AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY}" \
aws --endpoint-url "${S3_ENDPOINT}" \
    s3 ls "s3://${S3_BUCKET}/daily/" \
    | awk -v cutoff="${CUTOFF}" '{
        # Occupy columns: date time size key
        if ($4 ~ /bozoapp_/) {
            match($4, /[0-9]{8}/, arr)
            if (arr[0] < cutoff) print $4
        }
    }' \
    | while read -r old_key; do
        echo "[$(date -Is)] Deleting old backup: ${old_key}"
        aws --endpoint-url "${S3_ENDPOINT}" \
            s3 rm "s3://${S3_BUCKET}/daily/${old_key}"
    done

echo "[$(date -Is)] Backup completed successfully"
