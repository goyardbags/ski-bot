# Ski Bot - Crypto Metrics Discord Bot

A Discord bot that provides real-time cryptocurrency metrics with a skiing theme. Features 24-hour change tracking, Fear & Greed Index, and fun skiing-themed messages.

## Features

- **Real-time BTC price** in bot status
- **Funding rates** for any cryptocurrency
- **Open Interest** data with 24h tracking
- **Volume analysis** (spot & perpetual)
- **Fear & Greed Index** from Alternative.me
- **24-hour change tracking** using local storage
- **Skiing-themed messages** for a fun experience
- **Clean, lowercase UI** for minimal aesthetic

## Commands

- `sb fear` - Get current Fear & Greed Index
- `sb fund [symbol]` - Get current funding rate (default: BTC)
- `sb oi [symbol]` - Get open interest data with 24h change
- `sb vol [symbol]` - Get spot and perpetual volume with 24h change
- `sb all [symbol]` - Get all metrics with 24h changes
- `sb help` - Show help message

## Project Structure

```
ski-bot/
├── src/                    # Source code
│   └── main_storage.py     # Main bot file
├── data/                   # Data files
│   ├── crypto_data.json    # 24h tracking data
│   ├── syn.txt            # Skiing action words
│   └── trails.txt         # Trail names
├── config/                 # Configuration
│   └── env.example        # Environment template
├── run.py                 # Bot launcher
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ski-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp config/env.example .env
   # Edit .env with your Discord bot token and channel ID
   ```

4. **Run the bot**
   ```bash
   python run.py
   ```

## Environment Variables

Create a `.env` file in the root directory:

```env
DISCORD_TOKEN=your_discord_bot_token
CHANNEL_ID=your_channel_id
```

## Dependencies

- `discord.py` - Discord bot framework
- `okx-sdk` - OKX exchange API
- `aiohttp` - Async HTTP client
- `python-dotenv` - Environment variable management

## Features

### 24-Hour Tracking
The bot stores metrics locally and calculates 24-hour percentage changes. Data is automatically cleaned up after 48 hours.

### Skiing Theme
Random skiing messages like "shredding devil's elbow..." appear when fetching data, adding personality to the bot.

### Real-Time Status
The bot's status shows the current BTC price, updating every minute.

### Clean UI
All text is lowercase for a minimal, modern aesthetic.

## API Sources

- **OKX Exchange** - Funding rates, open interest, volume data
- **Alternative.me** - Fear & Greed Index

## License

This project is for educational purposes. 