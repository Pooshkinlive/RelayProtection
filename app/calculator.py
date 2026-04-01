from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from app.models import Cell, Sheet, Workbook, LineType, LineSection, UserConfiguration, RelayType, Reactance
import math

def get_cell_value(db: Session, sheet_name: str, cell_addr: str, workbook_filename: str = None) -> Optional[float]:
    """Получить числовое значение ячейки"""
    try:
        query = db.query(Cell).join(Sheet).join(Workbook)
        if workbook_filename:
            query = query.filter(Workbook.filename == workbook_filename)
        
        clean_sheet = sheet_name.strip()
        clean_addr = cell_addr.strip().upper().replace('$', '')
        
        cell = query.filter(
            Sheet.sheet_name == clean_sheet, 
            Cell.address == clean_addr
        ).first()
        
        if cell and cell.value_numeric is not None:
            return float(cell.value_numeric)
        if cell and cell.value_text:
            try:
                return float(cell.value_text.replace(',', '.'))
            except:
                return None
        return None
    except Exception as e:
        print(f"Error reading {sheet_name}!{cell_addr}: {e}")
        return None

def get_line_type(db: Session, category: str, type_name: str) -> Optional[LineType]:
    """Получить тип линии из БД"""
    try:
        line_type = db.query(LineType).filter(
            LineType.category == category,
            LineType.type_name == type_name
        ).first()
        return line_type
    except Exception as e:
        print(f"Error reading line type: {e}")
        return None

def get_relay_coeffs(db: Session, relay_code: int) -> Tuple[float, float]:
    """
    Excel mapping:
    - L20 = VLOOKUP(K16, RelayTable, 3)
    - L19 = VLOOKUP(K16, RelayTable, 4)
    """
    relay = db.query(RelayType).filter(RelayType.relay_code == relay_code).first()
    if not relay:
        # fallback to legacy constants
        return 1.2, 1.5
    return float(relay.coef_l20), float(relay.coef_l19)

def get_reactance_z(db: Session, reactance_id: Optional[int], mode: str = "MAX") -> float:
    """
    Returns Z of network reactance (as a single equivalent impedance in Ohms),
    taken from ЭКСПЕРТ.xlsx sheet "Реактансы".
    mode: "MAX" -> Zmax, "MIN" -> Zmin
    """
    if not reactance_id:
        return 0.0
    rx = db.query(Reactance).filter(Reactance.id == reactance_id).first()
    if not rx:
        return 0.0
    m = (mode or "MAX").upper()
    return float(rx.z_min_ohm) if m == "MIN" else float(rx.z_max_ohm)

def calculate_section_impedance(db: Session, section: LineSection) -> Dict[str, float]:
    """Расчёт сопротивления участка"""
    r_total = 0.0
    x_total = 0.0
    
    # Провод
    if section.conductor_type and section.conductor_length > 0:
        conductor = get_line_type(db, "Провода", section.conductor_type)
        if conductor:
            r_total += conductor.r_ohm_per_km * section.conductor_length
            x_total += conductor.x_ohm_per_km * section.conductor_length
    
    # Кабель
    if section.cable_type and section.cable_length > 0:
        cable = get_line_type(db, "Кабели", section.cable_type)
        if cable:
            r_total += cable.r_ohm_per_km * section.cable_length
            x_total += cable.x_ohm_per_km * section.cable_length
    
    return {"r": r_total, "x": x_total}

def calculate_total_impedance(db: Session, sections: List[LineSection]) -> Dict[str, float]:
    """Расчёт полного сопротивления линии"""
    r_total = 0.0
    x_total = 0.0
    length_total = 0.0
    
    for section in sections:
        impedance = calculate_section_impedance(db, section)
        r_total += impedance["r"]
        x_total += impedance["x"]
        length_total += section.conductor_length + section.cable_length
    
    return {
        "r_total": r_total,
        "x_total": x_total,
        "z_total": math.sqrt(r_total**2 + x_total**2),
        "length_total": length_total
    }

def calculate_short_circuit_current(u_nom: float, z_total: float) -> float:
    """Расчёт тока КЗ"""
    if z_total <= 0:
        return 0.0
    return u_nom / (math.sqrt(3) * z_total)

