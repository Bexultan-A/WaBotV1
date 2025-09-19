import os
import re
import json
import time
import requests
from yaml import safe_load

from whatsapp_chatbot_python import GreenAPIBot, Notification, BaseStates
from whatsapp_chatbot_python.filters import TEXT_TYPES
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)   # подхватит .env из корня проекта

# ========= ENV / CONFIG =========
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID   = os.getenv("ASSISTANT_ID")

ID_INSTANCE        = os.getenv("ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("API_TOKEN_INSTANCE")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_API_URL   = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

BITRIX_BASE = os.getenv("BITRIX_WEBHOOK_BASE", "").rstrip("/")
ASSIGNED_BY_ID = os.getenv("BITRIX_ASSIGNED_BY_ID")
CATEGORY_ID = os.getenv("BITRIX_CATEGORY_ID")
STAGE_ID = os.getenv("BITRIX_STAGE_ID")
DEAL_TITLE_PREFIX = os.getenv("DEAL_TITLE_PREFIX", "Заявка с сайта")

if not BITRIX_BASE:
    raise RuntimeError("Set BITRIX_WEBHOOK_BASE in .env")

YAML_DATA_RELATIVE_PATH = "data.yml"

# ========= OpenAI Assistants API =========
from openai import OpenAI
oai = OpenAI(api_key=OPENAI_API_KEY)

# Хранилище thread_id по отправителю (для продакшена — Redis/БД)
THREADS_BY_SENDER: dict[str, str] = {}

def get_or_create_thread_id(sender: str) -> str:
    if sender in THREADS_BY_SENDER:
        return THREADS_BY_SENDER[sender]
    thread = oai.beta.threads.create()
    THREADS_BY_SENDER[sender] = thread.id
    return thread.id

# ========= Telegram helpers =========
def send_to_telegram(text: str, chat_id: int = TELEGRAM_CHAT_ID, timeout: int = 10):
    """Отправка произвольного текста в Telegram."""
    try:
        r = requests.post(
            TELEGRAM_API_URL,
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True
            },
            timeout=timeout,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[TG] send_to_telegram error: {e}")
        return False

def send_lead_to_telegram(*, sender: str, name: str, phone: str, brief: str) -> bool:
    """Функция-исполнитель для tool `submit_lead`."""
    text = (
        "🆕 Новая заявка\n"
        f"• Отправитель (WA): {sender}\n"
        f"• Имя: {name}\n"
        f"• Телефон: {phone}\n"
        f"• Описание: {brief}"
    )
    return send_to_telegram(text)

# ========= Основной вызов ассистента с обработкой function calling =========
def ask_assistant(sender: str, user_text: str) -> str:
    if not OPENAI_API_KEY or not ASSISTANT_ID:
        return "Ассистент не сконфигурирован. Укажите OPENAI_API_KEY и ASSISTANT_ID."

    thread_id = get_or_create_thread_id(sender)

    # 1) складываем реплику пользователя в тред
    oai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_text
    )

    # 2) запускаем Run; инструкцией напоминаем про submit_lead
    run = oai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
    )

    terminal = {"completed", "failed", "cancelled", "expired"}

    while True:
        run = oai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

        if run.status == "requires_action":
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = []

            for tc in tool_calls:
                if tc.type == "function" and tc.function.name == "submit_lead":
                    # 2.1) Парсим аргументы функции
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}

                    name   = (args.get("name")  or "").strip()
                    phone  = (args.get("phone") or "").strip()
                    brief  = (args.get("brief") or "").strip()
                    _sender = (args.get("sender") or sender).strip()

                    # 2.2) Исполняем логику — отправка в Телеграм
                    ok = send_lead_to_telegram(sender=_sender, name=name, phone=phone, brief=brief)
                    tool_outputs.append({
                        "tool_call_id": tc.id,
                        "output": json.dumps({"ok": bool(ok)})
                    })
                else:
                    # неизвестные/прочие — подтверждаем нейтрально
                    tool_outputs.append({"tool_call_id": tc.id, "output": json.dumps({"ok": True})})

            # 2.3) Возвращаем результаты инструментов и продолжаем ран
            oai.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=tool_outputs
            )

        elif run.status in terminal:
            break
        else:
            time.sleep(0.4)

    if run.status != "completed":
        return f"Извините, ассистент не ответил (status={run.status})."

    # 3) Достаём финальный текст ассистента
    msgs = oai.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=15)
    for m in msgs.data:
        if m.role == "assistant":
            parts = []
            for c in getattr(m, "content", []) or []:
                if getattr(c, "type", "") == "text" and getattr(c, "text", None):
                    parts.append(c.text.value)
            if parts:
                return "\n".join(parts).strip()

    return "Пустой ответ ассистента."

# ========= Инициализация WhatsApp-бота =========
bot = GreenAPIBot(ID_INSTANCE, API_TOKEN_INSTANCE)

with open(YAML_DATA_RELATIVE_PATH, encoding="utf8") as f:
    answers_data = safe_load(f)

class States(BaseStates):
    Initial  = "initial"
    Main     = "main"
    Secondary= "secondary"
    Third    = "third"   # Диалог с ассистентом

# ========= Хендлеры =========
@bot.router.message(state=None)
def start_handler(notification: Notification) -> None:
    """Сразу переводим в режим общения с ассистентом."""
    sender = notification.sender
    notification.state_manager.update_state(sender, States.Third.value)
    notification.answer(
        answers_data.get(
            "welcome_message",
            "Здравствуйте! Я ИИ-ассистент. Можете просто задать вопрос или прислать заявку в формате: ФИО, телефон, краткое описание."
        )
    )

@bot.router.message(type_message=TEXT_TYPES, state=States.Third.value)
def assistant_chat_handler(notification: Notification) -> None:
    """Единый ответ ассистента (без чанков), с обработкой вызовов функций."""
    sender = notification.sender
    text = (notification.message_text or "").strip()

    if text.lower() in {"выход", "стоп", "меню"}:
        notification.state_manager.update_state(sender, None)
        notification.answer("Вышли из режима ассистента. Напишите 'start', чтобы начать заново.")
        return

    try:
        reply = ask_assistant(sender, text)
    except Exception as e:
        reply = f"Ошибка обращения к ассистенту: {e}"

    notification.answer(reply)

# ========= ENTRY =========
if __name__ == "__main__":
    bot.run_forever()
