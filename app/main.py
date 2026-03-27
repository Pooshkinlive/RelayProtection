# app/main.py
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
import os
from app.calculator import RZACalculator
from app.parser_excel import parse_excel_files, save_formulas_to_txt

# Настройки путей
INPUT_DIR = "data/input"
OUTPUT_DIR = "data/output"

class InputData(BaseModel):
    current_max: float
    k_n: float = 1.2
    k_r: float = 1.1
    k_z: float = 0.9

def create_app():
    app = FastAPI()
    rza_calc = RZACalculator()  # Локальная переменная внутри функции
    
    @app.get("/")
    async def root():
        return {"message": "RZA Calculator API"}

    @app.post("/calculate-overcurrent/")
    async def calc(data: InputData):
        result = rza_calc.calculate_overcurrent_protection(
            data.current_max,
            data.k_n,
            data.k_r,
            data.k_z
        )
        return {"setting": result}

    @app.post("/process-excel-files/")
    async def process_files():
        """Обрабатывает все Excel файлы в папке input"""
        file_paths = []
        for filename in os.listdir(INPUT_DIR):
            if filename.endswith(('.xls', '.xlsx')):
                file_paths.append(os.path.join(INPUT_DIR, filename))
        
        if not file_paths:
            return {"error": "No Excel files found in input directory"}
        
        # Парсим формулы
        formulas = parse_excel_files(file_paths)
        
        # Сохраняем в файл
        output_path = os.path.join(OUTPUT_DIR, "parsed_formulas.txt")
        save_formulas_to_txt(formulas, output_path)
        
        return {
            "message": f"Processed {len(formulas)} formulas",
            "output_file": output_path
        }
    
    return app

# Создаем экземпляр приложения
app = create_app()
