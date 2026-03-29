import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def create_test_database():
    try:
        # Connect to default 'postgres' database
        con = psycopg2.connect(
            dbname="postgres",
            user="postgres",
            password="postgres",
            host="localhost"
        )
        con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = con.cursor()
        
        # Check if database exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname = 'carometro_test'")
        exists = cur.fetchone()
        
        if not exists:
            print("Creating database 'carometro_test'...")
            cur.execute("CREATE DATABASE carometro_test")
            print("Database created successfully.")
        else:
            print("Database 'carometro_test' already exists.")
            
        cur.close()
        con.close()
    except Exception as e:
        print(f"Error creating database: {e}")

if __name__ == "__main__":
    create_test_database()
