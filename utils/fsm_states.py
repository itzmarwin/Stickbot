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
