USE RZA_Calculator;
GO

-- Инженерные параметры (вводятся расчетчиком)
INSERT INTO input_parameters (param_code, param_name, param_description, unit, default_value, min_value, max_value, display_order, excel_sheet, excel_cell, is_engineer_input) VALUES
('TYPE_LINE_1', 'Тип линии 1', 'Тип первой секции линии (берется из справочника)', NULL, NULL, NULL, NULL, 1, 'Расчет', 'C5', 1),
('LENGTH_LINE_1', 'Длина линии 1', 'Длина первой секции линии', 'км', 2.5, 0.1, 50.0, 2, 'Расчет', 'D5', 1),
('TYPE_LINE_2', 'Тип линии 2', 'Тип второй секции линии', NULL, NULL, NULL, NULL, 3, 'Расчет', 'C6', 1),
('LENGTH_LINE_2', 'Длина линии 2', 'Длина второй секции линии', 'км', 1.8, 0.1, 50.0, 4, 'Расчет', 'D6', 1),
('NOMINAL_CURRENT', 'Номинальный ток', 'Номинальный ток линии', 'А', 400.0, 10.0, 2000.0, 5, 'Расчет', 'F6', 1),
('SET_MTO', 'Уставка МТО', 'Ток срабатывания максимальной токовой отсечки', 'А', NULL, 10.0, 10000.0, 6, 'Расчет', 'K26', 1),
('SET_MTZ', 'Уставка МТЗ', 'Ток срабатывания максимальной токА', NULL, 10.0, 10000.0, 7, 'Расчет', 'K27', 1);

-- Автоматические параметры (рассчитываются)
INSERT INTO input_parameters (param_code, param_name, param_description, unit, default_value, min_value, max_value, display_order, excel_sheet, excel_cell, is_engineer_input) VALUES
('CALC_REACTANCE_R', 'Рассчитанный R''', 'Активное сопротивление линии', 'Ом/км', NULL, 0.0, 2.0, 100, 'Расчет', 'E5', 0),
('CALC_REACTANCE_X', 'Рассчитанный X''', 'Индуктивное сопротивление линии', 'Ом/км', NULL, 0.0, 2.0, 101, 'Расчет', 'F5', 0),
('CALC_SHORT_CIRCUIT', 'Ток КЗ', 'Рассчитанный ток короткого замыкания', 'А', NULL, 0.0, 50000.0, 102, 'Расчет', 'J82', 0),
('SENSITIVITY_FACTOR', 'Коэффициент чувствительности', 'Коэффициент чувствительности защиты', NULL, NULL, 0.5, 5.0, 103, 'Расчет', 'L82', 0);