"""
Idempotent DDL for SQL Server: extend dbo.reactances for UI-CRUD (hide / audit).
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_telephonegram_tables(engine: Engine) -> None:
    """Таблицы телефонограмм + счётчик номеров по дате «от:» (допускаются повторы № при разных датах)."""
    stmts = [
        """
        IF OBJECT_ID(N'dbo.telephonegram_daily_counters', N'U') IS NULL
        BEGIN
            CREATE TABLE dbo.telephonegram_daily_counters (
                telegram_date DATE NOT NULL PRIMARY KEY,
                last_no INT NOT NULL CONSTRAINT DF_tgdc_last_no DEFAULT (0)
            );
        END
        """,
        """
        IF OBJECT_ID(N'dbo.telephonegrams', N'U') IS NULL
        BEGIN
            CREATE TABLE dbo.telephonegrams (
                id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                created_at DATETIME2 NOT NULL CONSTRAINT DF_tg_created DEFAULT (SYSUTCDATETIME()),
                updated_at DATETIME2 NULL,
                created_by_role NVARCHAR(20) NOT NULL,
                telegram_no INT NOT NULL,
                telegram_date DATE NOT NULL,
                manual_fields_json NVARCHAR(MAX) NULL,
                calc_input_json NVARCHAR(MAX) NULL,
                calc_snapshot_json NVARCHAR(MAX) NOT NULL,
                status NVARCHAR(20) NOT NULL CONSTRAINT DF_tg_status DEFAULT (N'draft')
            );
            CREATE INDEX IX_telegrams_date_no ON dbo.telephonegrams (telegram_date DESC, telegram_no DESC);
        END
        """,
    ]
    with engine.begin() as conn:
        for sql in stmts:
            conn.execute(text(sql))


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
