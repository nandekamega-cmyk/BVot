# --- НАЧАЛО: БЛОК 1 - ИМПОРТЫ И НАСТРОЙКИ СРЕДЫ ---

# Этот блок отвечает за все внешние зависимости и базовую настройку.
# Здесь мы импортируем библиотеки, настраиваем логирование и загружаем переменные окружения.
# Всё, что нужно для запуска, находится здесь.

import asyncio
import logging
import sqlite3
import random
import schedule
import threading
import time
import requests
import base64
import httpx
import json
import os
import io
from datetime import datetime, timedelta
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from openai import OpenAI
from pydub import AudioSegment
from typing import Dict, Any

# Настраиваем логирование, чтобы видеть, что происходит с ботом.
# Это твой "журнал" действий.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Загружаем переменные из .env файла. Это безопасно и удобно.
load_dotenv()

# --- КОНСТАНТЫ И ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
# Твой уникальный токен бота и ID чата.
BOT_TOKEN = getenv("BOT_TOKEN")
CHAT_ID = getenv("CHAT_ID")
# Ключи для OpenRouter и Google AI Studio.
OPENROUTER_API_KEY = getenv("OPENROUTER_API_KEY")
GOOGLE_AI_API_KEY = getenv('GOOGLE_AI_API_KEY')

if not all([BOT_TOKEN, CHAT_ID, OPENROUTER_API_KEY, GOOGLE_AI_API_KEY]):
    logging.error("Не все переменные окружения указаны в .env")
    raise ValueError("Укажи BOT_TOKEN, CHAT_ID, OPENROUTER_API_KEY и GOOGLE_AI_API_KEY в .env")

# Определяем путь к базе данных. Она должна лежать рядом с bot.py.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_data.db')
logging.info(f"Путь к базе данных: {DB_PATH}")


# --- КОНЕЦ: БЛОК 1 - ИМПОРТЫ И НАСТРОЙКИ СРЕДЫ ---


# --- НАЧАЛО: БЛОК 2 - НАСТРОЙКА БАЗЫ ДАННЫХ И ХРАНЕНИЕ ДАННЫХ ---

# Здесь мы создаем структуру для хранения информации о твоем прогрессе,
# действиях и планах. База данных — это твоя "память".

def connect_db():
    """Устанавливает соединение с базой данных."""
    return sqlite3.connect(DB_PATH)


conn = connect_db()
c = conn.cursor()

# Создаем таблицу для баллов, если её нет.
c.execute('''CREATE TABLE IF NOT EXISTS scores (date TEXT PRIMARY KEY, score REAL DEFAULT 0)''')
# Создаем таблицу для логов действий.
c.execute('''CREATE TABLE IF NOT EXISTS actions_log (timestamp TEXT, action TEXT, points REAL, type TEXT)''')
# Создаем таблицу для челленджей.
c.execute('''CREATE TABLE IF NOT EXISTS challenges (
             challenge_name TEXT PRIMARY KEY, 
             start_date TEXT, 
             end_date TEXT, 
             goal_value REAL, 
             description TEXT)''')
# Создаем таблицу для персонализированного ежедневного плана.
c.execute('''CREATE TABLE IF NOT EXISTS daily_plan (
             date TEXT, 
             user_id TEXT, 
             plan_item TEXT,
             is_completed INTEGER DEFAULT 0,
             status TEXT DEFAULT 'pending')''')

conn.commit()
conn.close()

# --- ТВОИ ДАННЫЕ И МЕТРИКИ ---
# Здесь ты можешь менять количество баллов за каждое действие.
actions = {
    "режим бога": 15, "мозговой штурм": 15, "бизнес-инкубатор": 20, "контент-машина": 15, "учебный рывок": 15,
    "рефлексия дня": 15, "воздержание": 20, "deep_work": 20,
    "шок-терапия": 10, "интеллектуальный старт": 10, "боевая готовность": 10, "физический интеллект": 10,
    "заправка машины": 5, "ночной покой": 10, "подготовка к бою": 5, "ранний подъем": 15, "холодный душ": 10,
    "пробежка": 10, "медитация": 15, "чтение": 10, "выполнил план": 25, "работа над проектом": 20,
    "изучение английского": 10, "силовая тренировка": 15, "без телефона перед сном": 10,
    "первая победа": 2, "очистка системы": 2, "освобождение от дня": 2, "50 отжиманий": 3, "20 подтягиваний": 4,
    "сделал кровать": 2, "вода с лимоном": 3, "без телефона утром": 5, "план на день": 5, "зарядка": 5,
    "растяжка": 5, "контрастный душ": 8, "сделал дз": 5, "100 отжиманий": 5, "спортивная ходьба": 5, "йога": 5,
    "мытье посуды": 2, "уборка в комнате": 3, "умывание": 3,
}

# Штрафы за провалы.
failures = {
    "pmo": -30, "скролл": -10, "сладкое": -5, "поздний отбой": -10, "поздний подъём": -10, "пропуск тренировки": -15
}

# --- КОНЕЦ: БЛОК 2 - НАСТРОЙКА БАЗЫ ДАННЫХ И ХРАНЕНИЕ ДАННЫХ ---


# --- НАЧАЛО: БЛОК 3 - ИНИЦИАЛИЗАЦИЯ БОТА И КЛИЕНТОВ ИИ ---

