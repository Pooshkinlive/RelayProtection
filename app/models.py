from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean, Numeric, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class Workbook(Base):
    __tablename__ = 'workbooks'
    id = Column(Integer, primary_key=True)
    filename = Column(String(255), unique=True, nullable=False)
    file_hash = Column(String(32))
    imported_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    sheets = relationship("Sheet", back_populates="workbook")

class Sheet(Base):
    __tablename__ = 'sheets'
    id = Column(Integer, primary_key=True)
    workbook_id = Column(Integer, ForeignKey('workbooks.id', ondelete='CASCADE'))
    sheet_name = Column(String(255), nullable=False)
    workbook = relationship("Workbook", back_populates="sheets")
    cells = relationship("Cell", back_populates="sheet")

class Cell(Base):
    __tablename__ = 'cells'
    id = Column(BigInteger, primary_key=True)
    sheet_id = Column(Integer, ForeignKey('sheets.id', ondelete='CASCADE'))
    address = Column(String(10), nullable=False)
    formula = Column(Text)
    value_numeric = Column(Numeric(38, 15))
    value_text = Column(Text)
    data_type = Column(String(20))
    has_external_link = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sheet = relationship("Sheet", back_populates="cells")

class InputParameter(Base):
    __tablename__ = 'input_parameters'
    id = Column(Integer, primary_key=True)
    param_code = Column(String(50), unique=True, nullable=False)
    param_name = Column(String(255), nullable=False)
    param_description = Column(Text)
    unit = Column(String(20))
    default_value =(Numeric(38, 15))
    min_value = Column(Numeric(38, 15))
    max_value = Column(Numeric(38, 15))
    is_required = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    excel_sheet = Column(String(100))
    excel_cell = Column(String(10))
    is_engineer_input = Column(Boolean, default=False)

class CalculationResult(Base):
    __tablename__ = 'calculation_results'
    id = Column(BigInteger, primary_key=True)
    calculation_type = Column(String(100))
    input_params_json = Column(Text)
    result_value = Column(Numeric(38, 15))
    result_unit = Column(String(20))
    calculated_at = Column(DateTime, default=datetime.utcnow)
    calculated_by = Column(String(100))