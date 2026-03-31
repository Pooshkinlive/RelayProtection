import os
import re
import hashlib
import logging
from pathlib import Path
from typing import Tuple, Optional, List, Dict  # ✅ Исправлено: запятая после Optional
from openpyxl import load_workbook
from sqlalchemy import create_engine, text
import pyodbc

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Конфигурация подключения к MS SQL Server 2022 ===
DB_CONFIG = {
    'driver': 'ODBC Driver 18 for SQL Server',
    'server': 'MSI-ALEXNAB\\SQLEXPRESS',  # или 'localhost\\SQLEXPRESS'
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
    """Безопасное преобразование значения ячейки"""
    if val is None:
        return None, "-", "constant"
    if isinstance(val, str):
        val = val.strip()
        if val.startswith('#'):
            return None, val, "error"
        if val == "-":
            return None, "-", "constant"
        try:
            # Замена запятой на точку для русской локали
            num = float(val.replace(',', '.'))
            return num, None, "constant"
        except ValueError:
            return None, val, "constant"
    if isinstance(val, (int, float)):
        return float(val), None, "constant"
    return None, str(val), "constant"

def normalize_formula(formula: str) -> str:
    """Очищает формулу от '=' и кавычек в именах листов"""
    if not formula:
        return ""
    formula = formula.lstrip('=')
    # Убираем кавычки из имён листов: 'Лист'!A1 → Лист!A1
    formula = re.sub(r"'([^']+)'!", r"\1!", formula)
    return formula

def has_external_link(formula: str) -> bool:
    if not formula:
        return False
    pattern = r'\[[^\]]+\.(xls|xlsx?|xlsm|xlsb)\][^\s!]+!'
    return bool(re.search(pattern, formula, re.IGNORECASE))

def import_workbook(filepath: str, engine) -> Dict:
    filepath = Path(filepath)
    if not filepath.exists():
        logger.error(f"Файл не найден: {filepath}")
        return {}

    file_hash = get_file_hash(str(filepath))
    filename = filepath.name

    with engine.begin() as conn:
        # Проверка существования файла с тем же хэшем
        existing = conn.execute(
            text("SELECT id, file_hash FROM workbooks WHERE filename = :fn"),
            {"fn": filename}
        ).fetchone()

        if existing:
            if existing.file_hash == file_hash:
                logger.info(f"Файл {filename} уже импортирован (хэш совпадает). Очищаем старые данные.")
                # Удаляем все листы и ячейки этого файла
                conn.execute(
                    text("DELETE FROM cells WHERE sheet_id IN (SELECT id FROM sheets WHERE workbook_id = :wid)"),
                    {"wid": existing.id}
                )
                conn.execute(
                    text("DELETE FROM sheets WHERE workbook_id = :wid"),
                    {"wid": existing.id}
                )
                workbook_id = existing.id
            else:
                logger.info(f"Хэш файла изменился. Удаляем старую запись.")
                conn.execute(text("DELETE FROM workbooks WHERE id = :id"), {"id": existing.id})
                res = conn.execute(
                    text("INSERT INTO workbooks (filename, file_hash) OUTPUT INSERTED.id VALUES (:fn, :h)"),
                    {"fn": filename, "h": file_hash}
                )
                workbook_id = res.scalar()
        else:
            res = conn.execute(
                text("INSERT INTO workbooks (filename, file_hash) OUTPUT INSERTED.id VALUES (:fn, :h)"),
                {"fn": filename, "h": file_hash}
            )
            workbook_id = res.scalar()
            logger.info(f"Создана запись о файле: {filename} (id={workbook_id})")

        wb = load_workbook(str(filepath), data_only=True)  # сохраняем формулы
        stats = {"file": filename, "sheets": {}, "total_cells": 0}

        for ws in wb.worksheets:
            sheet_name = ws.title
            sheet_res = conn.execute(
                text("INSERT INTO sheets (workbook_id, sheet_name) OUTPUT INSERTED.id VALUES (:wid, :sname)"),
                {"wid": workbook_id, "sname": sheet_name}
            )
            sheet_id = sheet_res.scalar()

            cells_count = 0
            for row in ws.iter_rows(min_row=1, max_col=ws.max_column, max_row=ws.max_row):
                for cell in row:
                    if cell.data_type != 'f' and cell.value is None:
                        continue

                    num_val, text_val, dtype = safe_value(cell.value)
                    raw_formula = None
                    if cell.data_type == 'f' and isinstance(cell.value, str):
                        raw_formula = cell.value
                        formula = normalize_formula(raw_formula)
                    else:
                        formula = None

                    clean_addr = cell.coordinate.replace('$', '')

                    # Вставляем только если такой записи ещё нет
                    conn.execute(
                        text("""
                            INSERT INTO cells (sheet_id, address, formula, value_numeric, value_text, data_type, has_external_link)
                            SELECT :sid, :addr, :formula, :num, :txt, :dtype, :extlink
                            WHERE NOT EXISTS (
                                SELECT 1 FROM cells WHERE sheet_id = :sid AND address = :addr
                            )
                        """),
                        {
                            "sid": sheet_id,
                            "addr": clean_addr,
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
            logger.info(f"Лист '{sheet_name}': {cells_count} ячеек")

        wb.close()
        return stats

def main():
    conn_str = get_connection_string()
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={conn_str}", echo=False)

    # Проверка подключения
    with engine.connect() as conn:
        result = conn.execute(text("SELECT @@VERSION"))
        logger.info(f"Подключено к SQL Server: {result.scalar()[:80]}...")

    # 🔑 Ключевое: правильные пути без синтаксических ошибок
    files = [
        "data/input/ЭТАЛОН защита ВЛ 6кВ ПЕРЕМИТИН.xlsx",
        "data/input/ЭКСПЕРТ.xlsx",
        "data/input/Расчет реактансов по сетевым районам 2016.xlsx"
    ]

    all_stats = {}
    for f in files:
        if Path(f).exists():
            stats = import_workbook(f, engine)
            all_stats[f] = stats
            logger.info(f"✅ {stats}")
        else:
            logger.warning(f"⚠️ Файл не найден: {f}")

    logger.info("🎉 Импорт завершён.")

if __name__ == "__main__":
    main()