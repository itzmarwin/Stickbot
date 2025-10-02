# Sticker Kang Bot 🎨

A powerful Telegram bot built with Aiogram v3.x that allows users to create and manage their own personal sticker packs by adding images, GIFs, stickers, and videos.

## Features ✨

- **Multi-Format Support**: Add images, GIFs, stickers, and videos to your pack
- **Automatic Conversion**: 
  - Images → WebP format (512x512)
  - Videos/GIFs → WebM format (optimized for Telegram)
- **Personal Packs**: Each user gets their own unique sticker pack
- **Custom Pack Names**: Users can choose their own pack names
- **Size Validation**: Automatic rejection of videos over 4MB
- **Real-time Logging**: Owner receives notifications about new users and bot activity
- **MongoDB Storage**: Reliable data persistence with async operations

## Requirements 📋

- Python 3.8+
- MongoDB
- FFmpeg (for video conversion)
- Telegram Bot Token

## Installation 🚀

1. **Clone the repository**
```bash
git clone <repository-url>
cd sticker-kang-bot
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Install FFmpeg**
   - **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
   - **macOS**: `brew install ffmpeg`
   - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

5. **Setup environment variables**
```bash
cp .env.example .env
# Edit .env with your configuration
```

6. **Configure MongoDB**
   - Install MongoDB locally or use MongoDB Atlas
   - Update `MONGO_URI` in `.env`

## Configuration ⚙️

Edit `.env` file with your credentials:

```env
BOT_TOKEN=your_bot_token_from_botfather
BOT_USERNAME=YourBotUsername
OWNER_ID=your_telegram_user_id
LOG_GROUP_ID=your_logger_group_id
MONGO_URI=mongodb://localhost:27017
DATABASE_NAME=sticker_kang_bot
```

### Getting Your Configuration:

1. **BOT_TOKEN**: Create a bot with [@BotFather](https://t.me/botfather)
2. **BOT_USERNAME**: Your bot's username (without @)
3. **OWNER_ID**: Your Telegram user ID (get from [@userinfobot](https://t.me/userinfobot))
4. **LOG_GROUP_ID**: Create a group, add your bot, and get group ID (use [@RawDataBot](https://t.me/RawDataBot) to get group ID)

## Usage 🎯

1. **Start the bot**
```bash
python main.py
```

2. **Bot Commands**
   - `/start` - Start the bot and see welcome message
   - `/kang` - Add media to your sticker pack
   - `/packs` - View your sticker pack information
   - `/help` - Get help and instructions
   - `/stats` - View bot statistics (owner only)

## How It Works 🔧

### Creating a Pack

1. User replies to an image/GIF/sticker/video with `/kang`
2. If first time, bot asks for pack name
3. User provides name (e.g., "devil pack @itzdevil")
4. Bot appends its username: "devil pack @itzdevil ~ @BotUsername"
5. Pack is created with the first sticker added

### Pack Name Format

```
{User Provided Name} ~ @BotUsername
```

**Example:**
- Input: `devil pack @itzdevil`
- Bot Username: `Stickerkangbot`
- Final: `devil pack @itzdevil ~ @Stickerkangbot`

### Adding Stickers

- Reply to any supported media with `/kang`
- Bot automatically converts and adds to your pack
- Supported: Images (JPG, PNG), GIFs, Stickers, Videos (<4MB)

## Project Structure 📁

```
sticker-kang-bot/
├── main.py                 # Entry point
├── config.py              # Configuration
├── database.py            # MongoDB operations
├── templates.py           # Message templates
├── requirements.txt       # Dependencies
├── .env.example          # Environment template
├── .gitignore            # Git ignore rules
├── README.md             # Documentation
│
├── handlers/             # Feature handlers
│   ├── __init__.py
│   ├── start.py         # Start & help commands
│   ├── kang.py          # Main kang functionality
│   ├── packs.py         # Pack management
│   ├── logger.py        # Activity logging
│   └── misc.py          # Miscellaneous handlers
│
└── utils/               # Utility modules
    ├── __init__.py
    ├── converters.py    # Media conversion
    ├── fsm_states.py    # FSM state definitions
    └── helpers.py       # Helper functions
```

## Media Processing 🎬

### Images
- Converted to WebP format
- Resized to 512x512 (maintaining aspect ratio)
- Transparent background support

### Videos/GIFs
- Converted to WebM format
- Limited to 3 seconds
- 512x512 resolution
- VP9 codec
- Max 4MB file size

### Stickers
- Directly copied to pack
- Preserves original format

## Database Schema 💾

### Users Collection
```json
{
  "user_id": 123456789,
  "username": "username",
  "first_name": "First Name",
  "created_at": "2025-01-01T00:00:00",
  "has_started": true
}
```

### Sticker Packs Collection
```json
{
  "user_id": 123456789,
  "pack_name": "My Pack ~ @BotUsername",
  "short_name": "my_pack_123456789_by_Bot",
  "pack_link": "https://t.me/addstickers/...",
  "sticker_count": 5,
  "created_at": "2025-01-01T00:00:00"
}
```

## Logging System 📝

The bot automatically logs:
- New user registrations
- Bot added to groups
- Bot removed from groups
- Errors and warnings

All logs are sent to the owner's private chat.

## Error Handling 🛡️

- Automatic cleanup of temporary files
- User-friendly error messages
- Detailed logging for debugging
- Graceful failure handling

## Contributing 🤝

Contributions are welcome! Please feel free to submit a Pull Request.

## License 📄

This project is licensed under the MIT License.

## Support 💬

For issues and questions:
- Open an issue on GitHub
- Contact the bot owner

## Acknowledgments 🙏

- Built with [Aiogram 3.x](https://docs.aiogram.dev/)
- Database: [MongoDB](https://www.mongodb.com/)
- Media processing: [Pillow](https://pillow.readthedocs.io/) & [FFmpeg](https://ffmpeg.org/)

---

Made with ❤️ by the community
