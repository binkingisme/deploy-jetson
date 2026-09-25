#!/bin/bash
# ==============================================================================
# Jetson Orin Nano / Linux - Native PostgreSQL Setup Script
# Open-Set Face Recognition Thesis Project
# ==============================================================================

set -e

DB_NAME="open_set_fr"
DB_USER="open_set_fr"
DB_PASS="open_set_fr_pass"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="$(dirname "$SCRIPT_DIR")/database/init_schema.sql"

echo "=== Step 1: Installing PostgreSQL & Dependencies on Jetson ==="
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib

echo "=== Step 2: Enabling & Starting PostgreSQL Service ==="
sudo systemctl enable postgresql
sudo systemctl start postgresql

echo "=== Step 3: Creating Database and User ==="
sudo -u postgres psql -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER') THEN CREATE ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASS'; END IF; END \$\$;"
sudo -u postgres psql -c "SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

echo "=== Step 4: Configuring Listen Addresses for Remote/Local Connections ==="
PG_VER=$(psql -V | awk '{print $3}' | cut -d. -f1)
CONF_DIR="/etc/postgresql/$PG_VER/main"

if [ -d "$CONF_DIR" ]; then
    echo "Configuring postgresql.conf..."
    sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$CONF_DIR/postgresql.conf" || true
    sudo sed -i "s/listen_addresses = 'localhost'/listen_addresses = '*'/" "$CONF_DIR/postgresql.conf" || true
    
    echo "Configuring pg_hba.conf..."
    if ! sudo grep -q "$DB_USER" "$CONF_DIR/pg_hba.conf"; then
        echo "host    $DB_NAME        $DB_USER        0.0.0.0/0               md5" | sudo tee -a "$CONF_DIR/pg_hba.conf" > /dev/null
    fi
    
    sudo systemctl restart postgresql
fi

echo "=== Step 5: Applying Schema (init_schema.sql) ==="
if [ -f "$SQL_FILE" ]; then
    PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -f "$SQL_FILE"
    echo "✅ Schema successfully applied from $SQL_FILE"
else
    echo "⚠️ Warning: $SQL_FILE not found. Creating schema directly..."
    PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
fi

echo "=== Step 6: Verifying Tables ==="
PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "\dt"

echo "=============================================================================="
echo "🎉 PostgreSQL setup complete on Jetson!"
echo "Database: $DB_NAME"
echo "Username: $DB_USER"
echo "Host: localhost / Jetson IP (Port 5432)"
echo "Connection string: postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"
echo "=============================================================================="
