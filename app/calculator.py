# app/calculator.py
from app.parser_excel import parse_excel_files
import pandas as pd
import numpy as np
from typing import List, Dict
import logging

class RZACalculator:
    def __init__(self, db_path: str = "rza_settings.db"):
        self.db_path = db_path
        self.parsed_formulas = []
    
    def process_excel_files(self, file_paths: List[str]) -> List[Dict]:
        """Обрабатывает Excel файлы и сохраняет формулы"""
        self.parsed_formulas = parse_excel_files(file_paths)
        return self.parsed_formulas
    
    def find_rza_formulas(self) -> List[Dict]:
        """Находит формулы, относящиеся к расчетам РЗА"""
        rza_formulas = []
        keywords = ['ток', 'уставк', 'время', 'срабатыван', 'защит']
        
        for formula_info in self.parsed_formulas:
            formula_lower = formula_info['formula'].lower()
            # Проверяем на ключевые слова или типичные формулы РЗА
            if any(keyword in formula_lower for keyword in keywords) or \
               any(op in formula_info['formula'] for op in ['*', '/', '+', '-']):
                rza_formulas.append(formula_info)
        
        return rza_formulas
    
    def calculate_overcurrent_protection(self, current_max: float, 
                                       k_n: float = 1.2, 
                                       k_r: float = 1.1, 
                                       k_z: float = 0.9) -> float:
        """Расчет уставки тока срабатывания МТЗ"""
        return (k_n * k_r * current_max) / k_z
