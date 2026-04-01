import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import engine, Base
from app.models import Workbook, Sheet, Cell, LineType, LineSection, UserConfiguration, InputParameter, CalculationResult
from sqlalchemy import text

print('Creating tables in DB RZA_Calculator...')

# Создаём все таблицы
Base.metadata.create_all(engine)
print('Tables created successfully.')

# Проверка созданных таблиц
with engine.connect() as conn:
    tables = conn.execute(text("SELECT name FROM sys.tables WHERE type = 'U' ORDER BY name"))
    print('\nTables in DB:')
    for t in tables:
        print(f'  - {t[0]}')

print('\nDone.')