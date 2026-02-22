import re
from pyrogram import filters

CMD_STARTERS = r"^[!/\.@]"

def cmd(commands):
    if isinstance(commands, str):
        commands = [commands]
    
    pattern = r"^[!/\.@](" + "|".join(commands) + r")(@\w+)?(\s|$)"
    return filters.regex(re.compile(pattern, re.IGNORECASE))

def get_args(message) -> list:
    text = message.text or message.caption or ""
    parts = text.split()
    return parts[1:] if parts else []
