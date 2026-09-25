#!/usr/bin/env bash
# ============================================================
# Set up PostgreSQL for the open-set Face Recognition system (Phase 0/5).
# Creates DB user, database, and runs migrations.
# ============================================================
set -euo pipefail

DB_USER="${POSTGRES_USER:-open_set_fr}"
DB_PASS="${POSTGRES_PASSWORD:-open_set_fr_secret}"
DB_NAME="${POSTGRES_DB:-open_set_fr}"

MIGRATIONS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../database/migrations" && pwd)"

echo "=== Installing PostgreSQL ==="
sudo apt-get update
sudo apt-get install -y postgresql postgresql-client

echo "=== Starting service ==="
sudo systemctl enable --now postgresql

echo "=== Creating role and database ==="
(cd /tmp && sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}') THEN
      CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';
   END IF;
END
\$\$;
SQL
)

(cd /tmp && sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1 \
  || sudo -u postgres createdb -O "${DB_USER}" "${DB_NAME}")

echo "=== Running migrations ==="
# NOTE: run psql from /tmp so the `postgres` user does not need read
# access to the project dir under the current user's home (mode 700).
# Migration files are fed via stdin: the current shell opens the file,
# psql (running as postgres) only reads stdin.
for f in "$MIGRATIONS_DIR"/*.sql; do
  echo "  applying: $(basename "$f")"
  (cd /tmp && sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" < "$f")
done

echo "=== Granting schema privileges ==="
(cd /tmp && sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" <<SQL
GRANT ALL ON SCHEMA public TO ${DB_USER};
SQL
)

echo "=== Done. PostgreSQL ready ==="
echo "User: ${DB_USER}  DB: ${DB_NAME}"
