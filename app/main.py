from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Dict, Any, List

from app.database import get_db
from app.calculator import calculate_mto, calculate_mtz, get_excel_data as calc_get_excel_data

app = FastAPI(title="RZA Calculator")

# === Пуки к файлам ===
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
INDEX_FILE = TEMPLATES_DIR / "index.html"

print(f"📁 BASE_DIR: {BASE_DIR}")
print(f"📁 TEMPLATES_DIR: {TEMPLATES_DIR}")
print(f"📄 INDEX_FILE exists: {INDEX_FILE.exists()}")

# Монтируем статику
if TEMPLATES_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(TEMPLATES_DIR)), name="static")
else:
    print(f"⚠️ Папка templates не найдена: {TEMPLATES_DIR}")

@app.get("/")
async def root():
    if not INDEX_FILE.exists():
        return {
            "error": "index.html not found",
            "expected_path": str(INDEX_FILE),
            "templates_dir_exists": TEMPLATES_DIR.exists()
        }
    return FileResponse(str(INDEX_FILE))

@app.get("/api/health")
async def health():
    return {"status": "ok", "templates": str(TEMPLATES_DIR)}

@app.get("/api/excel-data")
async def get_excel_data(db: Session = Depends(get_db)):
    """Возвращает ключевые ячейки из ЭТАЛОН"""
    try:
        data = calc_get_excel_data(db)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/calculate")
async def calculate(inputs: Dict[str, float], db: Session = Depends(get_db)):
    """Основной расчёт МТО и МТЗ"""
    try:
        mto_result = calculate_mto(db, inputs)
        mtz_result = calculate_mtz(db, inputs)
        
        return {
            "success": True,
            "mto": mto_result,
            "mtz": mtz_result
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/parameters")
async def get_parameters(db: Session = Depends(get_db)):
    """Список всех параметров для ввода"""
    from app.models import InputParameter
    try:
        params = db.query(InputParameter).order_by(InputParameter.display_order).all()
        return {
            "success": True,
            "parameters": [{
                "code": p.param_code,
                "name": p.param_name,
                "unit": p.unit,
                "default_value": float(p.default_value) if p.default_value else None,
                "engineer_input": p.is_engineer_input
            } for p in params]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)