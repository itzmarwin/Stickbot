from aiogram.fsm.state import State, StatesGroup

class KangStates(StatesGroup):
    """FSM states for kang command"""
    waiting_for_pack_name = State()

class PackManagementStates(StatesGroup):
    """FSM states for pack management"""
    waiting_for_new_pack_name = State()
    waiting_for_rename_pack_name = State()
    waiting_for_sticker_to_add = State()
    confirming_delete_pack = State()
    waiting_for_first_sticker = State()  # NEW STATE ADDED

class PublishStates(StatesGroup):
    """FSM states for publish pack feature"""
    waiting_for_keyword = State()
    confirming_publish = State()

class CopyPackStates(StatesGroup):
    """FSM states for copypack feature"""
    waiting_for_pack_name = State()
