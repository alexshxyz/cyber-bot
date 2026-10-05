from decimal import Decimal
import os
from pathlib import Path


# Путь к каталогу проекта.
PROJECT_ROOT = Path(__file__).resolve().parent
# Базовый URL BetsAPI.
API_BASE_URL = "https://api.b365api.com/v3"
# Идентификатор киберспортивного вида спорта в BetsAPI.
API_SPORT_ID = 151
# Таймаут одного запроса к BetsAPI в секундах.
API_TIMEOUT_SECONDS = 20
# Таймаут запроса к Telegram Bot API в секундах.
TELEGRAM_TIMEOUT_SECONDS = 20
# Базовый URL Telegram Bot API.
TELEGRAM_API_URL = "https://api.telegram.org"
# Количество повторных попыток запроса к BetsAPI после первой ошибки.
API_MAX_RETRIES = 4
# Пауза между повторными попытками запроса в секундах.
API_RETRY_DELAY_SECONDS = 3
# Интервал между циклами сбора матчей в секундах.
POLL_INTERVAL_SECONDS = 120
# Путь к файлу с полученными матчами и коэффициентами.
DATA_FILE = PROJECT_ROOT / "data.json"
# Режим сохранения подробных данных матчей (включается значением 1).
DEBUGMODE = os.getenv("DEBUGMODE", "0").strip()
# Путь к файлу с сигналами, подготовленными analyzer.
MATCHES_FILE = PROJECT_ROOT / "matches.json"
# Путь к файлу логов приложения.
BOT_LOG_FILE = PROJECT_ROOT / "bot.log"
# Минимальный процент падения коэффициента для создания сигнала.
DROP_THRESHOLD_PERCENT = Decimal("20")
# Максимальный новый коэффициент для создания сигнала.
MAX_SIGNAL_ODDS = Decimal("3.0")
# Максимальное время до начала матча для загрузки коэффициентов, в часах.
MAX_MATCH_START_HOURS = 8


# Загружает переменные окружения из файла .env, не перезаписывая системные.
def _load_env_file() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for line_number, line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if stripped_line.startswith("export "):
            stripped_line = stripped_line[len("export ") :]

        key, separator, value = stripped_line.partition("=")
        key = key.strip()
        if not separator or not key:
            raise ValueError(f"Invalid .env entry on line {line_number}.")

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_env_file()
# Ключ API BetsAPI из окружения или файла .env.
API_KEY = os.getenv("API_KEY", "").strip()
# Настройки канала Telegram Bot API.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
TELEGRAM_PROXY_HOST = os.getenv("TELEGRAM_PROXY_HOST", "").strip()
TELEGRAM_PROXY_PORT = os.getenv("TELEGRAM_PROXY_PORT", "").strip()
TELEGRAM_PROXY_USERNAME = os.getenv("TELEGRAM_PROXY_USERNAME", "").strip()
TELEGRAM_PROXY_PASSWORD = os.getenv("TELEGRAM_PROXY_PASSWORD", "").strip()
