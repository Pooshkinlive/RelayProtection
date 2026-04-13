import json
from datetime import datetime, date
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pathlib import Path
from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from app.database import get_db, engine
from app.db_migrate import ensure_reactance_crud_columns, ensure_telephonegram_tables
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
    Telephonegram,
    TelephonegramDailyCounter,
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
    try:
        ensure_telephonegram_tables(engine)
    except Exception as e:
        print(f"DB migrate warning (telephonegrams): {e}")


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
    reactance_mode: str = "MAX"  # устарело: расчёт КЗ не зависит от режима; оставлено для совместимости API
    mto_kch_mode: Literal["backup", "main"] = "backup"  # backup = доп. защита (I2ф на с.ш.); main = основная (конец КЛ)
    transformer_code: int | None = None
    total_power_kw: float = 0.0
    i_work: float = 0.0
    manual_mto: float = 0.0  # K26
    manual_mtz: float = 0.0  # K33
    # Реквизиты для телефонограммы / ЗОЗЗ (не участвуют в расчёте КЗ и графика)
    manual_t_mto: Optional[float] = None
    manual_t_mtz: Optional[float] = None
    ct_primary_a: Optional[float] = None
    ct_secondary_a: Optional[float] = None
    manual_izzz_a: Optional[float] = None
    manual_t_izzz_s: Optional[float] = None
    ozz_action: Optional[str] = None  # "signal" | "trip"
    apv_time_s: Optional[float] = None
    apv_cycles: Optional[int] = None


class TelephonegramCreateInput(BaseModel):
    """Создание записи телефонограммы (номер авто по дате «от:», если telegram_no не задан)."""

    telegram_date: str = Field(..., min_length=1, description="Дата «от:», формат YYYY-MM-DD")
    telegram_no: Optional[int] = None
    manual_fields: Dict[str, Any] = Field(default_factory=dict)
    calc_input: Dict[str, Any] = Field(default_factory=dict)
    calc_snapshot: Dict[str, Any]


class TelephonegramUpdateInput(BaseModel):
    telegram_date: Optional[str] = Field(default=None)
    telegram_no: Optional[int] = Field(default=None)
    manual_fields: Optional[Dict[str, Any]] = Field(default=None)
    status: Optional[str] = Field(default=None)


class LoginInput(BaseModel):
    role: Literal["engineer", "admin"]
    password: str = Field(min_length=1)


class ReactanceCreateInput(BaseModel):
    reactance_code: int
    name: str = Field(min_length=1, max_length=255)
    z_max_ohm: Optional[float] = None
    z_min_ohm: Optional[float] = None
    z_a_max_ohm: Optional[float] = None
    z_a_min_ohm: Optional[float] = None


