import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import LineType, Base

DATABASE_URL = "mssql+pyodbc:///?odbc_connect=DRIVER={ODBC Driver 18 for SQL Server};SERVER=MSI-ALEXNAB\\SQLEXPRESS;DATABASE=RZA_Calculator;Trusted_Connection=yes;TrustServerCertificate=yes"

engine = create_engine(DATABASE_URL)

# ============================================================================
# ДАННЫЕ ИЗ ЭКСПЕРТ.xlsx - ЛИСТ "ПРОВОДА"
# ============================================================================
conductors = [
    {"type_name": "R-Al-25", "r": 1.140, "x": 0.400},
    {"type_name": "R-Al-35", "r": 0.830, "x": 0.400},
    {"type_name": "R-Al-50", "r": 0.576, "x": 0.400},
    {"type_name": "R-Al-70", "r": 0.412, "x": 0.400},
    {"type_name": "R-Al-95", "r": 0.308, "x": 0.400},
    {"type_name": "R-Al-120", "r": 0.246, "x": 0.400},
    {"type_name": "R-Al-150", "r": 0.194, "x": 0.400},
    {"type_name": "R-Al-185", "r": 0.170, "x": 0.400},
    {"type_name": "R-Al-240", "r": 0.131, "x": 0.400},
    {"type_name": "R-Alct-25", "r": 1.146, "x": 0.400},
    {"type_name": "R-Alct-35", "r": 0.773, "x": 0.400},
    {"type_name": "R-Alct-50", "r": 0.592, "x": 0.400},
    {"type_name": "R-Alct-70", "r": 0.420, "x": 0.400},
    {"type_name": "R-Alct-95", "r": 0.314, "x": 0.400},
    {"type_name": "R-Alct-120", "r": 0.249, "x": 0.400},
    {"type_name": "R-Alct-150", "r": 0.195, "x": 0.400},
    {"type_name": "R-Alct-185", "r": 0.159, "x": 0.400},
    {"type_name": "R-Alct-240", "r": 0.131, "x": 0.400},
    {"type_name": "R-Alct-400", "r": 0.073, "x": 0.400},
    {"type_name": "R-Alct-500", "r": 0.060, "x": 0.400},
    {"type_name": "СИП-3-50", "r": 0.720, "x": 0.299},
    {"type_name": "СИП-3-70", "r": 0.493, "x": 0.291},
    {"type_name": "СИП-3-95", "r": 0.363, "x": 0.284},
    {"type_name": "СИП-3-120", "r": 0.288, "x": 0.278},
    {"type_name": "СИП-3-150", "r": 0.236, "x": 0.273},
]

