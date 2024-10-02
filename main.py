#!/usr/bin/env python3

import os
from dotenv import load_dotenv # type: ignore
import subprocess
import requests # type: ignore
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, Bot # type: ignore
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler # type: ignore
import asyncio
import threading

# Load environment variables from .env file
load_dotenv()

# Replace hardcoded values with environment variables
API_URL = os.getenv("API_URL")
LIVE_STREAM_URL = os.getenv("LIVE_STREAM_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
DB_NAME = os.getenv("DB_NAME", "user_clicks.db")
CHAT_ID = int(os.getenv("CHAT_ID"))

current_video = None
current_process = None

def get_duration(m3u8_url):
    cmd = [
        "ffprobe",
        "-headers", "Referer: https://emturbovid.com",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        m3u8_url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    duration = result.stdout.strip()
    
    if not duration:
        return None  # Return None if duration couldn't be obtained
    
    try:
        float(duration)  # Check if the duration is a valid float
        return duration
    except ValueError:
        return None  # Return None if duration is not a valid number

def stream_video(m3u8_url, duration):
    global current_process
    cmd = [
        "ffmpeg",
        "-headers", "Referer: https://emturbovid.com",
        "-re",
        "-i", m3u8_url,
        "-flags", "+low_delay",
        "-map", "0:0",
        "-codec:v", "copy",
        "-map", "0:1",
        "-codec:a", "copy",
        "-t", duration,
        "-shortest",
        "-f", "flv",
        LIVE_STREAM_URL
    ]
    current_process = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
    current_process.wait()  # Wait for the process to finish
    asyncio.run_coroutine_threadsafe(video_finished(), asyncio.get_event_loop())

async def video_finished():
    global current_video
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    try:
        response = requests.get(API_URL)
        videos = response.json()
        
        if not videos:
            print("No videos available. Waiting for 60 seconds before trying again.")
            await asyncio.sleep(60)
            await video_finished()
            return
        
        current_video = videos[0]
        m3u8_url = current_video['m3u8_url']
        duration = get_duration(m3u8_url)
        
        if duration is None:
            print("The selected video cannot be played. Trying the next one.")
            videos.pop(0)
            if not videos:
                print("No playable videos available. Waiting for 60 seconds before trying again.")
                await asyncio.sleep(60)
                await video_finished()
                return
            current_video = videos[0]
            m3u8_url = current_video['m3u8_url']
            duration = get_duration(m3u8_url)
        
        # Get video information
        video_title = current_video['title']
        video_image = current_video['bg']
        code = current_video['movieInfo']['code']
        
        # Create an inline keyboard with a "Next Video" button
        keyboard = [[InlineKeyboardButton("Next Video", callback_data='next_video')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send message with video information
        await bot.send_photo(
            chat_id=CHAT_ID,
            photo=video_image,
            caption=f"Now playing:\n\n{video_title}\n\nDuration: {duration} seconds\n\nCode: {code}",
            reply_markup=reply_markup
        )
        
        print(f"Starting next video: {video_title}")
        threading.Thread(target=stream_video, args=(m3u8_url, duration), daemon=True).start()
    
    except Exception as e:
        print(f"An error occurred while fetching the next video: {str(e)}")
        print("Waiting for 60 seconds before trying again.")
        await asyncio.sleep(60)
        await video_finished()

def stop_current_video():
    global current_process
    if current_process:
        current_process.terminate()
        current_process.wait()
        current_process = None

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_clicks
                 (user_id INTEGER, last_click TIMESTAMP)''')
    conn.commit()
    conn.close()

def can_user_click(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT last_click FROM user_clicks WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if result:
        last_click = datetime.fromisoformat(result[0])
        if datetime.now() - last_click < timedelta(minutes=15):
            conn.close()
            return False
    
    c.execute("INSERT OR REPLACE INTO user_clicks VALUES (?, ?)", 
              (user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True

async def start(update: Update, context: CallbackContext) -> None:
    global current_video
    
    if current_video:
        video_title = current_video['title']
        video_image = current_video['bg']
        code = current_video['movieInfo']['code']
        duration = get_duration(current_video['m3u8_url'])
        
        # Create an inline keyboard with a "Next Video" button
        keyboard = [[InlineKeyboardButton("Next Video", callback_data='next_video')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_photo(
            photo=video_image,
            caption=f"Currently playing:\n\n{video_title}\n\nDuration: {duration} seconds\n\nCode: {code}",
            reply_markup=reply_markup
        )
    else:
        keyboard = [[InlineKeyboardButton("Play Video", callback_data='next_video')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            'No video is currently playing. Click the "Play Video" button to start.',
            reply_markup=reply_markup
        )

async def play_next_video(update: Update, context: CallbackContext) -> None:
    global current_video
    
    user_id = update.effective_user.id
    
    # Determine whether this is a message or a callback query
    message = update.message or update.callback_query.message
    
    # Check if the user is authorized or if they can click
    if user_id != AUTHORIZED_USER_ID and not can_user_click(user_id):
        await message.reply_text("You can only request a new video every 15 minutes. Please try again later.")
        return
    
    try:
        # Stop the current video if it's playing
        stop_current_video()

        response = requests.get(API_URL)
        videos = response.json()
        
        if not videos:
            await message.reply_text("No videos available at the moment. Please try again later.")
            return
        
        current_video = videos[0]
        m3u8_url = current_video['m3u8_url']
        
        # Get video title, image URL, and code
        video_title = current_video['title']
        video_image = current_video['bg']
        code = current_video['movieInfo']['code']
        
        print(f"Starting next video: {video_title}")
        print(f"m3u8_url: {m3u8_url}")
        print(f"code: {code}")
        
        duration = get_duration(m3u8_url)
        
        print(f"Duration: {duration}")
        if duration is None:
            await message.reply_text("The selected video cannot be played. Trying the next one...")
            return
        
        # Create an inline keyboard with a "Next Video" button
        keyboard = [[InlineKeyboardButton("Next Video", callback_data='next_video')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send image with caption and the inline keyboard
        await message.reply_photo(
            photo=video_image,
            caption=f"Playing next video:\n\n{video_title}\n\nDuration: {duration} seconds\n\nCode: {code}",
            reply_markup=reply_markup
        )
        
        # Start streaming in a separate thread to avoid blocking the bot
        import threading
        threading.Thread(target=stream_video, args=(m3u8_url, duration), daemon=True).start()
    
    except Exception as e:
        await message.reply_text(f"An error occurred: {str(e)}")

async def next_video(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    
    await play_next_video(update, context)

async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if query.data == 'next_video':
        if user_id != AUTHORIZED_USER_ID and not can_user_click(user_id):
            await query.answer("You can only request a new video every 15 minutes. Please try again later.", show_alert=True)
        else:
            await query.answer("Processing your request...")
            await play_next_video(update, context)

async def stop_video(update: Update, context: CallbackContext) -> None:
    global current_process
    user_id = update.effective_user.id
    
    if user_id != AUTHORIZED_USER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    
    if current_process:
        stop_current_video()
        await update.message.reply_text("Video playback has been stopped.")
    else:
        await update.message.reply_text("No video is currently playing.")

async def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Define the commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("next", "Play the next video"),
        BotCommand("stop", "Stop the current video")
    ]

    # Set the commands
    await application.bot.set_my_commands(commands)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("next", next_video))
    application.add_handler(CommandHandler("stop", stop_video))
    application.add_handler(CallbackQueryHandler(button))

    await application.initialize()
    await application.start()
    print("Bot started. Press Ctrl+C to stop.")
    
    try:
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        # Keep the program running
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await application.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped gracefully")