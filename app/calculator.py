from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from app.models import (
    Cell,
    Sheet,
    Workbook,
    LineType,
    LineSection,
    UserConfiguration,
    RelayType,
    RelayTimeCharacteristic,
    Reactance,
    Transformer,
)
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
    - L20 = VLOOKUP(K16, RelayTable, 3) — множитель для КЗ за тр (~1.0…1.25)
    - L19 = VLOOKUP(K16, RelayTable, 4) — множитель Iнам (~2…4)
    """
    relay = db.query(RelayType).filter(RelayType.relay_code == relay_code).first()
    if not relay:
        return 1.2, 1.5
    c20 = float(relay.coef_l20)
    c19 = float(relay.coef_l19)
    # Если при импорте перепутаны столбцы C/D листа «Реле», в БД окажется L20≈3 и L19≈1.15.
    if c20 >= 1.8 and c19 <= 1.35:
        c20, c19 = c19, c20
    return c20, c19


def get_relay_time_char(db: Session, relay_code: int) -> Optional[str]:
    """
    K34 in ЭТАЛОН:
      =VLOOKUP(K16;[ЭКСПЕРТ.xls]Реле!$A$1:$E$9;5)
    i.e. MTZ time characteristic from column E.
    """
    row = (
        db.query(RelayTimeCharacteristic)
        .filter(RelayTimeCharacteristic.relay_code == relay_code)
        .first()
    )
    if not row:
        return None
    return str(row.time_char_e) if row.time_char_e is not None else None

def _reactance_by_id(db: Session, reactance_id: Optional[int]) -> Optional[Reactance]:
    if not reactance_id:
        return None
    return db.query(Reactance).filter(Reactance.id == reactance_id).first()


def regime_normal_available(rx: Optional[Reactance]) -> bool:
    if not rx:
        return False
    return rx.z_max_ohm is not None and rx.z_min_ohm is not None


def regime_emergency_available(rx: Optional[Reactance]) -> bool:
    if not rx or rx.z_a_max_ohm is None or rx.z_a_min_ohm is None:
        return False
    try:
        return float(rx.z_a_max_ohm) > 0.0 and float(rx.z_a_min_ohm) > 0.0
    except (TypeError, ValueError):
        return False


def head_z_normal(rx: Reactance, mode: str) -> float:
    m = (mode or "MAX").upper()
    if m == "MIN":
        return float(rx.z_min_ohm or 0.0)
    return float(rx.z_max_ohm or 0.0)


def head_z_emergency(rx: Reactance, mode: str) -> float:
    m = (mode or "MAX").upper()
    if m == "MIN":
        return float(rx.z_a_min_ohm or 0.0)
    return float(rx.z_a_max_ohm or 0.0)


def get_reactance_z(db: Session, reactance_id: Optional[int], mode: str = "MAX") -> float:
    """
    Нормальный режим: Zmax/Zmin из C/D. Если строка без C/D — 0.
    """
    rx = _reactance_by_id(db, reactance_id)
    if not rx or not regime_normal_available(rx):
        return 0.0
    return head_z_normal(rx, mode)

def get_transformer_z(db: Session, transformer_code: Optional[int]) -> float:
    """
    Excel:
      E26 = VLOOKUP(D26; [ЭКСПЕРТ.xlsx]Трансформаторы!$A$1:$C$12; 3)
    where D26 is transformer_code from column A.
    """
    if transformer_code is None:
        return 0.0
    tr = db.query(Transformer).filter(Transformer.transformer_code == transformer_code).first()
    if not tr:
        return 0.0
    return float(tr.z_ohm)

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


def _section_etalon_ef_per_km(db: Session, section: LineSection) -> Tuple[float, float, float]:
    """
    Как строка «Расчет» для одного участка UI: длина L = D9+D10,
    в J16 используется L9*(E9+E10) и L9*(F9+F10), где E9/F9 — провод, E10/F10 — кабель.
    Возвращает (L_км, e_sum_Ом_на_км, f_sum_Ом_на_км) = (L, E9+E10, F9+F10).
    """
    Lc = float(section.conductor_length or 0)
    Lk = float(section.cable_length or 0)
    L = Lc + Lk
    e9 = 0.0
    f9 = 0.0
    e10 = 0.0
    f10 = 0.0
    if section.conductor_type and Lc > 0:
        lt = get_line_type(db, "Провода", section.conductor_type)
        if lt:
            e9 = float(lt.r_ohm_per_km)
            f9 = float(lt.x_ohm_per_km)
    if section.cable_type and Lk > 0:
        cab = get_line_type(db, "Кабели", section.cable_type)
        if cab:
            e10 = float(cab.r_ohm_per_km)
            f10 = float(cab.x_ohm_per_km)
    return L, e9 + e10, f9 + f10


def _kl_four_slot_rows(
    db: Session, sections: List[LineSection]
) -> List[List[Tuple[float, float, float]]]:
    """
    Четыре «слота» как четыре пары строк Расчет!9–10 … 18–19 на листе «1».
    Каждый слот — упорядоченный список сегментов (L_км, e_sum, f_sum), по одному
    участку UI на сегмент. При >4 участках два последних **склеиваются в цепочку**
    (b + a), а не в одно среднее (e,f): иначе для абсцисс 0,2·D20… J27… расходится
    с Эталоном, если у участков разные удельные сопротивления.
    """
    rows: List[List[Tuple[float, float, float]]] = []
    for sec in sections:
        L, e_sum, f_sum = _section_etalon_ef_per_km(db, sec)
        if L <= 1e-15 and abs(e_sum) < 1e-15 and abs(f_sum) < 1e-15:
            continue
        rows.append([(L, e_sum, f_sum)])

    if not rows:
        return [[] for _ in range(4)]

    while len(rows) > 4:
        a = rows.pop()
        b = rows.pop()
        rows.append(b + a)

    while len(rows) < 4:
        rows.append([])

    return rows[:4]


def _etalon_z_kl_sumsq(
    d_km: float,
    slot_rows: List[List[Tuple[float, float, float]]],
    f5_ohm: float,
) -> float:
    """
    Эквивалент J16/J27/J38/…: для каждого слота последовательно, внутри слота — по
    сегментам, нарастающая длина «как L9, L11, L13, L15» затем следующий слот.
      R_Σ = Σ take·(E9+E10),  X_Σ = F5 + Σ take·(F9+F10),  |Z| = √(R_Σ² + X_Σ²).
    """
    R_tot = 0.0
    X_line = 0.0
    rem = max(float(d_km), 0.0)
    for row in slot_rows:
        for Lb, e_sum, f_sum in row:
            if Lb <= 1e-15:
                continue
            take = min(rem, Lb)
            R_tot += take * e_sum
            X_line += take * f_sum
            rem -= take
            if rem <= 1e-15:
                break
        if rem <= 1e-15:
            break
    X_tot = float(f5_ohm) + X_line
    return max(math.sqrt(R_tot * R_tot + X_tot * X_tot), 1e-9)

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


def _feeder_r_x_lengths(
    db: Session,
    sections: List[LineSection],
    after_sections: Optional[List[LineSection]] = None,
) -> Tuple[float, float, float, float, float, float]:
    """R, X и длины участка до ТР и после ТР (сумма по секциям)."""
    after_sections = after_sections or []
    imp_before = calculate_total_impedance(db, sections)
    imp_after = calculate_total_impedance(db, after_sections)
    r_b = float(imp_before["r_total"])
    x_b = float(imp_before["x_total"])
    L_b = max(float(imp_before["length_total"]), 0.0)
    r_a = float(imp_after["r_total"])
    x_a = float(imp_after["x_total"])
    L_a = max(float(imp_after["length_total"]), 0.0)
    return r_b, x_b, L_b, r_a, x_a, L_a


def z_mod_full_path_at_length(
    L_km: float,
    r_b: float,
    x_b: float,
    L_b: float,
    r_a: float,
    x_a: float,
    L_a: float,
    z_react: float,
    z_tr: float,
) -> float:
    """
    Модуль |Z|(L) вдоль фидера (та же логика, что у графика I2ф):
    линия до ТР + E5; после точки Lдо — Zтр и линия после ТР.
    Для согласования с ЭТАЛОН: в конце фидера L = Lдо+Lпосле подставляется в цепочку J118 → B44.
    """
    eps = 1e-9
    L_km = max(0.0, L_km)
    if L_b <= eps:
        if L_a <= eps:
            zeq = abs(z_react + z_tr)
            return max(zeq, 1e-9)
        scale = min(L_km, L_a) / max(L_a, eps)
        r = r_a * scale
        xw = x_a * scale + z_react + z_tr
        return max(math.sqrt(r * r + xw * xw), 1e-9)
    if L_km <= L_b + 1e-9:
        scale = L_km / L_b
        r = r_b * scale
        xw = x_b * scale + z_react
        return max(math.sqrt(r * r + xw * xw), 1e-9)
    if L_a <= eps:
        r = r_b
        xw = x_b + z_react + z_tr
        return max(math.sqrt(r * r + xw * xw), 1e-9)
    dx = L_km - L_b
    scale_a = min(dx, L_a) / max(L_a, eps)
    r = r_b + r_a * scale_a
    xw = x_b + x_a * scale_a + z_react + z_tr
    return max(math.sqrt(r * r + xw * xw), 1e-9)


def j118_at_feeder_end(
    db: Session,
    sections: List[LineSection],
    after_sections: Optional[List[LineSection]],
    reactance_id: Optional[int],
    reactance_mode: str,
    transformer_code: Optional[int],
    z_react_override: Optional[float] = None,
) -> float:
    """
    |Z| в конце электрической трассы по вкладкам UI: L_доКЛ + L_доТР, с E5 и Zтр в конце
    (как нарастание по D28:F38 + E5 + E26). Для B44/K24 используйте j118_for_k24_b44 —
    при двух вкладках результат на полной длине совпадает; расхождение возможно, если модель
    расширят линией после ТР.
    """
    after_sections = after_sections or []
    r_b, x_b, L_b, r_a, x_a, L_a = _feeder_r_x_lengths(db, sections, after_sections)
    if z_react_override is not None:
        z_react = float(z_react_override)
    else:
        z_react = get_reactance_z(db, reactance_id, reactance_mode)
    z_tr = get_transformer_z(db, transformer_code)
    L_full = L_b + L_a
    if L_full <= 1e-9:
        return max(abs(z_react + z_tr), 1e-9)
    if L_a <= 1e-9:
        r_end = r_b
        x_end = x_b + z_react + z_tr
        return max(math.sqrt(r_end * r_end + x_end * x_end), 1e-9)
    return z_mod_full_path_at_length(L_full, r_b, x_b, L_b, r_a, x_a, L_a, z_react, z_tr)


def j118_for_k24_b44(
    db: Session,
    sections: List[LineSection],
    after_sections: Optional[List[LineSection]],
    reactance_id: Optional[int],
    reactance_mode: str,
    transformer_code: Optional[int],
    z_react_override: Optional[float] = None,
) -> float:
    """
    |Z| для '1'!B44 и K24: трёхфазное КЗ «за трансформатором».
    ЭТАЛОН, лист «1», яч. J118:
      J118 = SQRT( (SUMSQ( Σ L_i*(Rпровод_i + Rкабель_i) )) + (SUMSQ( E5 + E26 + Σ L_i*(Xпровод_i + Xкабель_i) )) )
    где блок i — строки «Расчет!D28:F38», т.е. **только** линия «до ТР» (вкладка 2 UI).

    Важно: ЭТАЛОН умножает суммарную длину участка (Dпровод+Dкабель) на сумму удельных
    сопротивлений (Eпровод+Eкабель) и (Fпровод+Fкабель). Это соответствует нашей функции
    `_section_etalon_ef_per_km`, а не `calculate_total_impedance` (которая суммирует L*R отдельно).
    """
    after_sections = after_sections or []
    if z_react_override is not None:
        z_react = float(z_react_override)
    else:
        z_react = get_reactance_z(db, reactance_id, reactance_mode)
    z_tr = get_transformer_z(db, transformer_code)  # E26

    # J118 uses only the "до ТР" part (after_sections), up to 4 slots.
    slot_rows_tr = _kl_four_slot_rows(db, after_sections)
    # Full distance to TR in the block: sum of all "до ТР" lengths.
    L_tr = 0.0
    for row in slot_rows_tr:
        for Lb, _, _ in row:
            L_tr += float(Lb)

    if L_tr <= 1e-9:
        return max(abs(z_react + z_tr), 1e-9)

    # Equivalent of SUMSQ( Σ L_i*(E_i) ) + SUMSQ( E5+E26 + Σ L_i*(F_i) )
    R_sum = 0.0
    X_line = 0.0
    for row in slot_rows_tr:
        for Lb, e_sum, f_sum in row:
            if Lb <= 1e-15:
                continue
            R_sum += float(Lb) * float(e_sum)
            X_line += float(Lb) * float(f_sum)

    X_sum = float(z_react) + float(z_tr) + X_line
    return max(math.sqrt(R_sum * R_sum + X_sum * X_sum), 1e-9)


def _ikz2_chart_series(
    u_nom: float,
    L_kl: float,
    slot_rows_kl: List[List[Tuple[float, float, float]]],
    z_head: float,
) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """Лист «1»: B20:B30 / D20:D30 или P20:P30 / R20:R30 — одна «головная» реактивность z_head."""
    eps = 1e-9
    zh = max(float(z_head), 1e-9)
    real: List[Optional[float]] = []
    for i in range(11):
        if i == 0:
            real.append(round(calculate_short_circuit_current_2ph(u_nom, zh), 2))
        elif L_kl <= eps:
            real.append(None)
        else:
            d_kl = (i / 10.0) * L_kl
            z_eq = _etalon_z_kl_sumsq(d_kl, slot_rows_kl, zh)
            real.append(round(calculate_short_circuit_current_2ph(u_nom, z_eq), 2))
    sens = [round(float(v) / 1.5, 2) if v is not None else None for v in real]
    return real, sens


def _calculate_rza_branch(
    db: Session,
    sections: List[LineSection],
    after_sections: List[LineSection],
    u_nom: float,
    relay_code: int,
    z_head: float,
    reactance_id: Optional[int],
    reactance_mode: str,
    transformer_code: Optional[int],
    total_power_kw: float,
    i_work: float,
    manual_mto: float,
    manual_mtz: float,
) -> Dict[str, Any]:
    """Расчёт уставок для одной ветки (Н или А) при заданной эквивалентной Z «головы»."""
    imp_kl = calculate_total_impedance(db, sections)
    slot_rows_kl = _kl_four_slot_rows(db, sections)
    L_kl_only = float(imp_kl["length_total"])
    eps_l = 1e-9
    zh = max(float(z_head), 0.0)
    if L_kl_only <= eps_l:
        z_kl_end = max(zh, 1e-9) if zh > 1e-15 else 1e-9
    else:
        z_kl_end = _etalon_z_kl_sumsq(L_kl_only, slot_rows_kl, zh)
    i_kz2_kl_end_min = calculate_short_circuit_current_2ph(u_nom, z_kl_end)

    j118_k24 = j118_for_k24_b44(
        db,
        sections,
        after_sections,
        reactance_id,
        reactance_mode,
        transformer_code,
        z_react_override=zh,
    )
    j118_feeder_end = j118_at_feeder_end(
        db,
        sections,
        after_sections,
        reactance_id,
        reactance_mode,
        transformer_code,
        z_react_override=zh,
    )

    i_kz3_b44 = calculate_short_circuit_current(u_nom, j118_k24)
    i_kz2_feeder_j118 = calculate_short_circuit_current_2ph(u_nom, j118_feeder_end)
    i_kz_end = i_kz2_kl_end_min

    coef_l20, coef_l19 = get_relay_coeffs(db, relay_code)
    i_nom = (float(total_power_kw) / 10.38) if total_power_kw > 0 else 0.0
    j11 = 0.7 * i_nom
    j12 = float(i_work) if i_work and i_work > 0 else 0.0

    i_kz3_tr = i_kz3_b44 * coef_l20 if i_kz3_b44 > 0 else 0.0
    i_nam = i_nom * coef_l19 if i_nom > 0 else 0.0
    i_raschet = j11 * 1.5 if j11 > 0 else 0.0
    i_real = j12 * 1.5 if j12 > 0 else 0.0
    i_mtz_dop = float(i_kz2_kl_end_min) / 1.5 if i_kz2_kl_end_min > 0 else 0.0

    i_mto_setting = i_kz3_tr
    i_mtz_setting = i_real

    sensitivity_mto = i_kz_end / i_mto_setting if i_mto_setting > 0 else 0
    sensitivity_mtz = i_kz_end / i_mtz_setting if i_mtz_setting > 0 else 0

    manual_mto_f = float(manual_mto or 0.0)
    manual_mtz_f = float(manual_mtz or 0.0)
    sensitivity_mto_manual = i_kz_end / manual_mto_f if manual_mto_f > 0 else 0.0
    sensitivity_mtz_manual = i_kz_end / manual_mtz_f if manual_mtz_f > 0 else 0.0

    kch_mto_min = 1.2
    kch_mtz_min = 1.5
    mto_ok = sensitivity_mto >= kch_mto_min
    mtz_ok = sensitivity_mtz >= kch_mtz_min
    mto_ok_manual = sensitivity_mto_manual >= kch_mto_min if manual_mto_f > 0 else False
    mtz_ok_manual = sensitivity_mtz_manual >= kch_mtz_min if manual_mtz_f > 0 else False

    z_tr = get_transformer_z(db, transformer_code)

    return {
        "j118_ohm": round(float(j118_k24), 5),
        "j118_k24_ohm": round(float(j118_k24), 5),
        "j118_feeder_end_ohm": round(float(j118_feeder_end), 5),
        "i_kz3_b44": round(float(i_kz3_b44), 3),
        "j11": round(float(j11), 3),
        "i_kz2_kl_end_min": round(float(i_kz2_kl_end_min), 2),
        "i_kz_end": round(float(i_kz_end), 2),
        "i_kz2_feeder_j118": round(float(i_kz2_feeder_j118), 2),
        "i_kz3_tr": round(float(i_kz3_tr), 2),
        "i_mto_setting": round(i_mto_setting, 2),
        "i_mtz_setting": round(i_mtz_setting, 2),
        "i_mtz_dop": round(float(i_mtz_dop), 2),
        "sensitivity_mto": round(sensitivity_mto, 3),
        "sensitivity_mtz": round(sensitivity_mtz, 3),
        "sensitivity_mto_manual": round(sensitivity_mto_manual, 3),
        "sensitivity_mtz_manual": round(sensitivity_mtz_manual, 3),
        "mto_ok": mto_ok,
        "mtz_ok": mtz_ok,
        "mto_ok_manual": mto_ok_manual,
        "mtz_ok_manual": mtz_ok_manual,
        "coef_l20": coef_l20,
        "coef_l19": coef_l19,
        "kch_mto_min": kch_mto_min,
        "kch_mtz_min": kch_mtz_min,
        "orient": {
            "j11": round(float(j11), 3),
            "b44_i_kz3": round(float(i_kz3_b44), 3),
            "k24_i_kz3_tr": round(float(i_kz3_tr), 3),
            "k25_i_nam": round(float(i_nam), 3),
            "k31_i_raschet": round(float(i_raschet), 3),
            "k32_i_real": round(float(i_real), 3),
            "k35_mtz_dop": round(float(i_mtz_dop), 3),
            "k34_vtx_mtz": get_relay_time_char(db, relay_code),
            "j118_ohm": round(float(j118_k24), 5),
            "j118_feeder_end_ohm": round(float(j118_feeder_end), 5),
        },
        "reactance_z_head_ohm": round(zh, 5),
        "transformer": {
            "code": transformer_code,
            "z_ohm": round(z_tr, 5),
        },
        "total_power_kw": round(float(total_power_kw), 3),
        "i_nom": round(float(i_nom), 3),
        "i_work": round(float(i_work), 3),
        "manual_mto": round(manual_mto_f, 3),
        "manual_mtz": round(manual_mtz_f, 3),
    }


def _empty_branch() -> Dict[str, Any]:
    return {
        "j118_ohm": 0.0,
        "j118_k24_ohm": 0.0,
        "j118_feeder_end_ohm": 0.0,
        "i_kz3_b44": 0.0,
        "j11": 0.0,
        "i_kz2_kl_end_min": 0.0,
        "i_kz_end": 0.0,
        "i_kz2_feeder_j118": 0.0,
        "i_kz3_tr": 0.0,
        "i_mto_setting": 0.0,
        "i_mtz_setting": 0.0,
        "i_mtz_dop": 0.0,
        "sensitivity_mto": 0.0,
        "sensitivity_mtz": 0.0,
        "sensitivity_mto_manual": 0.0,
        "sensitivity_mtz_manual": 0.0,
        "mto_ok": False,
        "mtz_ok": False,
        "mto_ok_manual": False,
        "mtz_ok_manual": False,
        "coef_l20": 1.2,
        "coef_l19": 1.5,
        "kch_mto_min": 1.2,
        "kch_mtz_min": 1.5,
        "orient": {
            "j11": 0.0,
            "b44_i_kz3": 0.0,
            "k24_i_kz3_tr": 0.0,
            "k25_i_nam": 0.0,
            "k31_i_raschet": 0.0,
            "k32_i_real": 0.0,
            "k35_mtz_dop": 0.0,
            "k34_vtx_mtz": None,
            "j118_ohm": 0.0,
            "j118_feeder_end_ohm": 0.0,
        },
        "reactance_z_head_ohm": 0.0,
        "transformer": {"code": None, "z_ohm": 0.0},
        "total_power_kw": 0.0,
        "i_nom": 0.0,
        "i_work": 0.0,
        "manual_mto": 0.0,
        "manual_mtz": 0.0,
    }


def calculate_rza_settings(
    db: Session,
    sections: List[LineSection],
    u_nom: float = 6300.0,
    relay_code: int = 6,
    reactance_id: Optional[int] = None,
    reactance_mode: str = "MAX",
    total_power_kw: float = 0.0,
    i_work: float = 0.0,
    manual_mto: float = 0.0,
    manual_mtz: float = 0.0,
    transformer_code: Optional[int] = None,
    after_sections: Optional[List[LineSection]] = None,
) -> Dict[str, Any]:
    """Основной расчёт уставок РЗА: нормальный и (при наличии J,K) аварийный режим."""
    after_sections = after_sections or []
    imp_kl = calculate_total_impedance(db, sections)
    imp_tr = calculate_total_impedance(db, after_sections)
    r_sum = float(imp_kl["r_total"]) + float(imp_tr["r_total"])
    x_sum = float(imp_kl["x_total"]) + float(imp_tr["x_total"])
    len_sum = float(imp_kl["length_total"]) + float(imp_tr["length_total"])
    impedance = {
        "r_total": r_sum,
        "x_total": x_sum,
        "z_total": math.sqrt(r_sum * r_sum + x_sum * x_sum),
        "length_total": len_sum,
    }

    rx = _reactance_by_id(db, reactance_id)
    has_n = bool(rx and regime_normal_available(rx))
    has_a = bool(rx and regime_emergency_available(rx))

    branch_n: Dict[str, Any]
    if has_n:
        zn = head_z_normal(rx, reactance_mode)
        branch_n = _calculate_rza_branch(
            db,
            sections,
            after_sections,
            u_nom,
            relay_code,
            zn,
            reactance_id,
            reactance_mode,
            transformer_code,
            total_power_kw,
            i_work,
            manual_mto,
            manual_mtz,
        )
    else:
        branch_n = _empty_branch()

    branch_a: Optional[Dict[str, Any]] = None
    if has_a:
        za = head_z_emergency(rx, reactance_mode)
        branch_a = _calculate_rza_branch(
            db,
            sections,
            after_sections,
            u_nom,
            relay_code,
            za,
            reactance_id,
            reactance_mode,
            transformer_code,
            total_power_kw,
            i_work,
            manual_mto,
            manual_mtz,
        )

    # Верхний уровень — нормальный режим; при отсутствии Н подставляем А (только аварийный справочник).
    primary = branch_n if has_n else (branch_a if has_a else branch_n)
    z_tr = get_transformer_z(db, transformer_code)

    out: Dict[str, Any] = {
        "impedance": impedance,
        "regime_normal_available": has_n,
        "regime_emergency_available": has_a,
        "u_nom": u_nom,
        "relay_code": relay_code,
        **primary,
        "emergency": branch_a,
        "reactance": {
            "id": reactance_id,
            "mode": reactance_mode,
            "z_ohm": round(float(primary.get("reactance_z_head_ohm") or 0), 5),
        },
        "transformer": {
            "code": transformer_code,
            "z_ohm": round(z_tr, 5),
        },
    }
    return out

def generate_chart_data(
    db: Session,
    sections: List[LineSection],
    u_nom: float,
    i_mto_setting: float,
    i_mtz_setting: float,
    after_sections: Optional[List[LineSection]] = None,
    reactance_id: Optional[int] = None,
    reactance_mode: str = "MAX",
    transformer_code: Optional[int] = None,
    kch_mto_min: float = 1.2,
    kch_mtz_min: float = 1.5,
    max_length: float = 55.0,
) -> Dict[str, Any]:
    """
    ЭТАЛОН, лист «1»:
      • Ось X для Реал.Н / С коэф.чувств.Н: B8:B18 = k/10 * Расчет!D20 (длина до КЛ).
      • B20 = U/(2*F5), F5 — реактивность ПС MIN (как в описании).
      • B21..B30 = U/(2*J16)…U/(2*J115); ось X — B9…B18 = 0,1…1,0·D20. Пары J↔L как в файле:
        J16↔L9,L11,L13,L15; J27↔L20,L22,L24,L26; J38↔L31…; J49↔L42…; … J115↔L108,L110,L112,L114.
      • |J| = √(R_Σ²+X_Σ²), R_Σ/X_Σ — суммы L·(E+E') и F5+L·(F+F') по слотам; >4 участков —
        цепочка сегментов в слоте (не среднее удельное на слот).
      • D20:D30 = B20:B30/1.5 — та же точка по X, Y чувствительности = соответствующий B/1,5.
      • При наличии J,K в справочнике — ещё P20:P30 / R20:R30 (Реал.А / С коэф.чувств.А), та же ось X.
    """
    after_sections = after_sections or []
    _, _, L_kl, _, _, L_tr = _feeder_r_x_lengths(db, sections, after_sections)
    z_tr = get_transformer_z(db, transformer_code)
    rx = _reactance_by_id(db, reactance_id)
    has_n = bool(rx and regime_normal_available(rx))
    has_a = bool(rx and regime_emergency_available(rx))
    zn = head_z_normal(rx, reactance_mode) if rx and has_n else None
    za = head_z_emergency(rx, reactance_mode) if rx and has_a else None

    slot_rows_kl = _kl_four_slot_rows(db, sections)

    L_full = L_kl + L_tr
    eps = 1e-9

    if L_kl <= eps:
        x_max_chart = min(max_length, 0.5)
    else:
        x_max_chart = min(max_length, L_kl)

    lengths_kl: List[float] = []
    for i in range(11):
        t = i / 10.0
        lengths_kl.append(round(t * L_kl, 6) if L_kl > eps else 0.0)

    if zn is not None:
        ikz2_real_n, ikz2_sens_n = _ikz2_chart_series(u_nom, L_kl, slot_rows_kl, zn)
    else:
        ikz2_real_n = [None] * 11
        ikz2_sens_n = [None] * 11

    if za is not None:
        ikz2_real_a, ikz2_sens_a = _ikz2_chart_series(u_nom, L_kl, slot_rows_kl, za)
    else:
        ikz2_real_a = [None] * 11
        ikz2_sens_a = [None] * 11

    y_candidates: List[float] = []
    for series in (ikz2_real_n, ikz2_sens_n, ikz2_real_a, ikz2_sens_a):
        for v in series:
            if v is not None:
                y_candidates.append(float(v))
    if i_mto_setting > 0:
        y_candidates.append(float(i_mto_setting))
    if i_mtz_setting > 0:
        y_candidates.append(float(i_mtz_setting))
    y_max = max(y_candidates) * 1.15 if y_candidates else 1000.0
    y_max = max(10.0, y_max)

    has_emergency_chart = has_a
    viz_mto_idx = 2 + (2 if has_emergency_chart else 0)
    viz_mtz_idx = viz_mto_idx + 1

    return {
        "lengths": lengths_kl,
        "lengths_kl": lengths_kl,
        "ikz2_real_n": ikz2_real_n,
        "ikz2_sens_n": ikz2_sens_n,
        "ikz2_real_a": ikz2_real_a,
        "ikz2_sens_a": ikz2_sens_a,
        "ikz2_values": ikz2_real_n,
        "ikz2_feeder_only": ikz2_real_n,
        "has_emergency_chart": has_emergency_chart,
        "vizor_mto_dataset_index": viz_mto_idx,
        "vizor_mtz_dataset_index": viz_mtz_idx,
        "length_kl_km": round(L_kl, 3),
        "length_tr_km": round(L_tr, 3),
        "length_before_tr_km": round(L_kl, 3),
        "length_after_tr_km": round(L_tr, 3),
        "i_mto_setting": round(float(i_mto_setting), 2),
        "i_mtz_setting": round(float(i_mtz_setting), 2),
        "total_length": round(L_full, 2),
        "x_max": round(float(x_max_chart), 4),
        "y_max": round(float(y_max), 2),
        "step": 0.1,
        "chart_points": 11,
        "chart_xy_mode": True,
        "reactance": {
            "id": reactance_id,
            "mode": reactance_mode,
            "z_ohm": round(float(zn or 0.0), 5),
        },
        "reactance_chart_min_ohm": round(float(zn or 0.0), 5),
        "reactance_emergency_z_ohm": round(float(za or 0.0), 5) if za is not None else None,
        "transformer": {"code": transformer_code, "z_ohm": round(z_tr, 5)},
    }