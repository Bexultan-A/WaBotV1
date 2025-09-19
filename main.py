from whatsapp_chatbot_python import GreenAPIBot, Notification, BaseStates
from whatsapp_chatbot_python.filters import TEXT_TYPES
from yaml import safe_load
import re
import requests
import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)   # подхватит .env из корня проекта

# 🔑 Авторизация (данные из кабинета Green-API)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID   = os.getenv("ASSISTANT_ID")

ID_INSTANCE        = os.getenv("ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("API_TOKEN_INSTANCE")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_API_URL   = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# Инициализация бота
bot = GreenAPIBot(ID_INSTANCE, API_TOKEN_INSTANCE)
YAML_DATA_RELATIVE_PATH = "data.yml"
with open(YAML_DATA_RELATIVE_PATH, encoding="utf8") as f:
    answers_data = safe_load(f)
class States(BaseStates):
    Initial="initial"
    Main="main"
    Secondary="secondary"
    Third="third"


def send_to_telegram(text: str, chat_id: int = TELEGRAM_CHAT_ID, timeout: int = 10):
    return requests.post(
        TELEGRAM_API_URL,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=timeout,
    )


@bot.router.message(state=None)
def start_handler(notification: Notification) -> None:
    sender = notification.sender

    notification.state_manager.update_state(sender, States.Initial.value)
    notification.answer(answers_data["welcome_message"])


@bot.router.message(
    type_message=TEXT_TYPES,
    state=States.Initial.value,
    regexp=r"^\s*(?:[1]|да)\s*$",
    re_flags=re.IGNORECASE,
)
def button_1_handler(notification: Notification) -> None:
    sender = notification.sender

    notification.state_manager.update_state(sender, States.Main.value)
    notification.answer(answers_data["button_1_response"])

@bot.router.message(
    type_message=TEXT_TYPES,
    state=States.Initial.value,
    regexp=r"^\s*(?:[2]|нет)\s*$",
    re_flags=re.IGNORECASE,
)
def button_2_handler(notification: Notification) -> None:
    sender = notification.sender

    notification.state_manager.update_state(sender, None)
    notification.answer(answers_data["button_2_response"])

#тут клиент ответит на вопрос ""Отлично! Пожалуйста, предоставьте следующую информацию:\n1. Ваше полное имя\n2. Контактный номер телефона\n3. Краткое описание того, что вы хотите от бота""
@bot.router.message(
    type_message=TEXT_TYPES,
    state=States.Main.value,
)
def info_handler(notification: Notification) -> None:
    sender = notification.sender
    user_message = notification.message_text.strip()

    # Проверка, что пользователь предоставил все необходимые данные. Данные должны быть разделены новой строкой или запятой или же пронумерованы 1. 2. 3.
    if len(user_message.split('\n')) >= 3 or len(user_message.split(',')) >= 3 or (re.search(r'1\.', user_message) and re.search(r'2\.', user_message) and re.search(r'3\.', user_message)):
        notification.state_manager.update_state(sender, States.Secondary.value)
        notification.answer(answers_data["info_received_response"])
        send_to_telegram(f"Новая заявка от {sender}:\n{user_message}")
    else:
        notification.answer("Пожалуйста, предоставьте всю необходимую информацию в указанном формате.")



# Запуск
if __name__ == "__main__":
    bot.run_forever()