class ReactanceUpdateInput(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    z_max_ohm: Optional[float] = None
    z_min_ohm: Optional[float] = None
    z_a_max_ohm: Optional[float] = None
    z_a_min_ohm: Optional[float] = None
    is_active: Optional[bool] = None


def _reactance_row_usable_for_calc(r: Reactance) -> bool:
    from app.calculator import regime_emergency_available, regime_normal_available

    return regime_normal_available(r) or regime_emergency_available(r)


def _reactance_to_dict(r: Reactance, include_inactive_fields: bool = True) -> dict:
    d = {
        "id": r.id,
        "code": r.reactance_code,
        "name": r.name,
        "z_max_ohm": r.z_max_ohm,
        "z_min_ohm": r.z_min_ohm,
        "z_a_max_ohm": getattr(r, "z_a_max_ohm", None),
        "z_a_min_ohm": getattr(r, "z_a_min_ohm", None),
    }
    if include_inactive_fields:
        d["is_active"] = getattr(r, "is_active", True)
        ua = getattr(r, "updated_at", None)
        d["updated_at"] = ua.isoformat() if ua else None
        d["updated_by"] = getattr(r, "updated_by", None)
    return d


def _parse_telegram_date(s: Optional[str]) -> date:
    raw = (s or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="заполните дату в поле от:  ")
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты «от:», ожидается YYYY-MM-DD")


def _allocate_next_telegram_no(db: Session, d: date) -> int:
    """Номер внутри календарной даты «от:»; допускаются одинаковые номера в разные даты."""
    counter = (
        db.query(TelephonegramDailyCounter)
        .filter(TelephonegramDailyCounter.telegram_date == d)
        .with_for_update()
        .first()
    )
    if counter is None:
        try:
            with db.begin_nested():
                db.add(TelephonegramDailyCounter(telegram_date=d, last_no=0))
                db.flush()
        except IntegrityError:
            pass
        counter = (
            db.query(TelephonegramDailyCounter)
            .filter(TelephonegramDailyCounter.telegram_date == d)
            .with_for_update()
            .first()
        )
    if counter is None:
        raise HTTPException(status_code=500, detail="Не удалось создать счётчик номера телефонограммы")
    counter.last_no = int(counter.last_no or 0) + 1
    db.flush()
    return int(counter.last_no)


def _telephonegram_to_api_dict(r: Telephonegram) -> Dict[str, Any]:
    mf: Dict[str, Any] = {}
    if r.manual_fields_json:
        try:
            mf = json.loads(r.manual_fields_json)
        except Exception:
            mf = {}
    snap: Dict[str, Any] = {}
    if r.calc_snapshot_json:
        try:
            snap = json.loads(r.calc_snapshot_json)
        except Exception:
            snap = {}
    cin: Dict[str, Any] = {}
    if r.calc_input_json:
        try:
            cin = json.loads(r.calc_input_json)
        except Exception:
            cin = {}
    return {
        "id": int(r.id),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "created_by_role": r.created_by_role,
        "telegram_no": int(r.telegram_no),
        "telegram_date": r.telegram_date.isoformat() if r.telegram_date else None,
        "manual_fields": mf,
        "calc_input": cin,
        "calc_snapshot": snap,
        "status": r.status,
        "object_description": snap.get("object_description"),
    }


# === API Endpoints ===

@app.get("/")
async def root():
    if not INDEX_FILE.exists():
        return {"error": "index.html not found", "path": str(INDEX_FILE)}
    return FileResponse(str(INDEX_FILE))

@app.get("/api/health")
async def health():
    return {"status": "ok", "templates": str(TEMPLATES_DIR)}


@app.get("/api/health/db")
async def health_db(db: Session = Depends(get_db)):
    """Лёгкая проверка доступности SQL Server / БД."""
    try:
        db.query(LineType).limit(1).first()
        return {"success": True, "connected": True}
    except Exception as e:
        return {"success": True, "connected": False, "error": str(e)}


@app.post("/api/auth/login")
async def auth_login(body: LoginInput):
    if not verify_password(body.role, body.password):
        raise HTTPException(status_code=401, detail="Неверная роль или пароль")
    token = mint_token(body.role)
    return {"success": True, "role": body.role, "token": token}


@app.get("/api/auth/me")
async def auth_me(staff: dict = Depends(_staff_from_credentials)):
    return {"success": True, "role": staff.get("role")}


@app.post("/api/telephonegrams")
async def telephonegram_create(
    body: TelephonegramCreateInput,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    dd = _parse_telegram_date(body.telegram_date)
    if not body.calc_snapshot:
        raise HTTPException(status_code=400, detail="Нет данных расчёта (calc_snapshot пустой)")
    role = str(staff.get("role") or "engineer")
    if body.telegram_no is None:
        no = _allocate_next_telegram_no(db, dd)
    else:
        no = int(body.telegram_no)
    row = Telephonegram(
        created_by_role=role,
        telegram_no=no,
        telegram_date=dd,
        manual_fields_json=json.dumps(body.manual_fields or {}, ensure_ascii=False),
        calc_input_json=json.dumps(body.calc_input or {}, ensure_ascii=False),
        calc_snapshot_json=json.dumps(body.calc_snapshot or {}, ensure_ascii=False),
        status="draft",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"success": True, "data": _telephonegram_to_api_dict(row)}


@app.get("/api/telephonegrams")
async def telephonegram_list(
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
    limit: int = 50,
    offset: int = 0,
):
    lim = max(1, min(int(limit or 50), 200))
    off = max(0, int(offset or 0))
    q = (
        db.query(Telephonegram)
        .order_by(
            Telephonegram.telegram_date.desc(),
            Telephonegram.telegram_no.desc(),
            Telephonegram.id.desc(),
        )
        .offset(off)
        .limit(lim)
    )
    rows = q.all()
    return {"success": True, "data": [_telephonegram_to_api_dict(r) for r in rows]}


@app.get("/api/telephonegrams/{row_id}")
async def telephonegram_get(
    row_id: int,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    row = db.query(Telephonegram).filter(Telephonegram.id == row_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return {"success": True, "data": _telephonegram_to_api_dict(row)}


@app.put("/api/telephonegrams/{row_id}")
async def telephonegram_update(
    row_id: int,
    body: TelephonegramUpdateInput,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    row = db.query(Telephonegram).filter(Telephonegram.id == row_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    upd = body.model_dump(exclude_unset=True)
    if "telegram_date" in upd and upd["telegram_date"] is not None:
        row.telegram_date = _parse_telegram_date(str(upd["telegram_date"]))
    if "telegram_no" in upd and upd["telegram_no"] is not None:
        row.telegram_no = int(upd["telegram_no"])
    if "manual_fields" in upd and upd["manual_fields"] is not None:
        row.manual_fields_json = json.dumps(upd["manual_fields"], ensure_ascii=False)
    if "status" in upd and upd["status"] is not None:
        row.status = str(upd["status"]).strip()[:20] or row.status
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {"success": True, "data": _telephonegram_to_api_dict(row)}


@app.delete("/api/telephonegrams/{row_id}")
async def telephonegram_delete(
    row_id: int,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    if str(staff.get("role") or "") != "admin":
        raise HTTPException(status_code=403, detail="Удаление доступно только роли admin")
    row = db.query(Telephonegram).filter(Telephonegram.id == row_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    db.delete(row)
    db.commit()
    return {"success": True}


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
    dup = db.query(Reactance).filter(Reactance.reactance_code == body.reactance_code).first()
    if dup:
        raise HTTPException(status_code=409, detail=f"Код {body.reactance_code} уже занят")
    has_n = body.z_max_ohm is not None and body.z_min_ohm is not None
    has_a = (
        body.z_a_max_ohm is not None
        and body.z_a_min_ohm is not None
        and float(body.z_a_max_ohm) > 0
        and float(body.z_a_min_ohm) > 0
    )
    if not has_n and not has_a:
        raise HTTPException(
            status_code=400,
            detail="Нужны оба Z норм. режима (C и D) или оба Z авар. режима (J и K) > 0",
        )
    role = str(staff.get("role") or "engineer")
    now = datetime.utcnow()
    row = Reactance(
        reactance_code=body.reactance_code,
        name=body.name.strip(),
        z_max_ohm=float(body.z_max_ohm) if has_n else None,
        z_min_ohm=float(body.z_min_ohm) if has_n else None,
        z_a_max_ohm=float(body.z_a_max_ohm) if has_a else None,
        z_a_min_ohm=float(body.z_a_min_ohm) if has_a else None,
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
    upd = body.model_dump(exclude_unset=True)
    if "name" in upd and upd["name"] is not None:
        row.name = str(upd["name"]).strip()
    if "z_max_ohm" in upd:
        row.z_max_ohm = float(upd["z_max_ohm"]) if upd["z_max_ohm"] is not None else None
    if "z_min_ohm" in upd:
        row.z_min_ohm = float(upd["z_min_ohm"]) if upd["z_min_ohm"] is not None else None
    if "z_a_max_ohm" in upd:
        row.z_a_max_ohm = float(upd["z_a_max_ohm"]) if upd["z_a_max_ohm"] is not None else None
    if "z_a_min_ohm" in upd:
        row.z_a_min_ohm = float(upd["z_a_min_ohm"]) if upd["z_a_min_ohm"] is not None else None
    if "is_active" in upd and upd["is_active"] is not None:
        row.is_active = bool(upd["is_active"])
    row.updated_at = datetime.utcnow()
    row.updated_by = role
    if not _reactance_row_usable_for_calc(row):
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Должен остаться хотя бы один режим: пара C/D или пара J/K > 0",
        )
    db.commit()
    db.refresh(row)
    return {"success": True, "data": _reactance_to_dict(row)}


# --- Админ: провода/кабели (line_types) ---


class LineTypeCreateInput(BaseModel):
    category: str = Field(min_length=1, max_length=50)
    type_name: str = Field(min_length=1, max_length=100)
    r_ohm_per_km: float
    x_ohm_per_km: float
    description: Optional[str] = None


class LineTypeUpdateInput(BaseModel):
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    type_name: Optional[str] = Field(None, min_length=1, max_length=100)
    r_ohm_per_km: Optional[float] = None
    x_ohm_per_km: Optional[float] = None
    description: Optional[str] = None


def _line_type_to_dict(t: LineType) -> dict:
    return {
        "id": t.id,
        "category": t.category,
        "type_name": t.type_name,
        "r_ohm_per_km": t.r_ohm_per_km,
        "x_ohm_per_km": t.x_ohm_per_km,
        "description": t.description,
    }


@app.get("/api/admin/line-types")
async def admin_list_line_types(
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
    category: Optional[str] = None,
):
    try:
        q = db.query(LineType)
        if category:
            q = q.filter(LineType.category == category)
        rows = q.order_by(LineType.category, LineType.type_name).all()
        return {"success": True, "data": [_line_type_to_dict(t) for t in rows]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/admin/line-types")
async def admin_create_line_type(
    body: LineTypeCreateInput,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    cat = body.category.strip()
    name = body.type_name.strip()
    dup = (
        db.query(LineType)
        .filter(LineType.category == cat, LineType.type_name == name)
        .first()
    )
    if dup:
        raise HTTPException(status_code=409, detail=f"Тип «{name}» в категории «{cat}» уже есть")
    row = LineType(
        category=cat,
        type_name=name,
        r_ohm_per_km=float(body.r_ohm_per_km),
        x_ohm_per_km=float(body.x_ohm_per_km),
        description=(body.description or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"success": True, "data": _line_type_to_dict(row)}


@app.put("/api/admin/line-types/{line_type_id}")
async def admin_update_line_type(
    line_type_id: int,
    body: LineTypeUpdateInput,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    row = db.query(LineType).filter(LineType.id == line_type_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    upd = body.model_dump(exclude_unset=True)
    new_cat = row.category
    new_name = row.type_name
    if "category" in upd and upd["category"] is not None:
        new_cat = str(upd["category"]).strip()
        row.category = new_cat
    if "type_name" in upd and upd["type_name"] is not None:
        new_name = str(upd["type_name"]).strip()
        row.type_name = new_name
    if "r_ohm_per_km" in upd and upd["r_ohm_per_km"] is not None:
        row.r_ohm_per_km = float(upd["r_ohm_per_km"])
    if "x_ohm_per_km" in upd and upd["x_ohm_per_km"] is not None:
        row.x_ohm_per_km = float(upd["x_ohm_per_km"])
    if "description" in upd:
        row.description = (str(upd["description"]).strip() if upd["description"] else "") or None
    oth = (
        db.query(LineType)
        .filter(
            LineType.category == new_cat,
            LineType.type_name == new_name,
            LineType.id != line_type_id,
        )
        .first()
    )
    if oth:
        db.rollback()
        raise HTTPException(status_code=409, detail="Дубликат категория + тип")
    db.commit()
    db.refresh(row)
    return {"success": True, "data": _line_type_to_dict(row)}


# --- Админ: трансформаторы ---


class TransformerCreateInput(BaseModel):
    transformer_code: int
    power_kva: float
    z_ohm: float


class TransformerUpdateInput(BaseModel):
    transformer_code: Optional[int] = None
    power_kva: Optional[float] = None
    z_ohm: Optional[float] = None


def _transformer_to_dict(t: Transformer) -> dict:
    return {
        "id": t.id,
        "code": t.transformer_code,
        "power_kva": t.power_kva,
        "z_ohm": t.z_ohm,
    }


@app.get("/api/admin/transformers")
async def admin_list_transformers(
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    try:
        rows = db.query(Transformer).order_by(Transformer.transformer_code).all()
        return {"success": True, "data": [_transformer_to_dict(t) for t in rows]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/admin/transformers")
async def admin_create_transformer(
    body: TransformerCreateInput,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    dup = (
        db.query(Transformer)
        .filter(Transformer.transformer_code == body.transformer_code)
        .first()
    )
    if dup:
        raise HTTPException(status_code=409, detail=f"Код {body.transformer_code} уже занят")
    row = Transformer(
        transformer_code=int(body.transformer_code),
        power_kva=float(body.power_kva),
        z_ohm=float(body.z_ohm),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"success": True, "data": _transformer_to_dict(row)}


@app.put("/api/admin/transformers/{transformer_row_id}")
async def admin_update_transformer(
    transformer_row_id: int,
    body: TransformerUpdateInput,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    row = db.query(Transformer).filter(Transformer.id == transformer_row_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    upd = body.model_dump(exclude_unset=True)
    new_code = row.transformer_code
    if "transformer_code" in upd and upd["transformer_code"] is not None:
        new_code = int(upd["transformer_code"])
        oth = (
            db.query(Transformer)
            .filter(
                Transformer.transformer_code == new_code,
                Transformer.id != transformer_row_id,
            )
            .first()
        )
        if oth:
            raise HTTPException(status_code=409, detail=f"Код {new_code} уже занят")
        row.transformer_code = new_code
    if "power_kva" in upd and upd["power_kva"] is not None:
        row.power_kva = float(upd["power_kva"])
    if "z_ohm" in upd and upd["z_ohm"] is not None:
        row.z_ohm = float(upd["z_ohm"])
    db.commit()
    db.refresh(row)
    return {"success": True, "data": _transformer_to_dict(row)}


# --- Админ: реле ---


class RelayAdminCreateInput(BaseModel):
    relay_code: int
    relay_name: str = Field(min_length=1, max_length=255)
    coef_l20: float
    coef_l19: float
    time_char_e: Optional[str] = Field(None, max_length=500)


class RelayAdminUpdateInput(BaseModel):
    relay_name: Optional[str] = Field(None, min_length=1, max_length=255)
    coef_l20: Optional[float] = None
    coef_l19: Optional[float] = None
    time_char_e: Optional[str] = Field(None, max_length=500)


def _relay_admin_row_dict(r: RelayType, time_char: Optional[str]) -> dict:
    return {
        "id": r.id,
        "relay_code": r.relay_code,
        "relay_name": r.relay_name,
        "coef_l20": r.coef_l20,
        "coef_l19": r.coef_l19,
        "time_char_e": time_char,
    }


def _get_time_char_map(db: Session) -> Dict[int, Optional[str]]:
    return {
        t.relay_code: t.time_char_e
        for t in db.query(RelayTimeCharacteristic).all()
    }


@app.get("/api/admin/relays")
async def admin_list_relays(
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    try:
        rows = db.query(RelayType).order_by(RelayType.relay_code).all()
        tm = _get_time_char_map(db)
        return {
            "success": True,
            "data": [_relay_admin_row_dict(r, tm.get(r.relay_code)) for r in rows],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/admin/relays")
async def admin_create_relay(
    body: RelayAdminCreateInput,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    dup = db.query(RelayType).filter(RelayType.relay_code == body.relay_code).first()
    if dup:
        raise HTTPException(status_code=409, detail=f"Код реле {body.relay_code} уже занят")
    row = RelayType(
        relay_code=int(body.relay_code),
        relay_name=body.relay_name.strip(),
        coef_l20=float(body.coef_l20),
        coef_l19=float(body.coef_l19),
    )
    db.add(row)
    db.flush()
    if body.time_char_e is not None and str(body.time_char_e).strip():
        db.add(
            RelayTimeCharacteristic(
                relay_code=int(body.relay_code),
                time_char_e=str(body.time_char_e).strip()[:500],
            )
        )
    db.commit()
    db.refresh(row)
    tm = _get_time_char_map(db)
    return {"success": True, "data": _relay_admin_row_dict(row, tm.get(row.relay_code))}


@app.put("/api/admin/relays/{relay_row_id}")
async def admin_update_relay(
    relay_row_id: int,
    body: RelayAdminUpdateInput,
    db: Session = Depends(get_db),
    staff: dict = Depends(_staff_from_credentials),
):
    row = db.query(RelayType).filter(RelayType.id == relay_row_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    upd = body.model_dump(exclude_unset=True)
    if "relay_name" in upd and upd["relay_name"] is not None:
        row.relay_name = str(upd["relay_name"]).strip()
    if "coef_l20" in upd and upd["coef_l20"] is not None:
        row.coef_l20 = float(upd["coef_l20"])
    if "coef_l19" in upd and upd["coef_l19"] is not None:
        row.coef_l19 = float(upd["coef_l19"])
    rc = row.relay_code
    if "time_char_e" in upd:
        tc_row = (
            db.query(RelayTimeCharacteristic)
            .filter(RelayTimeCharacteristic.relay_code == rc)
            .first()
        )
        val = upd["time_char_e"]
        s = str(val).strip()[:500] if val is not None and str(val).strip() else None
        if s:
            if tc_row:
                tc_row.time_char_e = s
            else:
                db.add(RelayTimeCharacteristic(relay_code=rc, time_char_e=s))
        elif tc_row:
            db.delete(tc_row)
    db.commit()
    db.refresh(row)
    tm = _get_time_char_map(db)
    return {"success": True, "data": _relay_admin_row_dict(row, tm.get(rc))}


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
        usable = [r for r in rows if _reactance_row_usable_for_calc(r)]
        return {
            "success": True,
            "data": [_reactance_to_dict(r, include_inactive_fields=False) for r in usable],
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
            mto_kch_mode=inputs.mto_kch_mode,
        )
        # Metadata for printing/telephonegram
        result["object_description"] = (inputs.object_description or "").strip()
        result["relay_form"] = {
            "t_mto_s": inputs.manual_t_mto,
            "t_mtz_s": inputs.manual_t_mtz,
            "ct_primary_a": inputs.ct_primary_a,
            "ct_secondary_a": inputs.ct_secondary_a,
            "izzz_pickup_a": inputs.manual_izzz_a,
            "t_izzz_s": inputs.manual_t_izzz_s,
            "ozz_action": (inputs.ozz_action or "").strip() or None,
            "apv_time_s": inputs.apv_time_s,
            "apv_cycles": inputs.apv_cycles,
        }
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