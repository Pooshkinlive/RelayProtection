# -*- coding: utf-8 -*-
"""
RZA Calculator - Backend API
Калькулятор уставок релейной защиты и автоматики
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
import json

from app.database import get_db
from app.models import Workbook, Sheet, Cell, InputParameter, CalculationResult
from pydantic import BaseModel, Field


# ============================================================================
# МОДЕЛИ ДАННЫХ PYDANTIC
# ============================================================================

class RZAInput(BaseModel):
    """Входные параметры для расчета уставок"""
    u_nom: Optional[float] = Field(None, description="Номинальное напряжение, кВ", ge=0.4, le=115)
    i_load_max: Optional[float] = Field(None, description="Максимальный ток нагрузки, А", ge=0)
    i_kz_max_3: Optional[float] = Field(None, description="Ток 3-фазного КЗ, А", ge=0)
    i_kz_min_2: Optional[float] = Field(None, description="Ток 2-фазного КЗ, А", ge=0)
    l_line: Optional[float] = Field(None, description="Длина линии, км", ge=0)
    k_n: float = Field(default=1.2, description="Коэффициент надежности", ge=1.0, le=1.5)
    k_v: float = Field(default=0.85, description="Коэффициент возврата", ge=0.8, le=0.95)
    k_ot: float = Field(default=1.0, description="Коэффициент отстройки", ge=1.0, le=1.3)

    class Config:
        json_schema_extra = {
            "example": {
                "u_nom": 6.3,
                "i_load_max": 100,
                "i_kz_max_3": 1000,
                "k_n": 1.2,
                "k_v": 0.85,
                "k_ot": 1.0
            }
        }


class RZAResult(BaseModel):
    """Результат расчета уставки"""
    setting_value: float
    unit: str
    formula_used: str
    inputs: dict


class WorkbookInfo(BaseModel):
    """Информация о книге Excel"""
    id: int
    filename: str
    imported_at: str


class SheetInfo(BaseModel):
    """Информация о листе"""
    id: int
    sheet_name: str


class CellInfo(BaseModel):
    """Информация о ячейке"""
    id: int
    address: str
    formula: Optional[str]
    value: Optional[str]
    data_type: str


class ParameterInfo(BaseModel):
    """Информация о параметре"""
    code: str
    name: str
    description: Optional[str]
    unit: Optional[str]
    default_value: Optional[float]
    min_value: Optional[float]
    max_value: Optional[float]
    required: bool


class StatsInfo(BaseModel):
    """Статистика базы данных"""
    workbooks: int
    sheets: int
    cells: int


# ============================================================================
# СОЗДАНИЕ ПРИЛОЖЕНИЯ
# ============================================================================

def create_app() -> FastAPI:
    """Factory function для создания FastAPI приложения"""
    
    app = FastAPI(
        title="RZA Calculator",
        description="Система расчета уставок релейной защиты и автоматики",
        version="1.0.0",
        root_path="/"
    )
    
    # ========================================================================
    # НАСТРОЙКА CORS
    # ========================================================================
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Для продакшена укажите конкретные домены
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # ========================================================================
    # СТАТИЧЕСКИЕ ФАЙЛЫ
    # ========================================================================
    app.mount("/static", StaticFiles(directory="templates"), name="static")
    
    # ========================================================================
    # API ENDPOINTS
    # ========================================================================
    
    @app.get("/", tags=["Main"])
    async def root():
        """Главная страница - веб-интерфейс калькулятора"""
        return FileResponse("templates/index.html")
    
    @app.get("/api/stats", response_model=StatsInfo, tags=["API"])
    async def get_stats(db: Session = Depends(get_db)):
        """Получить статистику по базе данных"""
        result = db.execute(text("""
            SELECT 
                COUNT(DISTINCT w.id) as workbooks,
                COUNT(DISTINCT s.id) as sheets,
                COUNT(c.id) as cells
            FROM workbooks w
            JOIN sheets s ON w.id = s.workbook_id
            JOIN cells c ON s.id = c.sheet_id
        """)).fetchone()
        
        return {
            "workbooks": result.workbooks,
            "sheets": result.sheets,
            "cells": result.cells
        }
    
    @app.get("/api/workbooks", response_model=List[WorkbookInfo], tags=["Excel"])
    async def get_workbooks(db: Session = Depends(get_db)):
        """Получить список импортированных Excel файлов"""
        workbooks = db.query(Workbook).filter(Workbook.is_active == True).all()
        return [
            {
                "id": w.id,
                "filename": w.filename,
                "imported_at": w.imported_at.isoformat() if w.imported_at else None
            }
            for w in workbooks
        ]
    
    @app.get("/api/sheets/{workbook_id}", response_model=List[SheetInfo], tags=["Excel"])
    async def get_sheets(workbook_id: int, db: Session = Depends(get_db)):
        """Получить листы указанной книги"""
        sheets = db.query(Sheet).filter(Sheet.workbook_id == workbook_id).all()
        return [{"id": s.id, "sheet_name": s.sheet_name} for s in sheets]
    
    @app.get("/api/cells/{sheet_id}", response_model=List[CellInfo], tags=["Excel"])
    async def get_cells(sheet_id: int, db: Session = Depends(get_db)):
        """Получить ячейки с формулами указанного листа"""
        cells = db.query(Cell).filter(Cell.sheet_id == sheet_id).all()
        return [
            {
                "id": c.id,
                "address": c.address,
                "formula": c.formula,
                "value": str(float(c.value_numeric)) if c.value_numeric else c.value_text,
                "data_type": c.data_type
            }
            for c in cells
        ]
    
    @app.get("/api/parameters", response_model=List[ParameterInfo], tags=["Parameters"])
    async def get_parameters(db: Session = Depends(get_db)):
        """Получить список входных параметров для расчетов"""
        params = db.query(InputParameter).order_by(InputParameter.display_order).all()
        return [
            {
                "code": p.param_code,
                "name": p.param_name,
                "description": p.param_description,
                "unit": p.unit,
                "default_value": float(p.default_value) if p.default_value else None,
                "min_value": float(p.min_value) if p.min_value else None,
                "max_value": float(p.max_value) if p.max_value else None,
                "required": p.is_required
            }
            for p in params
        ]
    
    @app.post("/api/calculate/mto", response_model=RZAResult, tags=["Calculations"])
    async def calculate_mto(inputs: RZAInput, db: Session = Depends(get_db)):
        """
        Расчет МТО (Максимальная Токовая Отсечка)
        
        Формула: I_mto = k_n × I_kz_max / k_ot
        """
        if not inputs.i_kz_max_3:
            raise HTTPException(
                status_code=400,
                detail="Необходим параметр i_kz_max_3 (ток 3-фазного КЗ)"
            )
        
        # Расчет по формуле
        result_value = inputs.k_n * inputs.i_kz_max_3 / inputs.k_ot
        
        # Сохранение в историю расчетов
        calc = CalculationResult(
            calculation_type="MTO",
            input_params_json=json.dumps(inputs.model_dump(), ensure_ascii=False),
            result_value=result_value,
            result_unit="А"
        )
        db.add(calc)
        db.commit()
        
        return {
            "setting_value": round(result_value, 2),
            "unit": "А",
            "formula_used": "I_mto = k_n × I_kz_max / k_ot",
            "inputs": inputs.model_dump()
        }
    
    @app.post("/api/calculate/mtz", response_model=RZAResult, tags=["Calculations"])
    async def calculate_mtz(inputs: RZAInput, db: Session = Depends(get_db)):
        """
        Расчет МТЗ (Максимальная Токовая Защита)
        
        Формула: I_mtz = k_n × I_load / k_v
        """
        if not inputs.i_load_max:
            raise HTTPException(
                status_code=400,
                detail="Необходим параметр i_load_max (ток нагрузки)"
            )
        
        # Расчет по формуле
        result_value = inputs.k_n * inputs.i_load_max / inputs.k_v
        
        # Сохранение в историю расчетов
        calc = CalculationResult(
            calculation_type="MTZ",
            input_params_json=json.dumps(inputs.model_dump(), ensure_ascii=False),
            result_value=result_value,
            result_unit="А"
        )
        db.add(calc)
        db.commit()
        
        return {
            "setting_value": round(result_value, 2),
            "unit": "А",
            "formula_used": "I_mtz = k_n × I_load / k_v",
            "inputs": inputs.model_dump()
        }
    
    @app.get("/health", tags=["System"])
    async def health_check():
        """Проверка работоспособности API"""
        return {"status": "ok", "service": "RZA Calculator API"}
    
    @app.get("/api/docs/info", tags=["System"])
    async def api_info():
        """Информация о API"""
        return {
            "title": "RZA Calculator API",
            "version": "1.0.0",
            "description": "Система расчета уставок релейной защиты",
            "endpoints": {
                "calculations": ["/api/calculate/mto", "/api/calculate/mtz"],
                "data": ["/api/workbooks", "/api/sheets", "/api/cells", "/api/parameters"],
                "system": ["/health", "/api/stats", "/api/docs/info"]
            }
        }
    
    return app


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )