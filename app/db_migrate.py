"""
Idempotent DDL for SQL Server: extend dbo.reactances for UI-CRUD (hide / audit).
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_reactance_crud_columns(engine: Engine) -> None:
    stmts = [
        """
        IF COL_LENGTH('dbo.reactances', 'is_active') IS NULL
        BEGIN
            ALTER TABLE dbo.reactances ADD is_active BIT NOT NULL
                CONSTRAINT DF_reactances_is_active DEFAULT (1);
        END
        """,
        """
        IF COL_LENGTH('dbo.reactances', 'updated_at') IS NULL
        BEGIN
            ALTER TABLE dbo.reactances ADD updated_at DATETIME2 NULL;
        END
        """,
        """
        IF COL_LENGTH('dbo.reactances', 'updated_by') IS NULL
        BEGIN
            ALTER TABLE dbo.reactances ADD updated_by NVARCHAR(100) NULL;
        END
        """,
        """
        IF COL_LENGTH('dbo.reactances', 'z_a_max_ohm') IS NULL
        BEGIN
            ALTER TABLE dbo.reactances ADD z_a_max_ohm FLOAT NULL;
        END
        """,
        """
        IF COL_LENGTH('dbo.reactances', 'z_a_min_ohm') IS NULL
        BEGIN
            ALTER TABLE dbo.reactances ADD z_a_min_ohm FLOAT NULL;
        END
        """,
        # Нормальный режим: C/D могут быть NULL (только аварийный режим)
        """
        ALTER TABLE dbo.reactances ALTER COLUMN z_max_ohm FLOAT NULL;
        """,
        """
        ALTER TABLE dbo.reactances ALTER COLUMN z_min_ohm FLOAT NULL;
        """,
    ]
    with engine.begin() as conn:
        for sql in stmts:
            conn.execute(text(sql))
