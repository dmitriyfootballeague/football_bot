from aiogram.fsm.state import State, StatesGroup


class FSMRegistration(StatesGroup):
    enter_first_name = State()
    enter_last_name = State()
    choose_position = State()
    enter_description = State()
    enter_birth_date = State()
    upload_photo = State()
    choose_status = State()
    choose_tournament = State()
    choose_club = State()
    choose_role = State()