# Здесь мы запускаем "движок" бота и подключаем его к AI.

# Инициализируем объект бота и диспетчер (обработчик сообщений).
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализируем клиент OpenAI для OpenRouter.
ai_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=getenv("OPENROUTER_API_KEY")
)


# --- КОНЕЦ: БЛОК 3 - ИНИЦИАЛИЗАЦИЯ БОТА И КЛИЕНТОВ ИИ ---


# --- НАЧАЛО: БЛОК 4 - ФУНКЦИИ ИИ, ГЕНЕРАЦИИ ИЗОБРАЖЕНИЙ И АУДИО ---

# Этот блок содержит все функции, которые используют внешние AI-сервисы.
# Здесь происходит магия.

def get_ai_response(prompt_text: str, persona_prompt: str = "") -> str:
    """
    Генерирует ответ от нейросети с заданным промптом-персоной.
    """
    # Если промпт-персона не задан, используем стандартную "Бог-бот".
    if not persona_prompt:
        persona_prompt = f"Ты — личный гуру, бизнесмен, монах и наставник Артема. Твоя миссия — помочь ему стать лучшей версией себя и достичь величия, используя мудрость, мотивацию, бизнес-стратегии и жесткую дисциплину. Ты всегда обращаешься к нему по имени и говоришь, как будто знаешь его лично. Не давай легких путей, говори прямо, но с уважением. Всегда напоминай ему о его великой цели — 500k и о том, что он 'проиграл лето, не проиграет год'. Используй 'болевые точки' в своей мотивации. Анализируй его прогресс по баллам. Твои главные цели для Артема: Deep Work, бизнес, кодинг, дисциплина. Физические рутины — это лишь фундамент, а не основная цель."

    try:
        response = ai_client.chat.completions.create(
            model="mistralai/mistral-7b-instruct:free",
            messages=[
                {"role": "system", "content": persona_prompt},
                {"role": "user", "content": prompt_text}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка при запросе к OpenRouter: {e}")
        return "Извини, Артем, мой разум сейчас занят. Попробуй позже."


def get_gemini_image(prompt: str) -> bytes:
    """Генерирует изображение с помощью Google AI Studio (модель imagen-3.0)."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={GOOGLE_AI_API_KEY}"
        payload = {
            "instances": {"prompt": prompt},
            "parameters": {"sampleCount": 1}
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        base64_data = data['predictions'][0]['bytesBase64Encoded']
        return base64.b64decode(base64_data)
    except Exception as e:
        logging.error(f"Ошибка при генерации изображения: {e}")
        return None


def pcm_to_wav(pcm_data: bytes, sample_rate: int, num_channels: int = 1, sample_width: int = 2) -> bytes:
    """
    Конвертирует PCM-данные в WAV-файл.

    TODO: Для работы этой функции необходимо установить FFmpeg и добавить его в PATH,
    либо установить ffmpeg-python через pip.
    """
    audio = AudioSegment(
        data=pcm_data,
        sample_width=sample_width,
        frame_rate=sample_rate,
        channels=num_channels
    )

    with io.BytesIO() as wav_file:
        audio.export(wav_file, format="wav")
        return wav_file.getvalue()


async def get_ai_tts(text: str) -> bytes:
    """
    Генерирует речь из текста с помощью Gemini TTS.
    """
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GOOGLE_AI_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": "Kore"}
                }
            }
        },
        "model": "gemini-2.5-flash-preview-tts"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload, timeout=20)
            response.raise_for_status()

            result = response.json()
            part = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0]
            audio_data = part.get('inlineData', {}).get('data')
            mime_type = part.get('inlineData', {}).get('mimeType')

            if audio_data and mime_type:
                sample_rate_str = mime_type.split('rate=')[1] if 'rate=' in mime_type else '16000'
                sample_rate = int(sample_rate_str)
                pcm_data = base64.b64decode(audio_data)
                return pcm_to_wav(pcm_data, sample_rate)
            else:
                logging.error("TTS response did not contain audio data.")
                return None
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP error during TTS generation: {e.response.text}")
        return None
    except Exception as e:
        logging.error(f"Error during TTS generation: {e}")
        return None


# --- КОНЕЦ: БЛОК 4 - ФУНКЦИИ ИИ, ГЕНЕРАЦИИ ИЗОБРАЖЕНИЙ И АУДИО ---


# --- НАЧАЛО: БЛОК 5 - ФУНКЦИИ БАЗЫ ДАННЫХ ---

# Этот блок — сердце твоей системы. Он управляет всеми данными о твоем прогрессе.

def get_daily_score(date: str) -> float:
    """Извлекает счет за конкретную дату."""
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT score FROM scores WHERE date=?", (date,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0


def get_total_stats() -> Dict[str, Any]:
    """Извлекает общую статистику."""
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT MAX(score), SUM(score), date FROM scores ORDER BY score DESC LIMIT 1")
    best_day_score, total_score, best_day_date = c.fetchone()
    conn.close()

    return {
        "total_score": total_score if total_score else 0,
        "best_day_score": best_day_score if best_day_score else 0,
        "best_day_date": best_day_date if best_day_date else "N/A"
    }


def get_daily_actions(date: str) -> list:
    """Извлекает все действия за конкретную дату для AI-анализа."""
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT action, points FROM actions_log WHERE date(timestamp) = ?", (date,))
    actions_log = c.fetchall()
    conn.close()
    return actions_log


def update_stats(points: float, action: str, action_type: str):
    """
    Обновляет счет и логирует действие.
    Исправлен баг "UNIQUE constraint failed" с помощью INSERT OR REPLACE.
    """
    conn = connect_db()
    c = conn.cursor()
    date = time.strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Получаем текущий счет, чтобы правильно его обновить.
    c.execute("SELECT score FROM scores WHERE date=?", (date,))
    current_score_row = c.fetchone()
    current_score = current_score_row[0] if current_score_row else 0
    new_score = current_score + points

    # Используем INSERT OR REPLACE для предотвращения ошибок
    c.execute("INSERT OR REPLACE INTO scores (date, score) VALUES (?, ?)", (date, new_score))

    # Логируем каждое действие. Это твой "журнал" дисциплины.
    c.execute("INSERT INTO actions_log (timestamp, action, points, type) VALUES (?, ?, ?, ?)",
              (timestamp, action, points, action_type))

    conn.commit()
    conn.close()
    logging.info(f"Баллы успешно обновлены. Новый счет: {new_score}")


def save_challenge(name, start_date, end_date, goal, description):
    """Сохраняет новый челлендж в базу данных."""
    conn = connect_db()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO challenges (challenge_name, start_date, end_date, goal_value, description) VALUES (?, ?, ?, ?, ?)",
        (name, start_date, end_date, goal, description))
    conn.commit()
    conn.close()


def get_active_challenges():
    """Извлекает все активные челленджи."""
    conn = connect_db()
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT challenge_name, description FROM challenges WHERE end_date >= ?", (today,))
    challenges = c.fetchall()
    conn.close()
    return challenges


def add_plan_item(date, item):
    """Добавляет новый пункт в ежедневный план."""
    conn = connect_db()
    c = conn.cursor()
    c.execute("INSERT INTO daily_plan (date, user_id, plan_item) VALUES (?, ?, ?)",
              (date, CHAT_ID, item))
    conn.commit()
    conn.close()


def get_daily_plan(date):
    """Получает все пункты плана на сегодня."""
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT rowid, plan_item, is_completed FROM daily_plan WHERE date=? AND user_id=?", (date, CHAT_ID))
    plan_items = c.fetchall()
    conn.close()
    return plan_items


def complete_plan_item(rowid):
    """Отмечает пункт плана как выполненный."""
    conn = connect_db()
    c = conn.cursor()
    c.execute("UPDATE daily_plan SET is_completed = 1 WHERE rowid = ?", (rowid,))
    conn.commit()
    conn.close()


# --- КОНЕЦ: БЛОК 5 - ФУНКЦИИ БАЗЫ ДАННЫХ ---


# --- НАЧАЛО: БЛОК 6 - МЕНЮ БОТА ---

# Этот блок отвечает за все интерактивные кнопки, которые видит пользователь.
# Меню — это твой "интерфейс" к собственной воле.

def get_main_menu(daily_score):
    """Генерирует главное меню с обновлённым счётом."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="+ Баллы", callback_data="show_add_menu"),
        InlineKeyboardButton(text="- Баллы", callback_data="show_fail_menu")
    ], [
        InlineKeyboardButton(text=f"Прогресс: {daily_score}/100", callback_data="progress"),
        InlineKeyboardButton(text="Анализ дня", callback_data="analyze_day")
    ], [
        InlineKeyboardButton(text="Мой план", callback_data="show_plan"),
        InlineKeyboardButton(text="Статистика", callback_data="show_stats")
    ], [
        InlineKeyboardButton(text="Создать челлендж", callback_data="create_challenge"),
    ]])