def calculate_short_circuit_current_2ph(u_nom: float, z_total: float) -> float:
    """
    2-phase (line-to-line) short-circuit current approximation.
    Using line-to-line voltage u_nom:
      I2 ≈ U / (2 * Z)
    """
    if z_total <= 0:
        return 0.0
    return u_nom / (2.0 * z_total)

def calculate_rza_settings(
    db: Session,
    sections: List[LineSection],
    u_nom: float = 6300.0,
    i_load_max: float = 100.0,
    relay_code: int = 6,
    reactance_id: Optional[int] = None,
    reactance_mode: str = "MAX",
    total_power_kw: float = 0.0,
    i_work: float = 0.0,
    manual_mto: float = 0.0,
    manual_mtz: float = 0.0,
) -> Dict[str, Any]:
    """Основной расчёт уставок РЗА"""
    
    # Расчёт полного сопротивления линии
    impedance = calculate_total_impedance(db, sections)

    # Reactance from network equivalent (C5 in Excel)
    z_react = get_reactance_z(db, reactance_id, reactance_mode)
    z_total_for_kz = math.sqrt(impedance["z_total"] ** 2) + z_react

    # Ток КЗ в конце линии (3ф, legacy placeholder)
    i_kz_end = calculate_short_circuit_current(u_nom, z_total_for_kz)
    i_kz2_end = calculate_short_circuit_current_2ph(u_nom, z_total_for_kz)
    
    # Excel-like: coefficients depend on relay type (K16)
    coef_l20, coef_l19 = get_relay_coeffs(db, relay_code)

    # Excel-derived load current:
    # J10 = L9 / 10.38  (for 6.3kV, includes sqrt(3) and reserve 1.05)
    i_nom = (float(total_power_kw) / 10.38) if total_power_kw > 0 else 0.0
    i_base_load = float(i_work) if i_work and i_work > 0 else i_nom

    # Approximated Excel-derived settings (placeholders until full formula engine):
    # - K24 ~ I_kz_end * L20
    # - K25 ~ J10 * L19 (or J12 if user provided)
    i_mto_setting = i_kz_end * coef_l20 if i_kz_end > 0 else 0.0
    i_mtz_setting = i_base_load * coef_l19 if i_base_load > 0 else 0.0
    
    # Sensitivity (Kч)
    sensitivity_mto = i_kz_end / i_mto_setting if i_mto_setting > 0 else 0
    sensitivity_mtz = i_kz_end / i_mtz_setting if i_mtz_setting > 0 else 0

    manual_mto_f = float(manual_mto or 0.0)
    manual_mtz_f = float(manual_mtz or 0.0)
    sensitivity_mto_manual = i_kz_end / manual_mto_f if manual_mto_f > 0 else 0.0
    sensitivity_mtz_manual = i_kz_end / manual_mtz_f if manual_mtz_f > 0 else 0.0
    
    # Проверка критериев
    kch_mto_min = 1.2
    kch_mtz_min = 1.5
    mto_ok = sensitivity_mto >= kch_mto_min
    mtz_ok = sensitivity_mtz >= kch_mtz_min
    mto_ok_manual = sensitivity_mto_manual >= kch_mto_min if manual_mto_f > 0 else False
    mtz_ok_manual = sensitivity_mtz_manual >= kch_mtz_min if manual_mtz_f > 0 else False
    
    return {
        "impedance": impedance,
        "i_kz_end": round(i_kz_end, 2),
        "i_kz2_end": round(i_kz2_end, 2),
        "i_mto_setting": round(i_mto_setting, 2),
        "i_mtz_setting": round(i_mtz_setting, 2),
        "sensitivity_mto": round(sensitivity_mto, 3),
        "sensitivity_mtz": round(sensitivity_mtz, 3),
        "sensitivity_mto_manual": round(sensitivity_mto_manual, 3),
        "sensitivity_mtz_manual": round(sensitivity_mtz_manual, 3),
        "mto_ok": mto_ok,
        "mtz_ok": mtz_ok,
        "mto_ok_manual": mto_ok_manual,
        "mtz_ok_manual": mtz_ok_manual,
        "u_nom": u_nom,
        "relay_code": relay_code,
        "coef_l20": coef_l20,
        "coef_l19": coef_l19,
        "kch_mto_min": kch_mto_min,
        "kch_mtz_min": kch_mtz_min,
        "reactance": {
            "id": reactance_id,
            "mode": reactance_mode,
            "z_ohm": round(z_react, 5),
        },
        "total_power_kw": round(float(total_power_kw), 3),
        "i_nom": round(float(i_nom), 3),
        "i_work": round(float(i_work), 3),
        "manual_mto": round(manual_mto_f, 3),
        "manual_mtz": round(manual_mtz_f, 3),
    }

