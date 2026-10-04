import logging

from config import BOT_LOG_FILE


# Настраивает единый формат и уровень логирования приложения.
def configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

    if not any(getattr(handler, "_bot_console_handler", False) for handler in root_logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        console_handler._bot_console_handler = True
        root_logger.addHandler(console_handler)

    log_file = BOT_LOG_FILE.resolve()
    if not any(
        isinstance(handler, logging.FileHandler)
        and getattr(handler, "baseFilename", None) == str(log_file)
        for handler in root_logger.handlers
    ):
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


# Возвращает логгер для указанного модуля.
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
