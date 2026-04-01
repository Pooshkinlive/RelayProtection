USE RZA_Calculator;
GO

-- Таблица типов линий
CREATE TABLE line_types (
    id INT IDENTITY(1,1) PRIMARY KEY,
    category NVARCHAR(50) NOT NULL,
    type_name NVARCHAR(100) NOT NULL,
    r_ohm_per_km DECIMAL(10,6) NOT NULL,
    x_ohm_per_km DECIMAL(10,6) NOT NULL,
    description NVARCHAR(255),
    UNIQUE(category, type_name)
);

-- Таблица конфигураций пользователя
CREATE TABLE user_configurations (
    id INT IDENTITY(1,1) PRIMARY KEY,
    created_at DATETIME2 DEFAULT GETDATE(),
    total_length DECIMAL(10,2) DEFAULT 0
);

-- Таблица участков линии
CREATE TABLE line_sections (
    id INT IDENTITY(1,1) PRIMARY KEY,
    configuration_id INT FOREIGN KEY REFERENCES user_configurations(id) ON DELETE CASCADE,
    section_number INT NOT NULL,
    conductor_type NVARCHAR(100),
    conductor_length DECIMAL(10,2) DEFAULT 0,
    cable_type NVARCHAR(100),
    cable_length DECIMAL(10,2) DEFAULT 0
);

CREATE INDEX IX_line_types_category ON line_types(category);
CREATE INDEX IX_line_sections_config ON line_sections(configuration_id);