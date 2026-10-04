import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
API_BASE_URL = "https://api.b365api.com/v3"
API_SPORT_ID = 151
API_TIMEOUT_SECONDS = 20
API_MAX_ATTEMPTS = 3
API_RETRY_BASE_DELAY_SECONDS = 1
API_RETRY_MAX_DELAY_SECONDS = 30
DATA_FILE = PROJECT_ROOT / "data.json"


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
API_KEY = os.getenv("API_KEY", "").strip()
