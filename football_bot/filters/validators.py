import re
from datetime import datetime

NAME_PATTERN = re.compile(r"^[А-Яа-яЁёA-Za-z\- ]+$")


def is_valid_name(text: str | None) -> bool:
    if not text:
        return False
    return bool(NAME_PATTERN.match(text.strip())) and len(text.strip()) <= 100


def is_valid_date(text: str | None) -> bool:
    if not text:
        return False
    try:
        datetime.strptime(text.strip(), "%d.%m.%Y")
        return True
    except ValueError:
        return False
