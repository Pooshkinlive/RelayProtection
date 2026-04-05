from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Dict, Any, List
from pydantic import BaseModel

from app.database import get_db
from app.calculator import calculate_rza_settings, generate_chart_data, get_line_type
from app.models import (
    LineType,
    LineSection,
    UserConfiguration,
    RelayType,
    RelayTimeCharacteristic,
    Reactance,
    Transformer,
)

app = FastAPI(title="RZA Calculator", description="Расчёт уставок релейной защиты")

# === Пути к файлам ===
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
INDEX_FILE = TEMPLATES_DIR / "index.html"

print(f"BASE_DIR: {BASE_DIR}")
print(f"TEMPLATES_DIR: {TEMPLATES_DIR}")
print(f"INDEX_FILE exists: {INDEX_FILE.exists()}")

# Монтируем статику
if TEMPLATES_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(TEMPLATES_DIR)), name="static")

# === Pydantic модели для API ===
class SectionInput(BaseModel):
    section_number: int
    conductor_type: str | None = None
    conductor_length: float = 0.0
    cable_type: str | None = None
    cable_length: float = 0.0

class CalculationInput(BaseModel):
    sections: List[SectionInput]
    after_sections: List[SectionInput] = []
    u_nom: float = 6300.0
    relay_code: int = 6
    reactance_id: int | None = None
    reactance_mode: str = "MAX"
    transformer_code: int | None = None
    total_power_kw: float = 0.0
    i_work: float = 0.0
    manual_mto: float = 0.0  # K26
    manual_mtz: float = 0.0  # K33

# === API Endpoints ===

@app.get("/")
async def root():
    if not INDEX_FILE.exists():
        return {"error": "index.html not found", "path": str(INDEX_FILE)}
    return FileResponse(str(INDEX_FILE))

@app.get("/api/health")
async def health():
    return {"status": "ok", "templates": str(TEMPLATES_DIR)}

@app.get("/api/line-types")
async def get_line_types(category: str = None, db: Session = Depends(get_db)):
    """Получить типы линий из БД"""
    try:
        query = db.query(LineType)
        if category:
            query = query.filter(LineType.category == category)
        
        types = query.all()
        return {
            "success": True,
            "data": [{
                "id": t.id,
                "category": t.category,
                "type_name": t.type_name,
                "r_ohm_per_km": t.r_ohm_per_km,
                "x_ohm_per_km": t.x_ohm_per_km,
                "description": t.description
            } for t in types]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/relays")
async def get_relays(db: Session = Depends(get_db)):
    """Получить типы реле из БД (для K16)"""
    try:
        relays = db.query(RelayType).order_by(RelayType.relay_code).all()

        time_map = {
            t.relay_code: t.time_char_e
            for t in db.query(RelayTimeCharacteristic).all()
        }
        return {
            "success": True,
            "data": [
                {
                    "relay_code": r.relay_code,
                    "relay_name": r.relay_name,
                    "coef_l20": r.coef_l20,
                    "coef_l19": r.coef_l19,
                    "time_char_e": time_map.get(r.relay_code),
                }
                for r in relays
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/reactances")
async def get_reactances(db: Session = Depends(get_db)):
    """Справочник реактансов (ЭКСПЕРТ -> лист Реактансы)"""
    try:
        rows = db.query(Reactance).order_by(Reactance.reactance_code).all()
        return {
            "success": True,
            "data": [
                {
                    "id": r.id,
                    "code": r.reactance_code,
                    "name": r.name,
                    "z_max_ohm": r.z_max_ohm,
                    "z_min_ohm": r.z_min_ohm,
                }
                for r in rows
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/transformers")
async def get_transformers(db: Session = Depends(get_db)):
    """Справочник трансформаторов (ЭКСПЕРТ.xlsx -> лист 'Трансформаторы')"""
    try:
        rows = db.query(Transformer).order_by(Transformer.transformer_code).all()
        return {
            "success": True,
            "data": [
                {
                    "id": r.id,
                    "code": r.transformer_code,
                    "power_kva": r.power_kva,
                    "z_ohm": r.z_ohm,
                }
                for r in rows
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/calculate")
async def calculate(inputs: CalculationInput, db: Session = Depends(get_db)):
    """Расчёт уставок РЗА"""
    try:
        # Создаём объекты LineSection из входных данных
        sections = []
        for s in inputs.sections:
            section = LineSection(
                section_number=s.section_number,
                conductor_type=s.conductor_type,
                conductor_length=s.conductor_length,
                cable_type=s.cable_type,
                cable_length=s.cable_length
            )
            sections.append(section)

        after_sections: List[LineSection] = []
        for s in inputs.after_sections or []:
            after_sections.append(
                LineSection(
                    section_number=s.section_number,
                    conductor_type=s.conductor_type,
                    conductor_length=s.conductor_length,
                    cable_type=s.cable_type,
                    cable_length=s.cable_length,
                )
            )
        
        # Расчёт
        result = calculate_rza_settings(
            db,
            sections,
            inputs.u_nom,
            relay_code=inputs.relay_code,
            reactance_id=inputs.reactance_id,
            reactance_mode=inputs.reactance_mode,
            total_power_kw=inputs.total_power_kw,
            i_work=inputs.i_work,
            manual_mto=inputs.manual_mto,
            manual_mtz=inputs.manual_mtz,
            transformer_code=inputs.transformer_code,
            after_sections=after_sections,
        )
        chart_data = generate_chart_data(
            db,
            sections,
            inputs.u_nom,
            i_mto_setting=float(result["i_mto_setting"]),
            i_mtz_setting=float(result["i_mtz_setting"]),
            after_sections=after_sections,
            kch_mto_min=float(result["kch_mto_min"]),
            kch_mtz_min=float(result["kch_mtz_min"]),
            reactance_id=inputs.reactance_id,
            reactance_mode=inputs.reactance_mode,
            transformer_code=inputs.transformer_code,
        )
        
        return {
            "success": True,
            "calculation": result,
            "chart": chart_data
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/excel-data")
async def get_excel_data(db: Session = Depends(get_db)):
    """Получить данные из импортированных Excel файлов"""
    try:
        # Получаем ключевые ячейки из ЭТАЛОН
        return {
            "success": True,
            "data": {
                "k24": get_cell_value(db, "Расчет", "K24"),
                "k25": get_cell_value(db, "Расчет", "K25"),
                "k26": get_cell_value(db, "Расчет", "K26"),
                "k35": get_cell_value(db, "Расчет", "K35"),
                "e5": get_cell_value(db, "Расчет", "E5"),
                "f5": get_cell_value(db, "Расчет", "F5"),
                "d20": get_cell_value(db, "Расчет", "D20")
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)