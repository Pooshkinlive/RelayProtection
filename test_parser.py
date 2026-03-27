# test_parser.py
from app.parser_excel import parse_excel_files, save_formulas_to_txt

# Укажи свои пути к файлам
file_paths = [
    r"data/input/Расчет реактансов по сетевым районам 2016.xlsx",
    r"data/input/ЭКСПЕРТ.xlsx",
    r"data/input/ЭТАЛОН защита ВЛ 6кВ ПЕРЕМИТИН.xlsx"
]

# Парсим формулы
formulas = parse_excel_files(file_paths)

# Сохраняем в файл
output_path = "data/output/parsed_formulas.txt"
save_formulas_to_txt(formulas, output_path)

print(f"Парсинг завершен. Результаты сохранены в {output_path}")
