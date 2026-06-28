from football_bot.keyboards.inline.registration_kb import PositionCallback, create_position_kb


def test_create_position_kb_uses_split_midfielder_options():
    markup = create_position_kb()

    buttons = [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]

    assert buttons == [
        ("Вратарь", PositionCallback(position="goalkeeper").pack()),
        ("Защитник", PositionCallback(position="defender").pack()),
        (
            "Оборонительный полузащитник",
            PositionCallback(position="defensive_midfielder").pack(),
        ),
        (
            "Атакующий полузащитник",
            PositionCallback(position="attacking_midfielder").pack(),
        ),
        ("Нападающий", PositionCallback(position="forward").pack()),
    ]
