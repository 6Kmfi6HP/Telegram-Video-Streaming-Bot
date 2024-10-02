# Telegram Video Streaming Bot

This is a Telegram bot that streams videos from an API to a live stream URL. It allows users to control video playback and get information about the currently playing video.

## Features

- Stream videos from an API to a live stream URL
- Display current video information (title, duration, code)
- Allow users to request the next video
- Limit how often users can request new videos
- Authorized user can stop video playback
- Inline keyboard for easy interaction

## Setup

1. Clone this repository
2. Install required dependencies:
   ```
   pip install python-telegram-bot python-dotenv requests
   ```
3. Create a `.env` file with the following variables:
   ```
   API_URL=<your_api_url>
   LIVE_STREAM_URL=<your_live_stream_url>
   TELEGRAM_BOT_TOKEN=<your_bot_token>
   AUTHORIZED_USER_ID=<authorized_user_id>
   DB_NAME=user_clicks.db
   CHAT_ID=<chat_id>
   ```
4. Run the bot:
   ```
   python main.py
   ```

## Usage

- `/start` - Start the bot and see current video info
- `/next` - Play the next video (authorized user only)
- `/stop` - Stop current video playback (authorized user only)
- Use the "Next Video" inline button to request the next video

## Requirements

- Python 3.7+
- FFmpeg
- python-telegram-bot
- requests
- python-dotenv

## License

This project is licensed under the MIT License.

Let me 知道如果你需要对 README 做任何修改或添加。
