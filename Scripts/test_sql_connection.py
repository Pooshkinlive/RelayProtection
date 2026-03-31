import sys
from pathlib import Path

# === ДОБАВЛЯЕМ КОРЕНЬ ПРОЕКТА В PYTHON PATH ===
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
# ===============================================

from app.database import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT @@VERSION"))
        print("✅ Подключение успешно!")
        print(f"Версия: {result.scalar()[:100]}")
        
        # Проверка таблиц
        tables = conn.execute(text("""
            SELECT name FROM sys.tables WHERE type = 'U'
        """))
        print("\n📋 Таблицы в БД:")
        for t in tables:
            print(f"  - {t[0]}")
except Exception as e:
    print(f"❌ Ошибка: {e}")