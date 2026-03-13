
hyperauto-parser

Парсер товаров по Бренду и Артикулу на сайте: https://hyperauto.ru/

Данные для поиска ввиде Колонок Бренд и Артикул записаны в excel файл: 'товары.xlsx'


Порядок настройки и запуска в PowerShell (от имени администратора):

```bash
git clone https://github.com/samloik/hyperauto-parser.git

cd hyperauto-parser

python -m venv pure_venv

.\pure_venv\Scripts\Activate.ps1 

$env:PLAYWRIGHT_BROWSERS_PATH="0"

pip install -r requirements.txt

playwright install chromium
```

Далее копируем в эту папку наш заполненный файл 'товары.xlsx' и запускаем 'main.py':

```bash
python main.py
```

Найденные данные будут записаны в файл: 'цены_гиперавто_<дата>_<время>.xlsx'

-------------------------------------------------------------

Для запуска на ubuntu через docker compose.

Запускаем:

```bash
sudo apt-get update
```

Необходимо установить git:

```bash
sudo apt install git -y
```

Установить docker compose (https://docs.docker.com/compose/install/linux/#install-using-the-repository)

```bash
sudo apt-get install docker-compose-plugin

docker compose version
```

Далее клонируем репозиторий:

```bash
git clone https://github.com/samloik/hyperauto-parser.git

cd hyperauto-parser
```

Собираем образ:

```bash
docker compose build
```

-------------------------------------------------------------

Добавляем в текущую папку файл 'товары.xlsx'

Запускаем контейнер:
```bash
docker compose up
```

Найденные данные будут записаны в файл: 'цены_гиперавто_<дата>_<время>.xlsx'

