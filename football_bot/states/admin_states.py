from aiogram.fsm.state import State, StatesGroup


class FSMAdminEditClub(StatesGroup):
    choose_club = State()
    enter_new_name = State()


class FSMAdminEditRating(StatesGroup):
    choose_player = State()
    enter_rating = State()
