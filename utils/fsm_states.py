from aiogram.fsm.state import State, StatesGroup

class KangStates(StatesGroup):
    """FSM states for kang command"""
    waiting_for_pack_name = State()