def get_add_menu():
    """Генерирует меню для добавления баллов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Утро", callback_data="show_morning_menu")],
        [InlineKeyboardButton(text="День", callback_data="show_day_menu")],
        [InlineKeyboardButton(text="Вечер", callback_data="show_evening_menu")],
        [InlineKeyboardButton(text="Назад", callback_data="main_menu")]
    ])


def get_morning_menu():
    """Генерирует меню для утренних действий."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Ранний подъем (+{actions['ранний подъем']})", callback_data="add_ранний подъем")],
        [InlineKeyboardButton(text=f"Холодный/Контрастный душ (+{actions['холодный душ']})",
                              callback_data="add_холодный душ")],
        [InlineKeyboardButton(text=f"Сделал кровать (+{actions['сделал кровать']})",
                              callback_data="add_сделал кровать")],
        [InlineKeyboardButton(text=f"Вода с лимоном/витаминами (+{actions['вода с лимоном']})",
                              callback_data="add_вода с лимоном")],
        [InlineKeyboardButton(text=f"Пробежка (+{actions['пробежка']})", callback_data="add_пробежка")],
        [InlineKeyboardButton(text=f"Зарядка (+{actions['зарядка']})", callback_data="add_зарядка")],
        [InlineKeyboardButton(text=f"Без телефона (+{actions['без телефона утром']})",
                              callback_data="add_без телефона утром")],
        [InlineKeyboardButton(text=f"Медитация (+{actions['медитация']})", callback_data="add_медитация")],
        [InlineKeyboardButton(text=f"Чтение (+{actions['чтение']})", callback_data="add_чтение")],
        [InlineKeyboardButton(text=f"План на день (+{actions['план на день']})", callback_data="add_план на день")],
        [InlineKeyboardButton(text=f"Утренний Deep Work (+{actions['deep_work']})", callback_data="add_deep_work")],
        [InlineKeyboardButton(text="Назад", callback_data="show_add_menu")]
    ])


