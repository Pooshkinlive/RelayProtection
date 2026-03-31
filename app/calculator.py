from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import Cell, Sheet, Workbook

def get_cell_value(db: Session, sheet_name: str, cell_addr: str, workbook_filename: str = None) -> Optional[float]:
    """Получить числовое значение ячейки по имени листа и адресу"""
    try:
        query = db.query(Cell).join(Sheet).join(Workbook)
        
        if workbook_filename:
            query = query.filter(Workbook.filename == workbook_filename)
        
        cell = query.filter(
            Sheet.sheet_name == sheet_name, 
            Cell.address == cell_addr.upper().replace('$', '')
        ).first()
        
        if cell and cell.value_numeric is not None:
            return float(cell.value_numeric)
        
        # Если нет числового значения, пробуем распарсить text
        if cell and cell.value_text:
            try:
                return float(cell.value_text.replace(',', '.'))
            except:
                return None
        
        return None
    except Exception as e:
        print(f"Ошибка получения {sheet_name}!{cell_addr}: {e}")
        return None

def calculate_mto(db: Session, inputs: Dict[str, float]) -> Dict[str, Any]:
    """Расчёт МТО на основе данных из Excel"""
    
    # Получаем ключевые значения из БД
    i_kz_min = get_cell_value(db, "Расчет", "K35")  # Iкз мин за ТР
    i_mto_calc = get_cell_value(db, "Расчет", "K24")  # Расчётная уставка МТО
    i_mto_raw = inputs.get("SET_MTO_RAW", None)  # Введённая пользователем
    
    # Если нет данных из БД — используем ввод пользователя
    if i_mto_calc is None and i_mto_raw is not None:
        i_mto_calc = i_mto_raw
    elif i_mto_calc is None:
        i_mto_calc = 1000.0  # Значение по умолчанию
    
    # Расчёт чувствительности
    sensitivity = i_kz_min / i_mto_calc if i_kz_min and i_mto_calc and i_mto_calc > 0 else 0.0
    ok = sensitivity >= 1.2
    
    return {
        "setting_raw": i_mto_raw,
        "setting_calc": i_mto_calc,
        "i_kz_min": i_kz_min,
        "sensitivity": round(sensitivity, 3),
        "ok": ok,
        "message": "OK" if ok else f"Недостаточная чувствительность ({sensitivity:.3f} < 1.2)"
    }

def calculate_mtz(db: Session, inputs: Dict[str, float]) -> Dict[str, Any]:
    """Расчёт МТЗ на основе данных из Excel"""
    
    # Получаем ключевые значения из БД
    i_kz_min = get_cell_value(db, "Расчет", "K35")  # Iкз мин за ТР
    i_mtz_calc = get_cell_value(db, "Расчет", "K25")  # Расчётная уставка МТЗ
    i_mtz_raw = inputs.get("SET_MTZ_RAW", None)  # Введённая пользователем
    
    # Если нет данных из БД — используем ввод пользователя
    if i_mtz_calc is None and i_mtz_raw is not None:
        i_mtz_calc = i_mtz_raw
    elif i_mtz_calc is None:
        i_mtz_calc = 400.0  # Значение по умолчанию
    
    # Расчёт чувствительности
    sensitivity = i_kz_min / i_mtz_calc if i_kz_min and i_mtz_calc and i_mtz_calc > 0 else 0.0
    ok = sensitivity >= 1.5
    
    return {
        "setting_raw": i_mtz_raw,
        "setting_calc": i_mtz_calc,
        "i_kz_min": i_kz_min,
        "sensitivity": round(sensitivity, 3),
        "ok": ok,
        "message": "OK" if ok else f"Недостаточная чувствительность ({sensitivity:.3f} < 1.5)"
    }

def get_excel_data(db: Session) -> Dict[str, Any]:
    """Получить все ключевые ячейки из ЭТАЛОН для отображения"""
    return {
        "k24": get_cell_value(db, "Расчет", "K24"),
        "k25": get_cell_value(db, "Расчет", "K25"),
        "k26": get_cell_value(db, "Расчет", "K26"),
        "k27": get_cell_value(db, "Расчет", "K27"),
        "k35": get_cell_value(db, "Расчет", "K35"),
        "e5": get_cell_value(db, "Расчет", "E5"),
        "f5": get_cell_value(db, "Расчет", "F5"),
        "j82": get_cell_value(db, "1", "J82")
    }