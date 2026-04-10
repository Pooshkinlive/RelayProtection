from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean, Numeric, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base

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


class LineType(Base):
    __tablename__ = 'line_types'
    
    id = Column(Integer, primary_key=True)
    category = Column(String(50), nullable=False)
    type_name = Column(String(100), nullable=False)
    r_ohm_per_km = Column(Float, nullable=False)
    x_ohm_per_km = Column(Float, nullable=False)
    description = Column(String(255))


class RelayType(Base):
    __tablename__ = "relay_types"

    id = Column(Integer, primary_key=True)
    relay_code = Column(Integer, nullable=False, unique=True)  # K16 in Excel
    relay_name = Column(String(255), nullable=False)
    coef_l20 = Column(Float, nullable=False)  # VLOOKUP(..., 3)
    coef_l19 = Column(Float, nullable=False)  # VLOOKUP(..., 4)


class RelayTimeCharacteristic(Base):
    """
    VLOOKUP(K16; [ЭКСПЕРТ]Реле!$A$1:$E$9; 5) - time characteristic for MTZ (column E).
    Stored separately to avoid altering existing relay_types table.
    """

    __tablename__ = "relay_time_characteristics"

    id = Column(Integer, primary_key=True)
    relay_code = Column(Integer, nullable=False, unique=True)
    time_char_e = Column(String(255))


class Substation(Base):
    __tablename__ = "substations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    voltage_kv = Column(Float)
    region = Column(String(255))

    feeders = relationship("Feeder", back_populates="substation")


class Feeder(Base):
    __tablename__ = "feeders"

    id = Column(Integer, primary_key=True)
    substation_id = Column(Integer, ForeignKey("substations.id", ondelete="SET NULL"))
    name = Column(String(255), nullable=False)
    u_nom = Column(Float)
    description = Column(Text)

    substation = relationship("Substation", back_populates="feeders")


class NetworkSource(Base):
    """
    Source / network equivalent parameters used for SC calculations,
    e.g., from "Расчет реактансов по сетевым районам 2016".
    """

    __tablename__ = "network_sources"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    r_ohm = Column(Float)
    x_ohm = Column(Float)
    notes = Column(Text)


class Reactance(Base):
    """
    Reactances list from ЭКСПЕРТ.xlsx sheet 'Реактансы':
    - A: порядковый номер
    - B: ПС/РУ
    - C: Zmax норм. (Ом), D: Zmin норм. — могут быть NULL (только аварийный режим)
    - J: Zmax авар., K: Zmin авар. — NULL если режим А недоступен
    """

    __tablename__ = "reactances"

    id = Column(Integer, primary_key=True)
    reactance_code = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    z_max_ohm = Column(Float, nullable=True)
    z_min_ohm = Column(Float, nullable=True)
    z_a_max_ohm = Column(Float, nullable=True)
    z_a_min_ohm = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(String(100), nullable=True)

class Transformer(Base):
    """
    Transformers list from ЭКСПЕРТ.xlsx sheet 'Трансформаторы':
      - A: порядковый номер (1..11) -> используется как D26 в ЭТАЛОН
      - B: мощность (кВА)
      - C: полное сопротивление (Ом)
    """
    __tablename__ = "transformers"

    id = Column(Integer, primary_key=True)
    transformer_code = Column(Integer, nullable=False, unique=True)  # column A
    power_kva = Column(Float, nullable=False)  # column B
    z_ohm = Column(Float, nullable=False)  # column C


class CalculationContext(Base):
    """
    Stores 'for which feeder / which substation / which network source'
    the calculation was performed.
    """

    __tablename__ = "calculation_contexts"

    id = Column(BigInteger, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    feeder_id = Column(Integer, ForeignKey("feeders.id", ondelete="SET NULL"))
    network_source_id = Column(Integer, ForeignKey("network_sources.id", ondelete="SET NULL"))
    reactance_id = Column(Integer, ForeignKey("reactances.id", ondelete="SET NULL"))

    relay_code = Column(Integer)
    u_nom = Column(Float)
    i_load_max = Column(Float)

    input_json = Column(Text)
    result_json = Column(Text)


class LineSection(Base):
    __tablename__ = 'line_sections'
    
    id = Column(Integer, primary_key=True)
    configuration_id = Column(Integer, ForeignKey('user_configurations.id', ondelete='CASCADE'))
    section_number = Column(Integer, nullable=False)
    conductor_type = Column(String(100))
    conductor_length = Column(Float, default=0)
    cable_type = Column(String(100))
    cable_length = Column(Float, default=0)
    
    configuration = relationship("UserConfiguration", back_populates="sections")


class UserConfiguration(Base):
    __tablename__ = 'user_configurations'
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    total_length = Column(Float, default=0)
    
    sections = relationship("LineSection", back_populates="configuration", cascade="all, delete-orphan")


class InputParameter(Base):
    __tablename__ = 'input_parameters'
    
    id = Column(Integer, primary_key=True)
    param_code = Column(String(50), unique=True, nullable=False)
    param_name = Column(String(255), nullable=False)
    param_description = Column(Text)
    unit = Column(String(20))
    default_value = Column(Numeric(38, 15))
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