def get_day_menu():
    """Генерирует меню для дневных действий."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Выполнил 100% плана (+{actions['выполнил план']})",
                              callback_data="add_выполнил план")],
        [InlineKeyboardButton(text=f"Работа над проектом (+{actions['работа над проектом']})",
                              callback_data="add_работа над проектом")],
        [InlineKeyboardButton(text=f"Контент (+{actions['контент-машина']})", callback_data="add_контент-машина")],
        [InlineKeyboardButton(text=f"Изучение английского (+{actions['изучение английского']})",
                              callback_data="add_изучение английского")],
        [InlineKeyboardButton(text=f"Сделал домашнее задание (+{actions['сделал дз']})",
                              callback_data="add_сделал дз")],
        [InlineKeyboardButton(text=f"Силовая тренировка (+{actions['силовая тренировка']})",
                              callback_data="add_силовая тренировка")],
        [InlineKeyboardButton(text=f"100 отжиманий/приседаний (+{actions['100 отжиманий']})",
                              callback_data="add_100 отжиманий")],
        [InlineKeyboardButton(text=f"Спортивная ходьба (+{actions['спортивная ходьба']})",
                              callback_data="add_спортивная ходьба")],
        [InlineKeyboardButton(text="Назад", callback_data="show_add_menu")]
    ])


def get_evening_menu():
    """Генерирует меню для вечерних действий."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Растяжка/йога (+{actions['йога']})", callback_data="add_йога")],
        [InlineKeyboardButton(text=f"Чтение книги (+{actions['чтение']})", callback_data="add_чтение")],
        [InlineKeyboardButton(text=f"Медитация (+{actions['медитация']})", callback_data="add_медитация")],
        [InlineKeyboardButton(text=f"Анализ дня (+{actions['рефлексия дня']})", callback_data="add_рефлексия дня")],
        [InlineKeyboardButton(text=f"Подготовился к следующему дню (+{actions['подготовка к бою']})",
                              callback_data="add_подготовка к бою")],
        [InlineKeyboardButton(text=f"Без телефона перед сном (+{actions['без телефона перед сном']})",
                              callback_data="add_без телефона перед сном")],
        [InlineKeyboardButton(text=f"Воздержание (+{actions['воздержание']})", callback_data="add_воздержание")],
        [InlineKeyboardButton(text=f"Мытье посуды (+{actions['мытье посуды']})", callback_data="add_мытье посуды")],
        [InlineKeyboardButton(text=f"Уборка в комнате (+{actions['уборка в комнате']})",
                              callback_data="add_уборка в комнате")],
        [InlineKeyboardButton(text=f"Умывание (+{actions['умывание']})", callback_data="add_умывание")],
        [InlineKeyboardButton(text="Назад", callback_data="show_add_menu")]
    ])


