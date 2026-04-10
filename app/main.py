from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from app.database import get_db, engine
from app.db_migrate import ensure_reactance_crud_columns
from app.auth_utils import mint_token, require_staff_token, verify_password
from app.calculator import calculate_rza_settings, generate_chart_data, get_line_type, get_cell_value
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
load_dotenv(BASE_DIR / ".env")

security_bearer = HTTPBearer(auto_error=False)


def _staff_from_credentials(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Требуется вход Инженер или Админ")
    try:
        return require_staff_token(f"Bearer {credentials.credentials}")
    except PermissionError:
        raise HTTPException(status_code=401, detail="Недействительный или просроченный токен")


print(f"BASE_DIR: {BASE_DIR}")
print(f"TEMPLATES_DIR: {TEMPLATES_DIR}")
print(f"INDEX_FILE exists: {INDEX_FILE.exists()}")

# Монтируем статику
if TEMPLATES_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(TEMPLATES_DIR)), name="static")


@app.on_event("startup")
def _startup_migrate() -> None:
    try:
        ensure_reactance_crud_columns(engine)
    except Exception as e:
        print(f"DB migrate warning (reactances CRUD columns): {e}")


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
    object_description: str = ""
    u_nom: float = 6300.0
    relay_code: int = 6
    reactance_id: int | None = None
    reactance_mode: str = "MAX"
    transformer_code: int | None = None
    total_power_kw: float = 0.0
    i_work: float = 0.0
    manual_mto: float = 0.0  # K26
    manual_mtz: float = 0.0  # K33


class LoginInput(BaseModel):
    role: Literal["engineer", "admin"]
    password: str = Field(min_length=1)


class ReactanceCreateInput(BaseModel):
    reactance_code: int
    name: str = Field(min_length=1, max_length=255)
    z_max_ohm: float = Field(gt=0)
    z_min_ohm: float = Field(gt=0)


class ReactanceUpdateInput(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    z_max_ohm: Optional[float] = Field(None, gt=0)
    z_min_ohm: Optional[float] = Field(None, gt=0)
    is_active: Optional[bool] = None


def _reactance_to_dict(r: Reactance, include_inactive_fields: bool = True) -> dict:
    d = {
        "id": r.id,
        "code": r.reactance_code,
        "name": r.name,
        "z_max_ohm": r.z_max_ohm,
        "z_min_ohm": r.z_min_ohm,
    }
    if include_inactive_fields:
        d["is_active"] = getattr(r, "is_active", True)
        ua = getattr(r, "updated_at", None)
        d["updated_at"] = ua.isoformat() if ua else None
        d["updated_by"] = getattr(r, "updated_by", None)
    return d


# === API Endpoints ===

@app.get("/")
async def root():
    if not INDEX_FILE.exists():
        return {"error": "index.html not found", "path": str(INDEX_FILE)}
    return FileResponse(str(INDEX_FILE))

@app.get("/api/health")
async def health():
    return {"status": "ok", "templates": str(TEMPLATES_DIR)}


@app.post("/api/auth/login")
async def auth_login(body: LoginInput):
    if not verify_password(body.role, body.password):
        raise HTTPException(status_code=401, detail="Неверная роль или пароль")
    token = mint_token(body.role)
    return {"success": True, "role": body.role, "token": token}


@app.get("/api/auth/me")
async def auth_me(staff: dict = Depends(_staff_from_credentials)):
    return {"success": True, "role": staff.get("role")}


@app.get("/api/admin/reactances")
async def admin_list_reactances(
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
    include_inactive: bool = True,
):
    """Список реактансов для CRUD (Инженер/Админ). По умолчанию включая скрытые."""
    try:
        q = db.query(Reactance).order_by(Reactance.reactance_code)
        if not include_inactive:
            q = q.filter(Reactance.is_active == True)  # noqa: E712 — MS SQL: .is_(True) даёт недопустимое «IS 1»
        rows = q.all()
        return {"success": True, "data": [_reactance_to_dict(r) for r in rows]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/admin/reactances")
async def admin_create_reactance(
    body: ReactanceCreateInput,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    if body.z_max_ohm < body.z_min_ohm:
        raise HTTPException(status_code=400, detail="Zmax должно быть ≥ Zmin")
    dup = db.query(Reactance).filter(Reactance.reactance_code == body.reactance_code).first()
    if dup:
        raise HTTPException(status_code=409, detail=f"Код {body.reactance_code} уже занят")
    role = str(staff.get("role") or "engineer")
    now = datetime.utcnow()
    row = Reactance(
        reactance_code=body.reactance_code,
        name=body.name.strip(),
        z_max_ohm=float(body.z_max_ohm),
        z_min_ohm=float(body.z_min_ohm),
        is_active=True,
        updated_at=now,
        updated_by=role,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"success": True, "data": _reactance_to_dict(row)}


@app.put("/api/admin/reactances/{reactance_id}")
async def admin_update_reactance(
    reactance_id: int,
    body: ReactanceUpdateInput,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    row = db.query(Reactance).filter(Reactance.id == reactance_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    role = str(staff.get("role") or "engineer")
    if body.name is not None:
        row.name = body.name.strip()
    if body.z_max_ohm is not None:
        row.z_max_ohm = float(body.z_max_ohm)
    if body.z_min_ohm is not None:
        row.z_min_ohm = float(body.z_min_ohm)
    if body.is_active is not None:
        row.is_active = bool(body.is_active)
    if float(row.z_max_ohm) < float(row.z_min_ohm):
        raise HTTPException(status_code=400, detail="Zmax должно быть ≥ Zmin")
    row.updated_at = datetime.utcnow()
    row.updated_by = role
    db.commit()
    db.refresh(row)
    return {"success": True, "data": _reactance_to_dict(row)}


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
    """Справочник реактансов для расчёта: только активные (видны Мастеру)."""
    try:
        rows = (
            db.query(Reactance)
            .filter(Reactance.is_active == True)  # noqa: E712
            .order_by(Reactance.reactance_code)
            .all()
        )
        return {
            "success": True,
            "data": [_reactance_to_dict(r, include_inactive_fields=False) for r in rows],
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
        # Metadata for printing/telephonegram
        result["object_description"] = (inputs.object_description or "").strip()
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