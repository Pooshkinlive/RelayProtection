from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Dict, List
import json
from app.database import get_db
from app.models import InputParameter, Cell, Sheet, Workbook
import os
from pathlib import Path

app = FastAPI(title="RZA Calculator", description="Расчёт уставок РЗА по Excel-логике")

app.mount("/static", StaticFiles(directory="templates"), name="static")

@app.get("/")
async def root():
    # Используем абсолютный путь, чтобы избежать проблем
    file_path = Path(__file__).parent.parent / "templates" / "index.html"
    if file_path.exists():
        return FileResponse(file_path)
    else:
        return {"error": "Файл templates/index.html не найден."}

@app.get("/api/parameters")
async def get_parameters(db: Session = Depends(get_db)) -> List[Dict]:
    """Возвращает все параметры с метками is_engineer_input"""
    params = db.query(InputParameter).order_by(InputParameter.display_order).all()
    result = []
    for p in params:
        current_value = get_cell_value(db, p.excel_sheet, p.excel_cell, p.param_code)
        result.append({
            "code": p.param_code,        # Исправлено: было p.paramname"
            "name": p.param_name,
            "description": p.param_description or "",
            "unit": p.unit,
            "default_value": float(p.default_value) if p.default_value else None,
            "min_value": float(p.min_value) if p.min_value else None,
            "max_value": float(p.max_value) if p.max_value else None,
            "required": p.is_required,
            "engineer_input": p.is_engineer_input,
            "excel_sheet": p.excel_sheet,
            "excel_cell": p.excel_cell,
            "current_value": current_value
        })
    return result

def get_cell_value(db: Session, sheet_name: str, cell_addr: str, param_code: str) -> float:
    """Получает текущее значение ячейки из БД (для отображения в форме)"""
    try:
        cell = db.query(Cell).join(Sheet).join(Workbook).filter(
            Sheet.sheet_name == sheet_name,
            Cell.address == cell_addr
        ).first()
        if cell and cell.value_numeric is not None:
            return float(cell.value_numeric)
        # Если нет — пытаемся взять из default_value
        param = db.query(InputParameter).filter(InputParameter.param_code == param_code).first()
        return float(param.default_value) if param and param.default_value else 0.0
    except Exception as e:
        print(f"Ошибка получения {sheet_name}!{cell_addr}: {e}")
        return 0.0

@app.post("/api/calculate")
async def calculate(inputs: Dict[str, float], db: Session = Depends(get_db)):
    """Основной расчёт: проверка чувствительности МТО/МТЗ"""
    # Получаем ключевые расчётные ячейки из БД
    i_kz_min = get_cell_value(db, "Расчет", "K35", "I_KZ_MIN_BEHIND_TR")  # 74.89 А (пример)
    i_mto_raw: float = inputs.get("SET_MTO_RAW", 1250.0)
    i_mtz_raw: float = inputs.get("SET_MTZ_RAW", 2000.0)

    # МТО: должна быть ≤ i_kz_min * k_чувств (обычно 1.2)
    sens_mto = i_kz_min / i_mto_raw if i_mto_raw > 0 else 0.0
    ok_mto = sens_mto >= 1.2

    # МТЗ: должна быть ≤ i_kz_min * k_чувств (обычно 1.5 для 100% зоны)
    sens_mtz = i_kz_min / i_mtz_raw if i_mtz_raw > 0 else 0.0
    ok_mtz = sens_mtz >= 1.5

    return {
        "input": inputs,
        "i_kz_min_behind_tr": i_kz_min,
        "mto": {
            "setting_raw": i_mto_raw,
            "sensitivity": round(sens_mto, 3),
            "ok": ok_mto,
            "message": "OK" if ok_mto else f"Недостаточная чувствительность (<1.2)"
        },
        "mtz": {
            "setting_raw": i_mtz_raw,
            "sensitivity": round(sens_mtz, 3),
            "message": "OK" if ok_mtz else f"Недостаточная чувствительность (<1.5)"
        }
    }
