-- Создание базы данных RZA_Calculator
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'RZA_Calculator')
BEGIN
    CREATE DATABASE RZA_Calculator;
    PRINT 'База данных RZA_Calculator создана успешно!';
END
ELSE
BEGIN
    PRINT 'База данных RZA_Calculator уже существует.';
END
GO

-- Переключение на базу данных
USE RZA_Calculator;
GO

-- Создание таблиц
CREATE TABLE workbooks (
    id INT IDENTITY(1,1) PRIMARY KEY,
    filename NVARCHAR(255) NOT NULL UNIQUE,
    file_hash CHAR(32),
    imported_at DATETIME2 DEFAULT GETDATE(),
    is_active BIT DEFAULT 1
);

CREATE TABLE sheets (
    id INT IDENTITY(1,1) PRIMARY KEY,
    workbook_id INT FOREIGN KEY REFERENCES workbooks(id) ON DELETE CASCADE,
    sheet_name NVARCHAR(255) NOT NULL,
    UNIQUE(workbook_id, sheet_name)
);

CREATE TABLE cells (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    sheet_id INT FOREIGN KEY REFERENCES sheets(id) ON DELETE CASCADE,
    address NVARCHAR(10) NOT NULL,
    formula NVARCHAR(MAX),
    value_numeric DECIMAL(38,15),
    value_text NVARCHAR(MAX),
    data_type NVARCHAR(20),
    has_external_link BIT DEFAULT 0,
    updated_at DATETIME2 DEFAULT GETDATE(),
    UNIQUE(sheet_id, address)
);

CREATE TABLE input_parameters (
    id INT IDENTITY(1,1) PRIMARY KEY,
    param_code NVARCHAR(50) NOT NULL UNIQUE,
    param_name NVARCHAR(255) NOT NULL,
    param_description NVARCHAR(MAX),
    unit NVARCHAR(20),
    default_value DECIMAL(38,15),
    min_value DECIMAL(38,15),
    max_value DECIMAL(38,15),
    is_required BIT DEFAULT 1,
    display_order INT DEFAULT 0
);

CREATE TABLE calculation_results (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    calculation_type NVARCHAR(100),
    input_params_json NVARCHAR(MAX),
    result_value DECIMAL(38,15),
    result_unit NVARCHAR(20),
    calculated_at DATETIME2 DEFAULT GETDATE(),
    calculated_by NVARCHAR(100)
);

-- Создание индексов
CREATE INDEX IX_cells_lookup ON cells(sheet_id, address);
CREATE INDEX IX_cells_formula ON cells(sheet_id) WHERE formula IS NOT NULL;
CREATE INDEX IX_params_code ON input_parameters(param_code);

PRINT 'Все таблицы созданы успешно!';
GO