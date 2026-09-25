import os
import sys
import psycopg2

def setup_database(db_url=None):
    """
    Executes database/init_schema.sql against PostgreSQL database.
    DB URL format: postgresql://username:password@host:port/dbname
    """
    if not db_url:
        db_url = os.getenv("DATABASE_URL", "postgresql://open_set_fr:open_set_fr_pass@localhost:5432/open_set_fr")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sql_path = os.path.join(script_dir, "init_schema.sql")

    if not os.path.exists(sql_path):
        print(f"Error: SQL file not found at {sql_path}")
        sys.exit(1)

    print(f"Connecting to database: {db_url}...")
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        with open(sql_path, "r", encoding="utf-8") as f:
            sql_content = f.read()

        print("Executing init_schema.sql...")
        cursor.execute(sql_content)
        conn.commit()

        cursor.close()
        conn.close()
        print("Database schema successfully created on Jetson PostgreSQL!")
    except Exception as e:
        print(f"Failed to setup database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else None
    setup_database(url)
