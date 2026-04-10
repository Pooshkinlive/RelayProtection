import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from openpyxl import load_workbook

from app.models import Reactance, Base


DATABASE_URL = "mssql+pyodbc:///?odbc_connect=DRIVER={ODBC Driver 18 for SQL Server};SERVER=MSI-ALEXNAB\\SQLEXPRESS;DATABASE=RZA_Calculator;Trusted_Connection=yes;TrustServerCertificate=yes"
ENGINE = create_engine(DATABASE_URL)


def _find_expert_workbook_path() -> Path:
    # In this workspace the filename may be garbled by console encoding,
    # so we pick the smallest non-lock xlsx in data/input (this is ЭКСПЕРТ.xlsx).
    p = Path("data/input")
    files = [f for f in p.glob("*.xlsx") if not f.name.startswith("~$")]
    if not files:
        raise RuntimeError("No .xlsx files found in data/input")
    return min(files, key=lambda x: x.stat().st_size)


def _find_reactances_sheet(wb):
    # Prefer exact sheet name
    if "Реактансы" in wb.sheetnames:
        return wb["Реактансы"]

    # Fallback: find sheet whose row1 contains "MAX" and "MIN" in columns C/D.
    for name in wb.sheetnames:
        ws = wb[name]
        c1 = ws.cell(1, 3).value
        d1 = ws.cell(1, 4).value
        if isinstance(c1, str) and isinstance(d1, str) and "MAX" in c1.upper() and "MIN" in d1.upper():
            return ws

    raise RuntimeError("Reactances sheet not found (Реактансы / MAX/MIN)")


def upsert_reactances_from_expert() -> int:
    Base.metadata.create_all(ENGINE)

    expert_path = _find_expert_workbook_path()
    wb = load_workbook(expert_path, data_only=True)
    ws = _find_reactances_sheet(wb)

    count = 0
    with Session(ENGINE) as session:
        # Replace fully to avoid stale data.
        session.query(Reactance).delete()
        session.commit()

        for r in range(2, 2000):
            code = ws.cell(r, 1).value
            name = ws.cell(r, 2).value
            zmax = ws.cell(r, 3).value
            zmin = ws.cell(r, 4).value

            if code is None and name is None:
                break
            if not isinstance(code, (int, float)) or not name:
                continue
            if not isinstance(zmax, (int, float)) or not isinstance(zmin, (int, float)):
                continue

            session.add(
                Reactance(
                    reactance_code=int(code),
                    name=str(name),
                    z_max_ohm=float(zmax),
                    z_min_ohm=float(zmin),
                    is_active=True,
                )
            )
            count += 1

        session.commit()

    return count


def main() -> None:
    count = upsert_reactances_from_expert()
    print(f"Inserted reactances: {count}")


if __name__ == "__main__":
    main()

