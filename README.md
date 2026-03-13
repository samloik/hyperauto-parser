
hyperauto-parser

Парсер товаров по Бренду и Артикулу на сайте: https://hyperauto.ru/

Данные для поиска ввиде Колонок Бренд и Артикул записаны в excel файл: товары.xlsx


Порядок настройки и запуска в PowerShell (от имени администратора):

```bash
git clone https://github.com/samloik/hyperauto-parser.git

cd hyperauto-parser

python -m venv pure_venv

.\pure_venv\Scripts\Activate.ps1 

$env:PLAYWRIGHT_BROWSERS_PATH="0"

pip install -r requirements.txt

playwright install chromium

python main.py
```

