from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import Cell, Sheet, Workbook

def get_cell_value(db: Session, sheet_name: str, cell_addr: str, workbook_filename: str = None) -> Optional[float]:
    """Получить числовое значение ячейки по имени листа и адресу"""
    try:
        query = db.query(Cell).join(Sheet).join(Workbook)
        
        if workbook_filename:
            query = query.filter(Workbook.filename == workbook_filename)
        
        clean_sheet = sheet_name.strip()
        clean_addr = cell_addr.strip().upper().replace('$', '')
        
        cell = query.filter(
            Sheet.sheet_name == clean_sheet, 
            Cell.address == clean_addr
        ).first()
        
        if cell:
            if cell.value_numeric is not None:
                return float(cell.value_numeric)
            if cell.value_text:
                try:
                    return float(cell.value_text.replace(',', '.'))
                except:
                    return None
        
        return None
    except Exception as e:
        print(f"❌ Ошибка получения {sheet_name}!{cell_addr}: {e}")
        return None

def calculate_mto(db: Session, inputs: Dict[str, float]) -> Dict[str, Any]:
    """Расчёт МТО — использует ВВЕДЁННОЕ пользователем значение!"""
    
    # Iкз мин за ТР (из БД)
    i_kz_min = get_cell_value(db, "Расчет", "K35")
    
    # ⚠️ ВАЖНО: Используем ВВЕДЁННОЕ пользователем значение, а не K24 из БД!
    i_mto_user = inputs.get("SET_MTO_RAW", None)
    
    # K24 из БД — только для справки (расчётное значение из Excel)
    i_mto_excel = get_cell_value(db, "Расчет", "K24")
    
    # Если пользователь ввёл значение — используем его
    if i_mto_user is not None and i_mto_user > 0:
        i_mto_calc = i_mto_user
    elif i_mto_excel is not None:
        i_mto_calc = i_mto_excel
    else:
        i_mto_calc = 1000.0
    
    # Расчёт чувствительности
    sensitivity = i_kz_min / i_mto_calc if i_kz_min and i_mto_calc and i_mto_calc > 0 else 0.0
    ok = sensitivity >= 1.2
    
    return {
        "setting_raw": i_mto_user,
        "setting_calc": i_mto_calc,
        "setting_excel": i_mto_excel,
        "i_kz_min": i_kz_min,
        "sensitivity": round(sensitivity, 3),
        "ok": ok,
        "message": "OK" if ok else f"Недостаточная чувствительность ({sensitivity:.3f} < 1.2)"
    }

def calculate_mtz(db: Session, inputs: Dict[str, float]) -> Dict[str, Any]:
    """Расчёт МТЗ — использует ВВЕДЁННОЕ пользователем значение!"""
    
    i_kz_min = get_cell_value(db, "Расчет", "K35")
    
    # ⚠️ ВАЖНО: Используем ВВЕДЁННОЕ пользователем значение
    i_mtz_user = inputs.get("SET_MTZ_RAW", None)
    i_mtz_excel = get_cell_value(db, "Расчет", "K25")
    
    if i_mtz_user is not None and i_mtz_user > 0:
        i_mtz_calc = i_mtz_user
    elif i_mtz_excel is not None:
        i_mtz_calc = i_mtz_excel
    else:
        i_mtz_calc = 400.0
    
    sensitivity = i_kz_min / i_mtz_calc if i_kz_min and i_mtz_calc and i_mtz_calc > 0 else 0.0
    ok = sensitivity >= 1.5
    
    return {
        "setting_raw": i_mtz_user,
        "setting_calc": i_mtz_calc,
        "setting_excel": i_mtz_excel,
        "i_kz_min": i_kz_min,
        "sensitivity": round(sensitivity, 3),
        "ok": ok,
        "message": "OK" if ok else f"Недостаточная чувствительность ({sensitivity:.3f} < 1.5)"
    }

def get_excel_data(db: Session) -> Dict[str, Any]:
    """Получить все ключевые ячейки из ЭТАЛОН"""
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