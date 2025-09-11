from whatsapp_chatbot_python import GreenAPIBot, Notification, BaseStates

# 🔑 Авторизация (данные из кабинета Green-API)
ID_INSTANCE = "7105317910"
API_TOKEN_INSTANCE = "a49a64afbc914cf5ac6c67982b7afae06f22d4bb68a541bcbe"

# Инициализация бота
bot = GreenAPIBot(ID_INSTANCE, API_TOKEN_INSTANCE)

class States(BaseStates):
    Main="main"
    Secondary="secondary"
    Third="third"

# Обработчик входящих сообщений
@bot.router.message(text_message=["start"], state=None)
def start_handler(notification: Notification) -> None:
    sender = notification.sender

    notification.state_manager.update_state(sender, States.Main.value)
    notification.answer(
        (
            "1 or 2"
        )
    )

@bot.router.message(text_message=["1"], state=States.Main.value)
def one_handler(notification: Notification) -> None:
    sender = notification.sender

    notification.state_manager.update_state(sender, States.Secondary.value)
    notification.answer(
        (
            "вы выбрали 1" \
            "теперь выберите а или б" \
            "Чтобы вернуться, напишите 'назад' "
        )
    )

@bot.router.message(text_message=["а"], state=States.Secondary.value)
def a_handler(notification: Notification) -> None:
    notification.answer(
        (
            "вы выбрали а"\
            "Чтобы вернуться, напишите 'назад' "
        )
    )


@bot.router.message(text_message=["б"], state=States.Secondary.value)
def b_handler(notification: Notification) -> None:
    notification.answer(
        (
            "вы выбрали б"\
            "Чтобы вернуться, напишите 'назад' "
        )
    )
@bot.router.message(text_message=["2"], state=States.Main.value)
def two_handler(notification: Notification) -> None:
    sender = notification.sender

    notification.state_manager.update_state(sender, States.Third.value)
    notification.answer(
        (
            "вы выбрали 2" \
            "теперь выберите н или д" \
            "Чтобы вернуться, напишите 'назад'"
        )
    )

@bot.router.message(text_message=["н"], state=States.Third.value)
def n_handler(notification: Notification) -> None:
    notification.answer(
        (
            "вы выбрали н"\
            "Чтобы вернуться, напишите 'назад' "
        )
    )

@bot.router.message(text_message=["д"], state=States.Third.value)
def d_handler(notification: Notification) -> None:
    notification.answer(
        (
            "вы выбрали д"\
            "Чтобы вернуться, напишите 'назад' "
        )
    )

@bot.router.message(text_message=["назад"])
def back_to_main_handler(notification: Notification) -> None:
    sender = notification.sender

    state = notification.state_manager.get_state(sender)
    if state == States.Main.value:
        return start_handler(notification)
    elif state == States.Secondary.value:
        notification.state_manager.update_state(sender, States.Main.value)
        return one_handler(notification)
    elif state == States.Third.value:
        notification.state_manager.update_state(sender, States.Main.value)
        return two_handler(notification)
    else:
        notification.state_manager.delete_state(sender)
        return start_handler(notification)

# Запуск
if __name__ == "__main__":
    bot.run_forever()
