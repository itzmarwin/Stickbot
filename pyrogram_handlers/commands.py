from pyrogram import filters

CMD_STARTERS = ("/", "!", ".", "@")

def cmd(commands):
    if isinstance(commands, str):
        commands = [commands]
    commands = [c.lower() for c in commands]

    async def func(_, __, message):
        text = message.text or ""
        if not text or text[0] not in CMD_STARTERS:
            return False
        return text[1:].split()[0].lower().split("@")[0] in commands

    return filters.create(func)

def get_args(message) -> list:
    text = message.text or message.caption or ""
    parts = text.split()
    return parts[1:] if parts else []