def generate_chart_data(
    db: Session,
    sections: List[LineSection],
    u_nom: float,
    i_mto_setting: float,
    i_mtz_setting: float,
    reactance_id: Optional[int] = None,
    reactance_mode: str = "MAX",
    kch_mto_min: float = 1.2,
    kch_mtz_min: float = 1.5,
    max_length: float = 55.0,
) -> Dict[str, Any]:
    """График: ток 2-х фазного КЗ в конце линии vs длина + авто-масштаб"""
    impedance_total = calculate_total_impedance(db, sections)
    z_react = get_reactance_z(db, reactance_id, reactance_mode)
    
    total_len = max(float(impedance_total["length_total"]), 0.0)

    # X-axis must match the actual feeder length (no extrapolation beyond Lфидера).
    # This avoids misleading "zone" outside the real line length.
    if total_len <= 0:
        x_max = min(max_length, 0.5)
    else:
        x_max = min(max_length, total_len)

    # Avoid extremely small length point that blows up Y-scale
    min_len = 0.5
    step = 0.5 if x_max <= 20 else 1.0

    lengths: List[float] = []
    ikz2_values: List[float] = []

    length_km = min_len
    while length_km <= x_max + 1e-9:
        
        # Масштабируем сопротивление пропорционально длине
        scale = length_km / max(impedance_total["length_total"], 0.1)
        r_scaled = impedance_total["r_total"] * scale
        x_scaled = impedance_total["x_total"] * scale
        z_scaled = math.sqrt(r_scaled**2 + x_scaled**2) + z_react
        
        ikz2 = calculate_short_circuit_current_2ph(u_nom, z_scaled)
        
        lengths.append(round(length_km, 2))
        ikz2_values.append(round(ikz2, 2))

        length_km += step

    # Ensure last point exactly at x_max (e.g., 13.00 km), even when step grid skips it.
    if total_len > 0 and (not lengths or abs(lengths[-1] - round(x_max, 2)) > 1e-6):
        length_km = float(x_max)
        scale = length_km / max(impedance_total["length_total"], 0.1)
        r_scaled = impedance_total["r_total"] * scale
        x_scaled = impedance_total["x_total"] * scale
        z_scaled = math.sqrt(r_scaled**2 + x_scaled**2) + z_react
        ikz2 = calculate_short_circuit_current_2ph(u_nom, z_scaled)
        lengths.append(round(length_km, 2))
        ikz2_values.append(round(ikz2, 2))

    # Auto Y scale so intersections are readable
    y_candidates = [v for v in ikz2_values if v is not None]
    if i_mto_setting > 0:
        y_candidates.append(float(i_mto_setting))
    if i_mtz_setting > 0:
        y_candidates.append(float(i_mtz_setting))
    y_max = max(y_candidates) * 1.15 if y_candidates else 1000.0
    y_max = max(10.0, y_max)

    return {
        "lengths": lengths,
        "ikz2_values": ikz2_values,
        "i_mto_setting": round(float(i_mto_setting), 2),
        "i_mtz_setting": round(float(i_mtz_setting), 2),
        "total_length": round(total_len, 2),
        "x_max": round(float(x_max), 2),
        "y_max": round(float(y_max), 2),
        "step": step,
        "reactance": {"id": reactance_id, "mode": reactance_mode, "z_ohm": round(z_react, 5)},
    }