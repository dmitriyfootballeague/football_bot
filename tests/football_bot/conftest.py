import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from football_bot.models import (
    Player,
    PlayerPosition,
    PlayerRole,
    RegistrationStatus,
)


class FakeBot:
    def __init__(self):
        self.sent_messages = []
        self.sent_photos = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )

    async def send_photo(self, chat_id, photo, caption, reply_markup=None):
        self.sent_photos.append(
            {
                "chat_id": chat_id,
                "photo": photo,
                "caption": caption,
                "reply_markup": reply_markup,
            }
        )


class FakeMessage:
    def __init__(self):
        self.answers = []
        self.documents = []
        self.edited_reply_markup = []
        self.edited_text = []
        self.edited_caption = []

    async def answer(self, text, reply_markup=None):
        self.answers.append(
            {
                "text": text,
                "reply_markup": reply_markup,
            }
        )

    async def answer_document(self, document, caption=None, reply_markup=None):
        self.documents.append(
            {
                "document": document,
                "caption": caption,
                "reply_markup": reply_markup,
            }
        )

    async def edit_reply_markup(self, reply_markup=None):
        self.edited_reply_markup.append(reply_markup)

    async def edit_text(self, text, reply_markup=None):
        self.edited_text.append(
            {
                "text": text,
                "reply_markup": reply_markup,
            }
        )

    async def edit_caption(self, caption, reply_markup=None):
        self.edited_caption.append(
            {
                "caption": caption,
                "reply_markup": reply_markup,
            }
        )


class FakeUserMessage:
    def __init__(self, *, text=None, photo=None, user_id=1, username="tester"):
        self.text = text
        self.photo = photo or []
        self.from_user = SimpleNamespace(id=user_id, username=username)
        self.answers = []
        self.documents = []

    async def answer(self, text, reply_markup=None):
        self.answers.append(
            {
                "text": text,
                "reply_markup": reply_markup,
            }
        )

    async def answer_document(self, document, caption=None, reply_markup=None):
        self.documents.append(
            {
                "document": document,
                "caption": caption,
                "reply_markup": reply_markup,
            }
        )


class FakeCallback:
    def __init__(self, *, user_id=1, username="tester", data=None):
        self.from_user = SimpleNamespace(id=user_id, username=username)
        self.data = data
        self.message = FakeMessage()
        self.bot = FakeBot()
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append(
            {
                "text": text,
                "show_alert": show_alert,
            }
        )


class FakeState:
    def __init__(self, initial_data=None):
        self.data = dict(initial_data or {})
        self.current_state = None
        self.cleared = False

    async def set_state(self, state):
        self.current_state = state

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def get_data(self):
        return dict(self.data)

    async def clear(self):
        self.cleared = True
        self.data.clear()
        self.current_state = None


@pytest.fixture
def run_async():
    def _run(coro):
        return asyncio.run(coro)

    return _run


@pytest.fixture
def player_factory():
    def _make_player(
        *,
        player_id=1,
        telegram_id=1001,
        first_name="Ivan",
        last_name="Petrov",
        position=PlayerPosition.MIDFIELDER,
        role=PlayerRole.PLAYER,
        registration_status=RegistrationStatus.APPROVED,
        club_id=10,
        current_rating=None,
        prev_season_rating=None,
        description=None,
    ):
        return Player(
            id=player_id,
            telegram_id=telegram_id,
            telegram_username=f"user{telegram_id}",
            first_name=first_name,
            last_name=last_name,
            position=position,
            description=description,
            birth_date=date(2000, 1, 1),
            photo_file_id="photo-file-id",
            role=role,
            registration_status=registration_status,
            club_id=club_id,
            current_rating=current_rating,
            prev_season_rating=prev_season_rating,
        )

    return _make_player


@pytest.fixture
def callback_factory():
    def _make_callback(*, user_id=1, username="tester", data=None):
        return FakeCallback(user_id=user_id, username=username, data=data)

    return _make_callback


@pytest.fixture
def state_factory():
    def _make_state(initial_data=None):
        return FakeState(initial_data=initial_data)

    return _make_state


@pytest.fixture
def message_factory():
    def _make_message(*, text=None, photo=None, user_id=1, username="tester"):
        return FakeUserMessage(text=text, photo=photo, user_id=user_id, username=username)

    return _make_message
