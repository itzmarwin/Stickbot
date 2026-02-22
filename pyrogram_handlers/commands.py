from pyrogram import filters

PREFIXES = ["!", ".", "/", "@"]

def cmd(commands):
    return filters.command(commands, prefixes=PREFIXES)

def get_args(message) -> list:
    text = message.text or message.caption or ""
    parts = text.split()
    if parts:
        return parts[1:]
    return []