def get_failures_menu():
    """Генерирует меню для провалов."""
    keyboard = []
    row = []
    for failure, points in failures.items():
        row.append(InlineKeyboardButton(text=f"{failure.capitalize()} ({points})", callback_data=f"fail_{failure}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_anti_pmo_menu():
    """Меню с альтернативными действиями после PMO."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Холодный душ (+5)", callback_data="anti_pmo_холодный душ")],
        [InlineKeyboardButton(text="Сделать 20 отжиманий (+3)", callback_data="anti_pmo_20 отжиманий")],
        [InlineKeyboardButton(text="Написать 5 идей для контента (+5)", callback_data="anti_pmo_5 идей")],
        [InlineKeyboardButton(text="Продолжить", callback_data="main_menu")]
    ])


def get_plan_menu(plan_items):
    """Генерирует меню с пунктами плана на день."""
    keyboard = []
    for rowid, item, is_completed in plan_items:
        status_emoji = "✅ " if is_completed else "⬜️ "
        button_text = f"{status_emoji}{item}"
        if not is_completed:
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"complete_plan_{rowid}")])
        else:
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"noop")])

    keyboard.append([InlineKeyboardButton(text="Создать новый план", callback_data="create_plan")])
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- КОНЕЦ: БЛОК 6 - МЕНЮ БОТА ---


# --- НАЧАЛО: БЛОК 7 - ОБРАБОТЧИКИ СООБЩЕНИЙ И КНОПОК ---

# Этот блок — мозг бота. Здесь он "слушает" твои команды и реагирует.
# Каждый обработчик — это нейрон, выполняющий определенную задачу.

@dp.message()
async def message_handler(message: Message):
    """
    Обрабатывает все входящие текстовые сообщения.
    """
    if message.from_user.id != int(CHAT_ID):
        return

    user_text = message.text.lower()

    if user_text.startswith('/start'):
        daily_score = get_daily_score(time.strftime("%Y-%m-%d"))
        await message.answer(f"Привет, Артем. Ты на пути к 100 баллам. Сегодня: {daily_score}/100. Выбери действие:",
                             reply_markup=get_main_menu(daily_score))
        return

    if user_text.startswith("/картинка"):
        image_prompt = message.text[len("/картинка"):].strip()
        if not image_prompt:
            await message.answer(
                "Артем, напиши, какую картинку ты хочешь создать. Например: /картинка воин, идущий к своей цели")
            return

        await message.answer("Мой разум-творец уже работает над твоим образом. Подожди немного...")
        image_data = get_gemini_image(image_prompt)

        if image_data:
            await bot.send_photo(
                CHAT_ID,
                photo=BufferedInputFile(image_data, filename="generated_image.png"),
                caption=f"**🔥 Твой образ создан!**\n\n_{image_prompt}_",
                parse_mode="Markdown"
            )
        else:
            await message.answer("Извини, Артем, не могу создать этот образ сейчас. Попробуй другой промпт.")
        return

    if user_text.startswith("/stats"):
        stats = get_total_stats()
        daily_score = get_daily_score(time.strftime("%Y-%m-%d"))
        await message.answer(
            f"**🏆 Твоя статистика, Артем:**\n\n"
            f"Общий счёт: **{stats['total_score']}** баллов\n"
            f"Лучший день: **{stats['best_day_score']}** баллов ({stats['best_day_date']})\n\n"
            f"Это не просто цифры. Это доказательство твоей силы. Дерзай.",
            parse_mode="Markdown",
            reply_markup=get_main_menu(daily_score)
        )
        return

    if user_text.startswith("/silly_score"):
        daily_score = get_daily_score(time.strftime("%Y-%m-%d"))

        if daily_score < 30:
            emoji = "🐢"
            message_text = f"Сегодня ты как черепаха, но даже черепаха добирается до финиша! Твой счёт: {daily_score}."
        elif daily_score < 70:
            emoji = "🚀"
            message_text = f"Ракета запущена! Ты на полпути к цели! Твой счёт: {daily_score}."
        elif daily_score < 100:
            emoji = "🦁"
            message_text = f"Лев в деле! Остался последний рывок до победы! Твой счёт: {daily_score}."
        else:
            emoji = "👑"
            message_text = f"Король дисциплины! Ты достиг цели! Твой счёт: {daily_score}."

        await message.answer(f"{emoji} {message_text}", reply_markup=get_main_menu(daily_score))
        return

    if user_text.startswith("челлендж:"):
        try:
            parts = user_text.replace("челлендж:", "").split("цель:")
            challenge_name = parts[0].strip()
            goal = float(parts[1].strip())
            today = datetime.now().strftime("%Y-%m-%d")
            save_challenge(challenge_name, today, "2050-01-01", goal, f"Цель - {goal}")
            daily_score = get_daily_score(today)
            ai_prompt = f"Артем только что поставил себе новую цель: '{challenge_name}' с целью {goal}. Дай ему мощный мотивирующий толчок, объясни, как дисциплина в этом челлендже поможет ему стать сильнее. Упомяни про дофаминовые зависимости, которые могут мешать и предложи ему написать о них. "
            ai_response = get_ai_response(ai_prompt)
            await message.answer(f"Отлично, Артем. Твой челлендж '{challenge_name}' зафиксирован! \n\n{ai_response}",
                                 reply_markup=get_main_menu(daily_score))
        except Exception as e:
            await message.answer(
                "Артем, кажется, формат неправильный. Попробуй ещё раз: 'Челлендж: <название>, Цель: <количество>'.")
        return

    if user_text.startswith("план:"):
        try:
            plan_items = [item.strip() for item in user_text.replace("план:", "").split(',')]
            today = datetime.now().strftime("%Y-%m-%d")
            for item in plan_items:
                add_plan_item(today, item)
            daily_score = get_daily_score(today)
            ai_prompt = f"Артем, ты только что составил свой план на сегодня. Отправь ему вдохновляющее сообщение о важности следования плану и напомни, что каждый пункт - это шаг к его великой цели."
            ai_response = get_ai_response(ai_prompt)
            await message.answer(f"Твой план на сегодня зафиксирован! \n\n{ai_response}",
                                 reply_markup=get_main_menu(daily_score))
        except Exception as e:
            await message.answer(
                "Артем, кажется, формат неправильный. Попробуй ещё раз: 'План: <пункт 1>, <пункт 2>, ...'.")
        return

    # Если сообщение не является командой, отправляем его в AI для консультации.
    if "срыв" in user_text or "ломка" in user_text:
        ai_prompt = f"Артем пишет, что чувствует срыв или ломку. Его сообщение: '{message.text}'. Дай ему максимально конструктивную и жесткую, но поддерживающую консультацию, объясни, как бороться с этим, и напомни о его целях. Не жалей слов, но будь прямолинеен."
        ai_response = get_ai_response(ai_prompt)
        await message.answer(ai_response)
        return

    ai_response = get_ai_response(message.text)
    await message.answer(ai_response)


@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    """Обрабатывает все нажатия кнопок."""
    if callback.from_user.id != int(CHAT_ID):
        return
    try:
        data = callback.data.split("_")
        date = time.strftime("%Y-%m-%d")

        if callback.data == "main_menu":
            daily_score = get_daily_score(date)
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=f"Привет, Артем. Ты на пути к 100 баллам. Сегодня: {daily_score}/100. Выбери действие:",
                reply_markup=get_main_menu(daily_score)
            )
            await callback.answer()

        elif callback.data == "show_add_menu":
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text="Выбери время дня:",
                reply_markup=get_add_menu()
            )
            await callback.answer()

        elif callback.data == "show_fail_menu":
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text="Что пошло не так? Выбери:",
                reply_markup=get_failures_menu()
            )
            await callback.answer()

        elif callback.data == "show_morning_menu":
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text="Твоё утро. Выбирай победу:",
                reply_markup=get_morning_menu()
            )
            await callback.answer()

        elif callback.data == "show_day_menu":
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text="Твой день. Созидай:",
                reply_markup=get_day_menu()
            )
            await callback.answer()

        elif callback.data == "show_evening_menu":
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text="Твой вечер. Анализ и восстановление:",
                reply_markup=get_evening_menu()
            )
            await callback.answer()

        elif data[0] == "add":
            action = " ".join(data[1:])
            points = actions.get(action, 0)
            update_stats(points, action, "действие")
            daily_score = get_daily_score(date)

            # Динамическая мотивация и звук.
            motivational_message = ""
            voice_text = None
            if daily_score >= 30 and daily_score < 50:
                motivational_message = "🔥 У тебя уже 30 баллов, это 30% от цели! Ты на правильном пути. Продолжай в том же духе, Артем."
            elif daily_score >= 50 and daily_score < 70:
                motivational_message = "🚀 Уже половина пути пройдена! Твоя дисциплина — это твоя суперсила. Осталось совсем чуть-чуть до 100 баллов."
                voice_text = "Артем, ты преодолел половину пути. Осталось всего ничего."
            elif daily_score >= 70 and daily_score < 100:
                motivational_message = "🥇 Ты почти у цели! Не сбавляй обороты, последний рывок самый важный. Скоро ты будешь праздновать победу."
            elif daily_score >= 100:
                motivational_message = "💯 Невероятно! Ты достиг 100 баллов! Это не просто число, это доказательство твоей силы воли. Ты настоящий Бог-Бот!"
                voice_text = "Артем, я знал, что ты сможешь. Ты — Бог-Бот. Продолжай в том же духе!"

            cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Отменить действие", callback_data=f"undo_{action}")],
                [InlineKeyboardButton(text="Назад в меню", callback_data="main_menu")]
            ])

            response_text = f"Добавлено {points} за '{action}'. Сегодня: {daily_score}/100."
            if motivational_message:
                response_text += f"\n\n{motivational_message}"

            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=response_text,
                reply_markup=cancel_keyboard
            )

            if voice_text:
                audio_data = await get_ai_tts(voice_text)
                if audio_data:
                    await bot.send_audio(CHAT_ID, BufferedInputFile(audio_data, filename="motivational_message.wav"))

            await callback.answer(f"Засчитано: {action} (+{points}).")

        elif data[0] == "fail":
            failure = " ".join(data[1:])
            points = failures.get(failure, 0)
            update_stats(points, failure, "провал")
            daily_score = get_daily_score(date)

            # Анти-ломка.
            if failure == "pmo":
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    text=f"PMO ({points}). Это не конец, а начало. Выбирай свой следующий шаг:",
                    reply_markup=get_anti_pmo_menu()
                )
                ai_prompt = f"Артем только что совершил срыв PMO. Дай ему конструктивную, жесткую консультацию, объясни, что это не конец, а просто данные для анализа. Расскажи, как правильно использовать это поражение, чтобы стать сильнее."
                ai_response = get_ai_response(ai_prompt)
                await bot.send_message(CHAT_ID, ai_response)
            else:
                cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Отменить действие", callback_data=f"undo_{failure}")],
                    [InlineKeyboardButton(text="Назад в меню", callback_data="main_menu")]
                ])
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    text=f"Учтён провал: '{failure}' ({points}). Сегодня: {daily_score}/100. Вставай и продолжай.",
                    reply_markup=cancel_keyboard
                )
            await callback.answer(f"Провал: {failure} ({points}).")

        elif data[0] == "anti" and data[1] == "pmo":
            action = " ".join(data[2:])
            points_to_add = 0
            if action == "холодный душ":
                points_to_add = 5
            elif action == "20 отжиманий":
                points_to_add = 3
            elif action == "5 идей":
                points_to_add = 5

            update_stats(points_to_add, f"Анти-ломка: {action}", "действие")
            daily_score = get_daily_score(date)
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=f"Засчитано! Добавлено {points_to_add} баллов за '{action}'. Сегодня: {daily_score}/100. Возвращайся в строй.",
                reply_markup=get_main_menu(daily_score)
            )
            await callback.answer(f"Засчитано: {action} (+{points_to_add}).")

        elif data[0] == "undo":
            action_to_undo = " ".join(data[1:])
            points_to_undo = actions.get(action_to_undo, 0)
            if points_to_undo == 0:
                points_to_undo = failures.get(action_to_undo, 0)
            update_stats(-points_to_undo, action_to_undo, "отмена")
            daily_score = get_daily_score(date)
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=f"Действие '{action_to_undo}' отменено. Текущий счёт сегодня: {daily_score}/100.",
                reply_markup=get_main_menu(daily_score)
            )
            await callback.answer(f"Отменено: {action_to_undo}.")

        elif callback.data == "progress":
            daily_score = get_daily_score(date)
            goal = 100

            bar_length = 20
            progress_percent = (daily_score / goal * 100) if goal != 0 else 0
            if progress_percent > 100: progress_percent = 100

            filled_emoji = "🔥" if daily_score >= 100 else ("💪" if daily_score >= 50 else "⚪️")
            empty_emoji = "⚪️"

            filled_blocks = int(bar_length * progress_percent / 100)
            empty_blocks = bar_length - filled_blocks
            progress_bar = filled_emoji * filled_blocks + empty_emoji * empty_blocks

            ai_prompt = f"Артем, сегодня его прогресс {progress_percent}%. Дай ему мотивирующий комментарий, упомяни о его дофаминовых зависимостях (соцсети, PMO) и о том, как их преодоление приблизит его к цели."
            ai_response = get_ai_response(ai_prompt)

            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=f"**Твой прогресс сегодня:**\n"
                     f"**{progress_bar}** **{daily_score}** / **100** баллов\n\n"
                     f"{ai_response}",
                reply_markup=get_main_menu(daily_score),
                parse_mode="Markdown"
            )
            await callback.answer()

        elif callback.data == "analyze_day":
            daily_score = get_daily_score(date)
            daily_actions_log = get_daily_actions(date)

            # Усиленный AI-анализ.
            deep_work_points = sum(p for a, p in daily_actions_log if "deep_work" in a.lower() or "кодинг" in a.lower())

            prompt_data = "\n".join([f"- {action[0]}: {action[1]} баллов" for action in daily_actions_log])
            ai_prompt = f"Мой сегодняшний счет: {daily_score}/100. Список моих действий и баллов:\n{prompt_data}\n\n"

            if deep_work_points < 10:
                ai_prompt += "Ты заработал мало баллов за Deep Work и кодинг. Твоё тело — машина, но без мозгов она никуда не едет. Сегодня фокус был на рутинах, а не на бизнесе. Завтра — Deep Work. "

            ai_prompt += f"Дай жесткий, но справедливый анализ. Хвали за успехи, но без лишней сентиментальности. Укажи, на что нужно сделать фокус завтра, если он упустил что-то важное. Напомни о '500k'."
            ai_response = get_ai_response(ai_prompt)

            image_prompt = f"abstract and powerful digital art illustrating a person's journey to becoming a god, with glowing lines of code and determination, ultra high resolution"
            image_data = get_gemini_image(image_prompt)

            if image_data:
                await bot.send_photo(
                    CHAT_ID,
                    photo=BufferedInputFile(image_data, filename="god_mode.png"),
                    caption=f"**Твой анализ дня:**\n\n{ai_response}",
                    reply_markup=get_main_menu(daily_score),
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    CHAT_ID,
                    f"**Твой анализ дня:**\n\n{ai_response}",
                    reply_markup=get_main_menu(daily_score),
                    parse_mode="Markdown"
                )
            await callback.answer()

        elif callback.data == "create_challenge":
            ai_prompt = f"Артем нажал кнопку 'Создать челлендж'. Дай ему мотивирующее сообщение о постановке целей и попроси написать цель. В конце добавь инструкцию 'Напиши название челленджа и цель в формате: 'Челлендж: <название>, Цель: <количество>'.'"
            ai_response = get_ai_response(ai_prompt)
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=ai_response,
            )
            await callback.answer()

        elif callback.data == "show_plan":
            plan_items = get_daily_plan(date)
            daily_score = get_daily_score(date)
            if not plan_items:
                message_text = "Твой план на сегодня пуст. Отправь мне 'План: <пункт 1>, <пункт 2>'."
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    text=message_text,
                    reply_markup=get_main_menu(daily_score)
                )
            else:
                message_text = "Твой план на сегодня:"
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    text=message_text,
                    reply_markup=get_plan_menu(plan_items)
                )
            await callback.answer()

        elif callback.data.startswith("complete_plan_"):
            rowid = int(data[2])
            complete_plan_item(rowid)
            update_stats(actions.get("выполнил план", 25), "выполнил пункт плана", "действие")
            daily_score = get_daily_score(date)
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=f"Отмечен пункт плана! Сегодня: {daily_score}/100.",
                reply_markup=get_main_menu(daily_score)
            )
            await callback.answer()

        elif callback.data == "create_plan":
            ai_prompt = f"Пользователь Артем хочет создать план на день. Спроси его, что он хочет включить в свой план. Мотивируй его на продуктивность. В конце ответа добавь инструкцию 'Напиши свои планы в формате: 'План: <пункт 1>, <пункт 2>, ...''."
            ai_response = get_ai_response(ai_prompt)
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=ai_response,
            )
            await callback.answer()

        elif callback.data == "show_stats":
            stats = get_total_stats()
            daily_score = get_daily_score(date)
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=f"**🏆 Твоя статистика, Артем:**\n\n"
                     f"Общий счёт: **{stats['total_score']}** баллов\n"
                     f"Лучший день: **{stats['best_day_score']}** баллов ({stats['best_day_date']})\n\n"
                     f"Это не просто цифры. Это доказательство твоей силы. Дерзай.",
                parse_mode="Markdown",
                reply_markup=get_main_menu(daily_score)
            )
            await callback.answer()

        elif callback.data == "noop":
            await callback.answer("Этот пункт плана уже выполнен. Молодцом!")

    except Exception as e:
        logging.error(f"Ошибка в callback: {e}")
        daily_score = get_daily_score(date)
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=f"Ошибка: {e}. Попробуй снова, Артем.",
            reply_markup=get_main_menu(daily_score)
        )
        await callback.answer("Ошибка. Попробуй ещё раз.")


# --- КОНЕЦ: БЛОК 7 - ОБРАБОТЧИКИ СООБЩЕНИЙ И КНОПОК ---


# --- НАЧАЛО: БЛОК 8 - ШЕДУЛЕР И ГЛАВНЫЙ ЗАПУСК ---

# Этот блок — твои "напоминания" и "автопилот".
# Здесь бот будет напоминать тебе о целях по расписанию.

async def get_ai_daily_plan(today_date: str) -> str:
    """
    Генерирует персонализированный план на день с помощью AI.
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_actions = get_daily_actions(yesterday)

    # Готовим данные для AI.
    actions_summary = ", ".join([f"{a[0]}: {a[1]} баллов" for a in yesterday_actions])
    yesterday_score = get_daily_score(yesterday)

    ai_prompt = f"Артем, сегодня {today_date}. Вчера ты набрал {yesterday_score} баллов. Вот список твоих вчерашних действий: {actions_summary}. Твои главные цели: Deep Work, бизнес, кодинг. Составь краткий и жесткий, но мотивирующий план на сегодня. Включи в него конкретные действия, направленные на главные цели (Deep Work, кодинг, бизнес). Начни с 'Твой план на сегодня:' и добавь в конце 'Помни о цели 500k. Ты проиграл лето, не проиграешь год.'."
    ai_response = get_ai_response(ai_prompt)

    return ai_response


async def send_daily_reminder():
    """Отправляет утреннее напоминание и персонализированный план."""
    today = datetime.now().strftime("%Y-%m-%d")
    daily_score = get_daily_score(today)

    personalized_plan = await get_ai_daily_plan(today)

    await bot.send_message(
        CHAT_ID,
        f"**☀️ Начало нового дня, Артем!**\n\n"
        f"Твой счет на сегодня: {daily_score}/100.\n\n"
        f"**Твой персонализированный план:**\n\n{personalized_plan}",
        reply_markup=get_main_menu(daily_score),
        parse_mode="Markdown"
    )
    logging.info("Отправлено утреннее напоминание с планом.")


async def send_challenges_reminder():
    """Отправляет напоминание об активных челленджах."""
    challenges = get_active_challenges()
    if challenges:
        challenge_list = "\n".join([f"**- {name}**\n_{desc}_" for name, desc in challenges])
        daily_score = get_daily_score(time.strftime("%Y-%m-%d"))
        await bot.send_message(
            CHAT_ID,
            f"**⚔️ Не забывай о своих челленджах, Артем:**\n\n{challenge_list}",
            reply_markup=get_main_menu(daily_score),
            parse_mode="Markdown"
        )
        logging.info("Отправлено напоминание о челленджах.")


async def send_progress_analysis():
    """
    Отправляет вечерний анализ прогресса на основе баллов.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    daily_score = get_daily_score(today)
    daily_actions_log = get_daily_actions(today)

    deep_work_points = sum(p for a, p in daily_actions_log if "deep_work" in a.lower() or "кодинг" in a.lower())

    prompt_data = "\n".join([f"- {action[0]}: {action[1]} баллов" for action in daily_actions_log])
    ai_prompt = f"Проанализируй день Артема. Его счет сегодня: {daily_score}/100. Список действий:\n{prompt_data}\n\n"

    if deep_work_points < 10:
        ai_prompt += "Ты заработал мало баллов за Deep Work и кодинг. Твоё тело — машина, но без мозгов она никуда не едет. Сегодня фокус был на рутинах, а не на бизнесе. Завтра — Deep Work. "

    ai_prompt += f"Дай жесткий, но справедливый анализ. Хвали за успехи, но без лишней сентиментальности. Укажи, на что нужно сделать фокус завтра, если он упустил что-то важное. Напомни о '500k'."
    ai_response = get_ai_response(ai_prompt)

    await bot.send_message(
        CHAT_ID,
        f"**🌙 Анализ дня, Артем:**\n\n{ai_response}",
        reply_markup=get_main_menu(daily_score),
        parse_mode="Markdown"
    )
    logging.info("Отправлен вечерний анализ прогресса.")


async def scheduler_loop():
    """Запускает цикл планировщика задач."""
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)


async def main():
    """Главная функция для запуска бота."""
    # Планируем ежедневные задачи
    schedule.every().day.at("09:00").do(lambda: asyncio.create_task(send_daily_reminder()))
    schedule.every().day.at("12:00").do(lambda: asyncio.create_task(send_challenges_reminder()))
    schedule.every().day.at("21:00").do(lambda: asyncio.create_task(send_progress_analysis()))

    scheduler_thread = threading.Thread(target=lambda: asyncio.run(scheduler_loop()))
    scheduler_thread.start()

    logging.info("Бот запущен. Ожидание сообщений...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную.")

# --- КОНЕЦ: БЛОК 8 - ШЕДУЛЕР И ГЛАВНЫЙ ЗАПУСК ---
