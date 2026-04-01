import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.database import engine


def main() -> None:
    dedupe_sql = """
WITH d AS (
  SELECT
    id,
    ROW_NUMBER() OVER (PARTITION BY category, type_name ORDER BY id) AS rn
  FROM line_types
)
DELETE FROM line_types
WHERE id IN (SELECT id FROM d WHERE rn > 1);
""".strip()

    constraint_sql = """
IF NOT EXISTS (
  SELECT 1
  FROM sys.key_constraints
  WHERE name = 'UQ_line_types_category_type'
)
  ALTER TABLE line_types
  ADD CONSTRAINT UQ_line_types_category_type UNIQUE (category, type_name);
""".strip()

    count_sql = "select category, count(*) as cnt from line_types group by category order by category"

    with engine.begin() as conn:
        conn.execute(text(dedupe_sql))
        conn.execute(text(constraint_sql))
        rows = list(conn.execute(text(count_sql)))

    print("line_types counts:", rows)


if __name__ == "__main__":
    main()

