from pyrogram import filters

PREFIXES = ["!", ".", "/", "@"]

def cmd(commands):
    return filters.command(commands, prefixes=PREFIXES)
