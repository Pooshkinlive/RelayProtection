import pyodbc

conn_str = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=MSI-ALEXNAB\\SQLEXPRESS;"
    "DATABASE=RZA_Calculator;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

try:
    conn = pyodbc.connect(conn_str)
    print("✅ Подключение успешно!")
    
    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION")
    version = cursor.fetchone()[0]
    print(f"Версия: {version[:80]}...")
    
    cursor.execute("SELECT name FROM sys.tables")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Таблицы в БД: {tables}")
    
    conn.close()
except Exception as e:
    print(f"❌ Ошибка: {e}")