# ============================================================================
# ДАННЫЕ ИЗ ЭКСПЕРТ.xlsx - ЛИСТ "КАБЕЛИ" (ПОЛНЫЙ СПИСОК)
# Источник: Full_System_Logic.txt, ячейки C2-C67
# ============================================================================
cables = [
    # ==================== 1 КАБЕЛЬ АЛЮМИНИЙ ====================
    {"type_name": "К(Al)10", "r": 3.100, "x": 0.110},
    {"type_name": "К(Al)16", "r": 1.940, "x": 0.102},
    {"type_name": "К(Al)25", "r": 1.240, "x": 0.095},
    {"type_name": "К(Al)35", "r": 0.890, "x": 0.087},
    {"type_name": "К(Al)50", "r": 0.620, "x": 0.083},
    {"type_name": "К(Al)70", "r": 0.443, "x": 0.078},
    {"type_name": "К(Al)95", "r": 0.326, "x": 0.076},
    {"type_name": "К(Al)120", "r": 0.258, "x": 0.073},
    {"type_name": "К(Al)150", "r": 0.206, "x": 0.074},
    {"type_name": "К(Al)185", "r": 0.167, "x": 0.073},
    {"type_name": "К(Al)240", "r": 0.129, "x": 0.071},
    
    # ==================== 1 КАБЕЛЬ МЕДЬ ====================
    {"type_name": "К(Cu)10", "r": 1.840, "x": 0.110},
    {"type_name": "К(Cu)16", "r": 1.150, "x": 0.102},
    {"type_name": "К(Cu)25", "r": 0.740, "x": 0.091},
    {"type_name": "К(Cu)35", "r": 0.520, "x": 0.087},
    {"type_name": "К(Cu)50", "r": 0.370, "x": 0.083},
    {"type_name": "К(Cu)70", "r": 0.260, "x": 0.080},
    {"type_name": "К(Cu)95", "r": 0.194, "x": 0.078},
    {"type_name": "К(Cu)120", "r": 0.153, "x": 0.076},
    {"type_name": "К(Cu)150", "r": 0.123, "x": 0.074},
    {"type_name": "К(Cu)185", "r": 0.099, "x": 0.073},
    {"type_name": "К(Cu)240", "r": 0.077, "x": 0.071},
    
    # ==================== 2 ПАРАЛЛЕЛЬНЫХ КАБЕЛЯ АЛЮМИНИЙ ====================
    {"type_name": "2К(Al)10", "r": 1.550, "x": 0.055},
    {"type_name": "2К(Al)16", "r": 0.970, "x": 0.051},
    {"type_name": "2К(Al)25", "r": 0.620, "x": 0.0475},
    {"type_name": "2К(Al)35", "r": 0.445, "x": 0.0435},
    {"type_name": "2К(Al)50", "r": 0.310, "x": 0.0415},
    {"type_name": "2К(Al)70", "r": 0.2215, "x": 0.039},
    {"type_name": "2К(Al)95", "r": 0.163, "x": 0.039},
    {"type_name": "2К(Al)120", "r": 0.129, "x": 0.038},
    {"type_name": "2К(Al)150", "r": 0.103, "x": 0.037},
    {"type_name": "2К(Al)185", "r": 0.0835, "x": 0.0365},
    {"type_name": "2К(Al)240", "r": 0.0645, "x": 0.0355},
    
    # ==================== 2 ПАРАЛЛЕЛЬНЫХ КАБЕЛЯ МЕДЬ ====================
    {"type_name": "2К(Cu)10", "r": 0.920, "x": 0.055},
    {"type_name": "2К(Cu)16", "r": 0.575, "x": 0.051},
    {"type_name": "2К(Cu)25", "r": 0.370, "x": 0.0455},
    {"type_name": "2К(Cu)35", "r": 0.260, "x": 0.0435},
    {"type_name": "2К(Cu)50", "r": 0.185, "x": 0.0415},
    {"type_name": "2К(Cu)70", "r": 0.130, "x": 0.040},
    {"type_name": "2К(Cu)95", "r": 0.097, "x": 0.039},
    {"type_name": "2К(Cu)120", "r": 0.0765, "x": 0.038},
    {"type_name": "2К(Cu)150", "r": 0.0615, "x": 0.037},
    {"type_name": "2К(Cu)185", "r": 0.0495, "x": 0.0365},
    {"type_name": "2К(Cu)240", "r": 0.0385, "x": 0.0355},
    
    # ==================== 3 ПАРАЛЛЕЛЬНЫХ КАБЕЛЯ АЛЮМИНИЙ ====================
    {"type_name": "3К(Al)10", "r": 1.033, "x": 0.0367},
    {"type_name": "3К(Al)16", "r": 0.647, "x": 0.034},
    {"type_name": "3К(Al)25", "r": 0.413, "x": 0.0317},
    {"type_name": "3К(Al)35", "r": 0.297, "x": 0.029},
    {"type_name": "3К(Al)50", "r": 0.207, "x": 0.0277},
    {"type_name": "3К(Al)70", "r": 0.1477, "x": 0.026},
    {"type_name": "3К(Al)95", "r": 0.1087, "x": 0.026},
    {"type_name": "3К(Al)120", "r": 0.086, "x": 0.0253},
    {"type_name": "3К(Al)150", "r": 0.0687, "x": 0.0247},
    {"type_name": "3К(Al)185", "r": 0.0557, "x": 0.0243},
    {"type_name": "3К(Al)240", "r": 0.043, "x": 0.0237},
    
    # ==================== 3 ПАРАЛЛЕЛЬНЫХ КАБЕЛЯ МЕДЬ ====================
    {"type_name": "3К(Cu)10", "r": 0.613, "x": 0.0367},
    {"type_name": "3К(Cu)16", "r": 0.383, "x": 0.034},
    {"type_name": "3К(Cu)25", "r": 0.247, "x": 0.0303},
    {"type_name": "3К(Cu)35", "r": 0.173, "x": 0.029},
    {"type_name": "3К(Cu)50", "r": 0.123, "x": 0.0277},
    {"type_name": "3К(Cu)70", "r": 0.0867, "x": 0.0267},
    {"type_name": "3К(Cu)95", "r": 0.0647, "x": 0.026},
    {"type_name": "3К(Cu)120", "r": 0.051, "x": 0.0253},
    {"type_name": "3К(Cu)150", "r": 0.041, "x": 0.0247},
    {"type_name": "3К(Cu)185", "r": 0.033, "x": 0.0243},
    {"type_name": "3К(Cu)240", "r": 0.0257, "x": 0.0237},
]

def insert_line_types():
    """Создание таблиц и заполнение типами линий"""
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        count = 0
        
        # Вставка проводов
        for c in conductors:
            category = "Провода"
            type_name = c["type_name"]
            existing = (
                session.query(LineType)
                .filter(LineType.category == category, LineType.type_name == type_name)
                .one_or_none()
            )
            if existing:
                existing.r_ohm_per_km = c["r"]
                existing.x_ohm_per_km = c["x"]
                existing.description = f"Провод {type_name}"
            else:
                session.add(
                    LineType(
                        category=category,
                        type_name=type_name,
                        r_ohm_per_km=c["r"],
                        x_ohm_per_km=c["x"],
                        description=f"Провод {type_name}",
                    )
                )
            count += 1
        
        # Вставка кабелей
        for c in cables:
            category = "Кабели"
            type_name = c["type_name"]
            existing = (
                session.query(LineType)
                .filter(LineType.category == category, LineType.type_name == type_name)
                .one_or_none()
            )
            if existing:
                existing.r_ohm_per_km = c["r"]
                existing.x_ohm_per_km = c["x"]
                existing.description = f"Кабель {type_name}"
            else:
                session.add(
                    LineType(
                        category=category,
                        type_name=type_name,
                        r_ohm_per_km=c["r"],
                        x_ohm_per_km=c["x"],
                        description=f"Кабель {type_name}",
                    )
                )
            count += 1
        
        session.commit()
        print(f"Inserted {count} line types into DB.")
        print(f"  - Conductors: {len(conductors)}")
        print(f"  - Cables: {len(cables)}")

if __name__ == "__main__":
    insert_line_types()