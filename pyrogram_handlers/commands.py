from pyrogram import filters

PREFIXES = "/!.@"

def cmd(commands):
    if isinstance(commands, str):
        commands = [commands]
    
    async def func(_, __, message):
        text = message.text or message.caption or ""
        if not text:
            return False
        
        if not text[0] in PREFIXES:
            return False
        
        command = text[1:].split()[0].lower()
        command = command.split("@")[0]
        
        return command in [c.lower() for c in commands]
    
    return filters.create(func)

def get_args(message) -> list:
    text = message.text or message.caption or ""
    parts = text.split()
    if parts:
        return parts[1:]
    return []
