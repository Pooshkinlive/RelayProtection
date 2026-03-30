import os
import re
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple
from openpyxl import load_workbook
from sqlalchemy import create_engine, text
import pyodbc

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Конфигурация подключения
DB_CONFIG = {
    'driver': 'ODBC Driver 18 for SQL Server',
    'server': 'MSI-ALEXNAB\\SQLEXPRESS',
    'database': 'RZA_Calculator',
    'trusted_connection': 'yes',
    'encrypt': 'no',
    'trust_server_certificate': 'yes'
}

def get_connection_string() -> str:
    parts = [f"{k}={v}" for k, v in DB_CONFIG.items()]
    return "DRIVER={" + DB_CONFIG['driver'] + "};" + ";".join(parts)

def get_file_hash(filepath: str) -> str:
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def safe_value(val) -> Tuple[Optional[float], Optional[str], str]:
    """Конвертация значения ячейки"""
    if val is None:
        return None, "-", "constant"
    if isinstance(val, str):
        val = val.strip()
        if val.startswith('#'):
            return None, val, "error"
        if val == "-":
            return None, "-", "constant"
        try:
            return float(val.replace(',', '.')), None, "constant"
        except:
            return None, val, "constant"
    if isinstance(val, (int, float)):
        return float(val), None, "constant"
    return None, str(val), "constant"

def has_external_link(formula: str) -> bool:
    if not formula:
        return False
    pattern = r'\[[^\]]+\.(xls|xlsx?|xlsm|xlsb)\][^\s!]+!|\[EXTERNAL\]'
    return bool(re.search(pattern, formula, re.IGNORECASE))

def import_workbook(filepath: str, engine) -> dict:
    """Импорт одного Excel файла"""
    filepath = Path(filepath)
    if not filepath.exists():
        logger.error(f"Файл не найден: {filepath}")
        return {}
    
    file_hash = get_file_hash(str(filepath))
    filename = filepath.name
    
    logger.info(f"📂 Обработка файла: {filename}")
    
    with engine.begin() as conn:
        # Проверка существующего файла
        result = conn.execute(
            text("SELECT id, file_hash FROM workbooks WHERE filename = :fn"),
            {"fn": filename}
        ).fetchone()
        
        if result and result.file_hash == file_hash:
            logger.info(f"✅ Файл {filename} уже импортирован (хэш совпадает)")
            return {"skipped": filename}
        
        # Вставка/обновление файла
        if result:
            conn.execute(
                text("UPDATE workbooks SET file_hash = :h, imported_at = GETDATE() WHERE id = :id"),
                {"h": file_hash, "id": result.id}
            )
            workbook_id = result.id
            logger.info(f"🔄 Обновлён файл: {filename}")
        else:
            result = conn.execute(
                text("INSERT INTO workbooks (filename, file_hash) OUTPUT INSERTED.id VALUES (:fn, :h)"),
                {"fn": filename, "h": file_hash}
            )
            workbook_id = result.scalar()
            logger.info(f"➕ Создана запись о файле: {filename} (id={workbook_id})")
        
        # Парсинг Excel
        wb = load_workbook(str(filepath), data_only=False)
        stats = {"file": filename, "sheets": {}, "total_cells": 0}
        
        for ws in wb.worksheets:
            sheet_name = ws.title
            logger.info(f"  📄 Лист: {sheet_name}")
            
            # Вставка листа
            sheet_result = conn.execute(
                text("""
                    MERGE INTO sheets AS target
                    USING (SELECT :wid AS workbook_id, :sname AS sheet_name) AS source
                    ON (target.workbook_id = source.workbook_id AND target.sheet_name = source.sheet_name)
                    WHEN NOT MATCHED THEN 
                        INSERT (workbook_id, sheet_name) 
                        VALUES (source.workbook_id, source.sheet_name)
                    OUTPUT INSERTED.id;
                """),
                {"wid": workbook_id, "sname": sheet_name}
            )
            sheet_id = sheet_result.scalar()
            
            cells_count = 0
            for row in ws.iter_rows(min_row=1, max_col=ws.max_column, max_row=ws.max_row):
                for cell in row:
                    if cell.data_type != 'f' and cell.value is None:
                        continue
                    
                    num_val, text_val, dtype = safe_value(cell.value)
                    formula = cell.value if cell.data_type == 'f' else None
                    
                    if formula and isinstance(formula, str) and formula.startswith('='):
                        formula = formula[1:]
                    
                    # Вставка ячейки
                    conn.execute(
                        text("""
                            MERGE INTO cells AS target
                            USING (
                                SELECT :sid AS sheet_id, :addr AS address, :formula AS formula,
                                       :num AS value_numeric, :txt AS value_text, 
                                       :dtype AS data_type, :extlink AS has_external_link
                            ) AS source
                            ON (target.sheet_id = source.sheet_id AND target.address = source.address)
                            WHEN MATCHED THEN 
                                UPDATE SET formula = source.formula, 
                                           value_numeric = source.value_numeric,
                                           value_text = source.value_text,
                                           data_type = source.data_type,
                                           has_external_link = source.has_external_link,
                                           updated_at = GETDATE()
                            WHEN NOT MATCHED THEN 
                                INSERT (sheet_id, address, formula, value_numeric, 
                                        value_text, data_type, has_external_link)
                                VALUES (source.sheet_id, source.address, source.formula, 
                                        source.value_numeric, source.value_text, 
                                        source.data_type, source.has_external_link);
                        """),
                        {
                            "sid": sheet_id,
                            "addr": cell.coordinate.replace('$', ''),
                            "formula": formula,
                            "num": num_val,
                            "txt": text_val,
                            "dtype": dtype,
                            "extlink": has_external_link(formula or "")
                        }
                    )
                    cells_count += 1
            
            stats["sheets"][sheet_name] = cells_count
            stats["total_cells"] += cells_count
            logger.info(f"    ✓ Ячеек с формулами: {cells_count}")
        
        wb.close()
        return stats

def main():
    conn_str = get_connection_string()
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={conn_str}", echo=False)
    
    # Проверка подключения
    with engine.connect() as conn:
        result = conn.execute(text("SELECT @@VERSION"))
        logger.info(f"✅ Подключено к SQL Server: {result.scalar()[:80]}...")
    
    # Файлы для импорта
    files_to_import = [
        "data/input/Расчет реактансов по сетевым районам 2016.xlsx",
        "data/input/ЭКСПЕРТ.xlsx",
        "data/input/ЭТАЛОН защита ВЛ 6кВ ПЕРЕМИТИН.xlsx"
    ]
    
    logger.info("🚀 Начало импорта Excel файлов...")
    
    for f in files_to_import:
        if Path(f).exists():
            stats = import_workbook(f, engine)
            logger.info(f"✅ {stats}")
        else:
            logger.warning(f"⚠️ Файл не найден: {f}")
    
    logger.info("🎉 Импорт завершен!")

if __name__ == "__main__":
    main()