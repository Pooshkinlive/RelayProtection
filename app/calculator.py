from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import Cell, Sheet, Workbook, InputParameter
from app.database import get_db

def get_cell_value(db: Session, sheet_name: str, cell_addr: str, workbook_filename: str = None) -> Optional[float]:
    """Получить числовое значение ячейки по имени листа и адресу"""
    query = db.query(Cell).join(Sheet).join(Workbook)
    if workbook_filename:
        query = query.filter(Workbook.filename == workbook_filename)
    cell = query.filter(Sheet.sheet_name == sheet_name, Cell.address == cell_addr).first()
    return cell.value_numeric if cell and cell.value_numeric is not None else None

def calculate_mto(db: Session, inputs: Dict[str, float]) -> Dict[str, Any]:
    """Расчёт МТО на основе данных из Excel"""
    # Пример: K24 = '1'!B44 * L20
    i_relay = get_cell_value(db, "1", "B44")  # ток срабатывания реле
    k_otst = get_cell_value(db, "Расчет", "L20")  # коэффициент отстройки

    if i_relay and k_otst:
        setting_calc = i_relay * k_otst
    else:
        setting_calc = inputs.get("SET_MTO_RAW", 1000.0)

    # I_kz_min за ТР (K35)
    i_kz_min = get_cell_value(db, "Расчет", "K35")
    sensitivity = i_kz_min / setting_calc if i_kz_min and setting_calc else 0.0

    return {
        "setting_raw": inputs.get("SET_MTO_RAW"),
        "setting_calc": setting_calc,
        "i_kz_min": i_kz_min,
        "sensitivity": round(sensitivity, 3),  # ✅ Запятая добавлена
        "ok": sensitivity >= 1.2
    }

def calculate_mtz(db: Session, inputs: Dict[str, float]) -> Dict[str, Any]:
    i_relay = get_cell_value(db, "1", "J10")
    k_n = get_cell_value(db, "Расчет", "L19")
    setting_calc = i_relay * k_n if i_relay and k_n else inputs.get("SET_MTZ_RAW", 400.0)

    i_kz_min = get_cell_value(db, "Расчет", "K35")
    sensitivity = i_kz_min / setting_calc if i_kz_min and setting_calc else 0.0

    return {
        "setting_raw": inputs.get("SET_MTZ_RAW"),
        "setting_calc": setting_calc,
        "i_kz_min": i_kz_min,
        "sensitivity": round(sensitivity, 3),  # ✅ Исправлено и здесь тоже
        "ok": sensitivity >= 1.5
    }