import logging


# Настраивает единый формат и уровень логирования приложения.
def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# Возвращает логгер для указанного модуля.
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
