from pyrogram import filters

COMMAND_PREFIXES = ["/", "!", ".", "@"]

def cmd(commands, prefixes=None):
    if prefixes is None:
        prefixes = COMMAND_PREFIXES
    return filters.command(commands, prefixes=prefixes)
