import sqlite3
from contextlib import contextmanager

class DatabaseManager:
    def __init__(self, db_path: str = "rza_settings.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS network_elements (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    element_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS element_parameters (
                    id INTEGER PRIMARY KEY,
                    element_id INTEGER,
                    parameter_name TEXT NOT NULL,
                    parameter_value REAL,
                    FOREIGN KEY (element_id) REFERENCES network_elements (id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS protection_settings (
                    id INTEGER PRIMARY KEY,
                    element_id INTEGER,
                    protection_type TEXT NOT NULL,
                    setting_value REAL,
                    operating_time REAL,
                    sensitivity REAL,
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (element_id) REFERENCES network_elements (id)
                )
            ''')
            conn.commit()
