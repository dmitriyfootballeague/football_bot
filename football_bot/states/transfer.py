from aiogram.fsm.state import State, StatesGroup


class FSMTransfer(StatesGroup):
    choose_tournament = State()
    choose_club = State()
