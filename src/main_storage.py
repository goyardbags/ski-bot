import discord
from discord.ext import commands, tasks
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import json
import logging
import aiohttp
import random
from okx import OkxRestClient
import re
import tweepy

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataStorage:
    def __init__(self, filename="data/crypto_data.json"):
        self.filename = filename
        # Ensure data directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        self.data = self.load_data()
    
    def load_data(self):
        """Load data from JSON file"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r') as f:
                    return json.load(f)
            else:
                return {}
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return {}
    
    def save_data(self):
        """Save data to JSON file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)
            with open(self.filename, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving data: {e}")
            # Don't crash if we can't save data
    
    def update_metric(self, symbol, metric_type, value, timestamp=None):
        """Update a metric for a symbol"""
        try:
            if timestamp is None:
                timestamp = datetime.now().isoformat()
            
            if symbol not in self.data:
                self.data[symbol] = {}
            
            if metric_type not in self.data[symbol]:
                self.data[symbol][metric_type] = []
            
            # Add new data point
            self.data[symbol][metric_type].append({
                'value': value,
                'timestamp': timestamp
            })
            
            # Keep only last 48 hours of data (for 24h comparison)
            cutoff_time = datetime.now() - timedelta(hours=48)
            self.data[symbol][metric_type] = [
                point for point in self.data[symbol][metric_type]
                if datetime.fromisoformat(point['timestamp']) > cutoff_time
            ]
            
            self.save_data()
        except Exception as e:
            logger.error(f"Error updating metric: {e}")
    
    def get_24h_change(self, symbol, metric_type):
        """Calculate 24h change for a metric"""
        try:
            if symbol not in self.data or metric_type not in self.data[symbol]:
                return None, None
            
            data_points = self.data[symbol][metric_type]
            if len(data_points) < 2:
                return None, None
            
            # Get current value (most recent)
            current_value = data_points[-1]['value']
            
            # Find value from 24 hours ago
            target_time = datetime.now() - timedelta(hours=24)
            historical_value = None
            
            for point in reversed(data_points[:-1]):  # Skip the most recent
                point_time = datetime.fromisoformat(point['timestamp'])
                if point_time <= target_time:
                    historical_value = point['value']
                    break
            
            if historical_value is None or historical_value == 0:
                return current_value, None
            
            # Calculate percentage change
            change_percent = ((current_value - historical_value) / historical_value) * 100
            return current_value, change_percent
        except Exception as e:
            logger.error(f"Error calculating 24h change: {e}")
            return None, None

class CryptoBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        if hasattr(intents, 'message_content'):
            intents.message_content = True
        super().__init__(command_prefix='sb ', intents=intents)
        
        # Initialize OKX client and data storage
        self.okx_client = OkxRestClient()
        self.storage = DataStorage()
        
        # Load skiing messages
        self.syn_messages = self.load_messages('data/syn.txt')
        self.trail_messages = self.load_messages('data/trails.txt')
        
        channel_id_str = os.getenv('CHANNEL_ID')
        if channel_id_str is None:
            raise ValueError("CHANNEL_ID environment variable is not set")
        self.channel_id = int(channel_id_str)
        
        # Remove default help command
        self.remove_command('help')
    
    def load_messages(self, filename):
        """Load messages from a text file"""
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    messages = [line.strip() for line in f.readlines() if line.strip()]
                logger.info(f"Loaded {len(messages)} messages from {filename}")
                return messages
            else:
                logger.warning(f"File {filename} not found, using default messages")
                return []
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            return []
    
    def get_random_message(self):
        """Get a random skiing message"""
        logger.info(f"syn_messages: {len(self.syn_messages)}, trail_messages: {len(self.trail_messages)}")
        
        if self.syn_messages and self.trail_messages:
            syn_word = random.choice(self.syn_messages)
            trail_word = random.choice(self.trail_messages)
            message = f"{syn_word.lower()} {trail_word.lower()}..."
            logger.info(f"Combined message: {message}")
            return message
        elif self.syn_messages:
            message = f"{random.choice(self.syn_messages).lower()}..."
            logger.info(f"Syn message: {message}")
            return message
        elif self.trail_messages:
            message = f"{random.choice(self.trail_messages).lower()}..."
            logger.info(f"Trail message: {message}")
            return message
        else:
            logger.warning("No messages loaded, using fallback")
            return "carving fresh powder..."
        
    async def setup_hook(self):
        """Called when the bot is starting up"""
        await self.add_cog(CryptoCog(self))
        
    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f'{self.user} has connected to Discord!')
        
        # Start the status update task
        self.update_status_task.start()
        
        # Set initial bot status
        await self.update_status()
    
    @tasks.loop(minutes=5)  # Update every 5 minutes instead of 1
    async def update_status_task(self):
        """Update bot status with current BTC price"""
        try:
            await self.update_status()
        except Exception as e:
            logger.error(f"Error in status update task: {e}")
            # Set fallback status if update fails
            try:
                await self.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching, 
                        name="crypto metrics"
                    )
                )
            except Exception as e2:
                logger.error(f"Error setting fallback status: {e2}")
    
    async def update_status(self):
        """Update bot status with current BTC price"""
        try:
            # Get BTC price
            ticker = self.okx_client.public.get_ticker(instId="BTC-USDT")
            
            if ticker and 'data' in ticker and ticker['data']:
                btc_price = float(ticker['data'][0].get('last', 0))
                price_formatted = f"${btc_price:,.0f}"
                
                # Set bot status with BTC price
                await self.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching, 
                        name=f"btc {price_formatted}"
                    )
                )
            else:
                # Fallback if price fetch fails
                await self.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching, 
                        name="crypto metrics"
                    )
                )
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            # Fallback status
            await self.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching, 
                    name="crypto metrics"
                )
            )
    
    def format_number(self, num):
        """Format large numbers with K, M, B suffixes"""
        if num >= 1e9:
            return f"{num/1e9:.2f}B"
        elif num >= 1e6:
            return f"{num/1e6:.2f}M"
        elif num >= 1e3:
            return f"{num/1e3:.2f}K"
        else:
            return f"{num:.2f}"

TWITTER_TRACK_FILE = 'data/twitter_profiles.json'

def load_tracked_profiles():
    if os.path.exists(TWITTER_TRACK_FILE):
        with open(TWITTER_TRACK_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_tracked_profiles(profiles):
    os.makedirs(os.path.dirname(TWITTER_TRACK_FILE), exist_ok=True)
    with open(TWITTER_TRACK_FILE, 'w') as f:
        json.dump(profiles, f, indent=2)

class TwitterTracker:
    def __init__(self):
        self.profiles = load_tracked_profiles()
        self.bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
        self.client = tweepy.Client(bearer_token=self.bearer_token, wait_on_rate_limit=True)

    def add_profile(self, name, url):
        self.profiles[name] = {'url': url, 'last_tweet_id': None}
        save_tracked_profiles(self.profiles)

    def remove_profile(self, name):
        if name in self.profiles:
            del self.profiles[name]
            save_tracked_profiles(self.profiles)

    def list_profiles(self):
        return self.profiles

    def update_last_tweet(self, name, tweet_id):
        if name in self.profiles:
            self.profiles[name]['last_tweet_id'] = tweet_id
            save_tracked_profiles(self.profiles)

    def get_last_tweet_id(self, name):
        return self.profiles.get(name, {}).get('last_tweet_id')

    def get_user_id(self, username):
        try:
            user = self.client.get_user(username=username)
            if user and user.data:
                return user.data.id
        except Exception as e:
            logger.error(f"Error fetching user id for {username}: {e}")
        return None

    def get_latest_tweet(self, username):
        try:
            user_id = self.get_user_id(username)
            if not user_id:
                return None, None
            tweets = self.client.get_users_tweets(id=user_id, max_results=5, exclude=['replies', 'retweets'])
            if tweets and tweets.data:
                tweet = tweets.data[0]
                return tweet.id, tweet.text
        except Exception as e:
            logger.error(f"Error fetching latest tweet for {username}: {e}")
        return None, None

class CryptoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twitter_tracker = TwitterTracker()
    
    @commands.command(name='fear')
    async def get_fear_greed(self, ctx):
        """Get current Crypto Fear & Greed Index"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.alternative.me/fng/') as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data and 'data' in data and data['data']:
                            fear_data = data['data'][0]
                            value = int(fear_data.get('value', 0))
                            classification = fear_data.get('value_classification', 'Unknown')
                            timestamp = fear_data.get('timestamp', '')
                            
                            # Store current fear value for tracking
                            self.bot.storage.update_metric('MARKET', 'fear_greed', value)
                            
                            # Get 24h change from local storage
                            current_value, change_percent = self.bot.storage.get_24h_change('MARKET', 'fear_greed')
                            
                            if change_percent is not None:
                                change_str = f" ({change_percent:+.1f}%)"
                            else:
                                change_str = " (tracking)"
                            
                            # Parse timestamp
                            if timestamp:
                                try:
                                    dt = datetime.fromtimestamp(int(timestamp))
                                    time_str = dt.strftime("%Y-%m-%d %H:%M UTC")
                                except:
                                    time_str = "unknown"
                            else:
                                time_str = "unknown"
                            
                            response = f"{self.bot.get_random_message()}\n\n**fear & greed index**\n"
                            response += f"value: {value}/100 {change_str}\n"
                            response += f"classification: {classification.lower()}\n"
                            response += f"updated: {time_str}"
                            
                            await ctx.send(response)
                        else:
                            await ctx.send(f"{self.bot.get_random_message()}\nno fear & greed data available")
                    else:
                        await ctx.send(f"{self.bot.get_random_message()}\nerror fetching fear & greed data: http {response.status}")
                        
        except Exception as e:
            await ctx.send(f"{self.bot.get_random_message()}\nerror fetching fear & greed data: {str(e)}")
    
    @commands.command(name='fund')
    async def get_funding_rates(self, ctx, symbol='BTC'):
        """Get current funding rates for a cryptocurrency"""
        try:
            # Get funding rate for the symbol
            funding_data = self.bot.okx_client.public.get_funding_rate(instId=f"{symbol.upper()}-USDT-SWAP")
            
            if not funding_data or 'data' not in funding_data or not funding_data['data']:
                await ctx.send(f"{self.bot.get_random_message()}\nno funding rate data found for {symbol.upper()}")
                return
            
            data = funding_data['data'][0]
            funding_rate = float(data.get('fundingRate', 0)) * 100  # Convert to percentage
            next_funding_time = data.get('nextFundingTime', '')
            inst_id = data.get('instId', '')
            
            # Parse next funding time
            if next_funding_time:
                try:
                    dt = datetime.fromtimestamp(int(next_funding_time) / 1000)
                    next_funding_str = dt.strftime("%Y-%m-%d %H:%M UTC")
                except:
                    next_funding_str = "unknown"
            else:
                next_funding_str = "unknown"
            
            response = f"{self.bot.get_random_message()}\n\n**{symbol.upper()} funding rate**\n"
            response += f"rate: {funding_rate:.4f}%\n"
            response += f"next funding: {next_funding_str}\n"
            response += f"instrument: {inst_id}"
            
            await ctx.send(response)
            
        except Exception as e:
            await ctx.send(f"{self.bot.get_random_message()}\nerror fetching funding rate: {str(e)}")
    
    @commands.command(name='oi')
    async def get_open_interest(self, ctx, symbol='BTC'):
        """Get open interest for a cryptocurrency"""
        try:
            # Get open interest data
            oi_data = self.bot.okx_client.public.get_open_interest(instType="SWAP", instId=f"{symbol.upper()}-USDT-SWAP")
            
            if not oi_data or 'data' not in oi_data or not oi_data['data']:
                await ctx.send(f"{self.bot.get_random_message()}\nno open interest data found for {symbol.upper()}")
                return
            
            data = oi_data['data'][0]
            open_interest = float(data.get('oi', 0))
            open_interest_value = float(data.get('oiCcy', 0))
            inst_id = data.get('instId', '')
            
            # Store current OI value for tracking
            self.bot.storage.update_metric(symbol.upper(), 'oi_value', open_interest_value)
            
            # Get 24h change from local storage
            current_value, change_percent = self.bot.storage.get_24h_change(symbol.upper(), 'oi_value')
            
            if change_percent is not None:
                oi_change_str = f"{change_percent:+.2f}%"
            else:
                oi_change_str = "tracking started"
            
            response = f"{self.bot.get_random_message()}\n\n**{symbol.upper()} open interest**\n"
            response += f"contracts: {self.bot.format_number(open_interest)}\n"
            response += f"value: {self.bot.format_number(open_interest)} {symbol.upper()} (${self.bot.format_number(open_interest_value)})\n"
            response += f"24h change: {oi_change_str}\n"
            response += f"instrument: {inst_id}"
            
            await ctx.send(response)
            
        except Exception as e:
            await ctx.send(f"{self.bot.get_random_message()}\nerror fetching open interest: {str(e)}")
    
    @commands.command(name='vol')
    async def get_volume(self, ctx, symbol='BTC'):
        """Get spot and perpetual volume for a cryptocurrency"""
        try:
            # Get spot volume
            spot_ticker = self.bot.okx_client.public.get_ticker(instId=f"{symbol.upper()}-USDT")
            
            # Get perpetual volume
            perp_ticker = self.bot.okx_client.public.get_ticker(instId=f"{symbol.upper()}-USDT-SWAP")
            
            response = f"{self.bot.get_random_message()}\n\n**{symbol.upper()} volume**\n"
            
            if spot_ticker and 'data' in spot_ticker and spot_ticker['data']:
                spot_data = spot_ticker['data'][0]
                spot_volume = float(spot_data.get('vol24h', 0))
                spot_volume_value = float(spot_data.get('volCcy24h', 0))
                
                response += f"spot (24h): {self.bot.format_number(spot_volume)} {symbol.upper()} (${self.bot.format_number(spot_volume_value)})\n"
            
            if perp_ticker and 'data' in perp_ticker and perp_ticker['data']:
                perp_data = perp_ticker['data'][0]
                perp_volume = float(perp_data.get('vol24h', 0))
                perp_volume_value = float(perp_data.get('volCcy24h', 0))
                
                # Store current perp volume for tracking
                self.bot.storage.update_metric(symbol.upper(), 'perp_volume', perp_volume_value)
                
                # Get 24h change from local storage
                current_value, change_percent = self.bot.storage.get_24h_change(symbol.upper(), 'perp_volume')
                
                if change_percent is not None:
                    volume_change_str = f"{change_percent:+.2f}%"
                else:
                    volume_change_str = "tracking started"
                
                response += f"perp (24h): {self.bot.format_number(perp_volume)} {symbol.upper()} (${self.bot.format_number(perp_volume_value)})\n"
                response += f"24h change: {volume_change_str}"
            
            if not spot_ticker and not perp_ticker:
                await ctx.send(f"{self.bot.get_random_message()}\nno volume data found for {symbol.upper()}")
                return
            
            await ctx.send(response)
            
        except Exception as e:
            await ctx.send(f"{self.bot.get_random_message()}\nerror fetching volume data: {str(e)}")
    
    @commands.command(name='liq')
    async def get_liquidations(self, ctx, symbol='BTC'):
        """Get recent liquidations for a cryptocurrency"""
        try:
            # Liquidations data requires premium API access
            await ctx.send(f"{self.bot.get_random_message()}\nliquidation data not available for {symbol.upper()} (requires premium api access)")
            
        except Exception as e:
            await ctx.send(f"{self.bot.get_random_message()}\nerror fetching liquidations: {str(e)}")
    
    @commands.command(name='all')
    async def get_all_metrics(self, ctx, symbol='BTC'):
        """Get all metrics (funding, OI, volume) for a cryptocurrency"""
        try:
            response = f"{self.bot.get_random_message()}\n\n**{symbol.upper()} metrics**\n"
            
            # Get funding rate
            try:
                funding_data = self.bot.okx_client.public.get_funding_rate(instId=f"{symbol.upper()}-USDT-SWAP")
                if funding_data and 'data' in funding_data and funding_data['data']:
                    funding_rate = float(funding_data['data'][0].get('fundingRate', 0)) * 100
                    response += f"funding: {funding_rate:.4f}%\n"
                else:
                    response += "funding: n/a\n"
            except:
                response += "funding: n/a\n"
            
            # Get open interest
            try:
                oi_data = self.bot.okx_client.public.get_open_interest(instType="SWAP", instId=f"{symbol.upper()}-USDT-SWAP")
                if oi_data and 'data' in oi_data and oi_data['data']:
                    oi_value = float(oi_data['data'][0].get('oiCcy', 0))
                    
                    # Store and get 24h change
                    self.bot.storage.update_metric(symbol.upper(), 'oi_value', oi_value)
                    current_value, change_percent = self.bot.storage.get_24h_change(symbol.upper(), 'oi_value')
                    
                    if change_percent is not None:
                        response += f"oi: {self.bot.format_number(oi_value)} ({change_percent:+.1f}%)\n"
                    else:
                        response += f"oi: {self.bot.format_number(oi_value)} (tracking)\n"
                else:
                    response += "oi: n/a\n"
            except:
                response += "oi: n/a\n"
            
            # Get volume
            try:
                perp_ticker = self.bot.okx_client.public.get_ticker(instId=f"{symbol.upper()}-USDT-SWAP")
                if perp_ticker and 'data' in perp_ticker and perp_ticker['data']:
                    perp_volume = float(perp_ticker['data'][0].get('volCcy24h', 0))
                    
                    # Store and get 24h change
                    self.bot.storage.update_metric(symbol.upper(), 'perp_volume', perp_volume)
                    current_value, change_percent = self.bot.storage.get_24h_change(symbol.upper(), 'perp_volume')
                    
                    if change_percent is not None:
                        response += f"volume: {self.bot.format_number(perp_volume)} ({change_percent:+.1f}%)"
                    else:
                        response += f"volume: {self.bot.format_number(perp_volume)} (tracking)"
                else:
                    response += "volume: n/a"
            except:
                response += "volume: n/a"
            
            await ctx.send(response)
            
        except Exception as e:
            await ctx.send(f"{self.bot.get_random_message()}\nerror fetching metrics: {str(e)}")
    
    @commands.command(name='help')
    async def help_command(self, ctx):
        """Show help message with available commands"""
        response = "**ski bot commands**\n"
        response += "all commands support any cryptocurrency symbol (e.g., btc, eth, sol)\n"
        response += "24h changes are tracked locally\n\n"
        response += "**sb fear** - get current fear & greed index\n"
        response += "**sb fund [symbol]** - get current funding rate (default: btc)\n"
        response += "**sb oi [symbol]** - get open interest data with 24h change\n"
        response += "**sb vol [symbol]** - get spot and perpetual volume with 24h change\n"
        response += "**sb all [symbol]** - get all metrics with 24h changes\n"
        response += "**sb add [profile link]** - add a Twitter profile to track and assign a name\n"
        response += "**sb list** - list all tracked Twitter profiles\n"
        response += "**sb remove {name}** - remove a tracked Twitter profile by name\n"
        response += "**sb help** - show this help message\n\n"
        response += "powered by okx exchange | local 24h tracking | twitter tracker"
        await ctx.send(response)

    @commands.command(name='add')
    async def add_twitter_profile(self, ctx, profile_link: str):
        """Add a Twitter profile to track. Usage: sb add [profile link]"""
        # Extract username from link
        match = re.search(r'twitter.com/([A-Za-z0-9_]+)', profile_link)
        if not match:
            await ctx.send("Invalid Twitter profile link.")
            return
        username = match.group(1)
        await ctx.send(f"Enter a name to assign to @{username}:")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=30)
            name = msg.content.strip()
            if not name:
                await ctx.send("Name cannot be empty.")
                return
            self.twitter_tracker.add_profile(name, profile_link)
            await ctx.send(f"Added Twitter profile @{username} as '{name}'.")
        except asyncio.TimeoutError:
            await ctx.send("Timed out waiting for a name.")

    @commands.command(name='list')
    async def list_twitter_profiles(self, ctx):
        """List all tracked Twitter profiles."""
        profiles = self.twitter_tracker.list_profiles()
        if not profiles:
            await ctx.send("No Twitter profiles are being tracked.")
            return
        msg = "**Tracked Twitter Profiles:**\n"
        for name, info in profiles.items():
            msg += f"- {name}: {info['url']}\n"
        await ctx.send(msg)

    @commands.command(name='remove')
    async def remove_twitter_profile(self, ctx, name: str):
        """Remove a tracked Twitter profile by name. Usage: sb remove {name}"""
        if name not in self.twitter_tracker.profiles:
            await ctx.send(f"No profile found with name '{name}'.")
            return
        self.twitter_tracker.remove_profile(name)
        await ctx.send(f"Removed Twitter profile '{name}'.")

    @tasks.loop(hours=1)
    async def periodic_data_pull(self):
        """Periodically pull data for BTC, ETH, and SOL every hour for 24h% change reference."""
        for symbol in ["BTC", "ETH", "SOL"]:
            try:
                # Pull and store perp volume
                perp_ticker = self.bot.okx_client.public.get_ticker(instId=f"{symbol}-USDT-SWAP")
                if perp_ticker and 'data' in perp_ticker and perp_ticker['data']:
                    perp_volume = float(perp_ticker['data'][0].get('volCcy24h', 0))
                    self.bot.storage.update_metric(symbol, 'perp_volume', perp_volume)
                # Pull and store open interest
                oi_data = self.bot.okx_client.public.get_open_interest(instType="SWAP", instId=f"{symbol}-USDT-SWAP")
                if oi_data and 'data' in oi_data and oi_data['data']:
                    oi_value = float(oi_data['data'][0].get('oiCcy', 0))
                    self.bot.storage.update_metric(symbol, 'oi_value', oi_value)
            except Exception as e:
                logger.error(f"Error in periodic data pull for {symbol}: {e}")

    @tasks.loop(hours=1)
    async def cleanup_old_data(self):
        """Remove all data older than 24h from storage."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)
            for symbol in list(self.bot.storage.data.keys()):
                for metric in list(self.bot.storage.data[symbol].keys()):
                    self.bot.storage.data[symbol][metric] = [
                        point for point in self.bot.storage.data[symbol][metric]
                        if datetime.fromisoformat(point['timestamp']) > cutoff_time
                    ]
            self.bot.storage.save_data()
        except Exception as e:
            logger.error(f"Error during cleanup_old_data: {e}")

    @tasks.loop(minutes=2)
    async def check_new_tweets(self):
        """Check for new tweets from tracked profiles and forward them."""
        if not self.twitter_tracker.bearer_token:
            logger.error("No Twitter Bearer Token found. Set TWITTER_BEARER_TOKEN environment variable.")
            return
            
        profiles = self.twitter_tracker.list_profiles()
        if not profiles:
            return
            
        logger.info(f"Checking {len(profiles)} Twitter profiles for new tweets...")
        
        for name, info in profiles.items():
            try:
                # Extract username from URL
                match = re.search(r'twitter.com/([A-Za-z0-9_]+)', info['url'])
                if not match:
                    logger.error(f"Could not extract username from URL: {info['url']}")
                    continue
                    
                username = match.group(1)
                logger.info(f"Checking tweets for @{username} (name: {name})")
                
                latest_tweet_id, tweet_text = self.twitter_tracker.get_latest_tweet(username)
                last_tweet_id = info.get('last_tweet_id')
                
                logger.info(f"Latest tweet ID: {latest_tweet_id}, Last sent ID: {last_tweet_id}")
                
                if latest_tweet_id and latest_tweet_id != last_tweet_id:
                    channel = self.bot.get_channel(self.bot.channel_id)
                    tweet_url = f"https://twitter.com/{username}/status/{latest_tweet_id}"
                    
                    if channel:
                        await channel.send(f"[{name}] {tweet_text}\n{tweet_url}")
                        logger.info(f"Forwarded tweet from {name} to Discord")
                    else:
                        logger.error(f"Could not find Discord channel with ID: {self.bot.channel_id}")
                        
                    self.twitter_tracker.update_last_tweet(name, str(latest_tweet_id))
                else:
                    logger.info(f"No new tweets for {name}")
                    
            except Exception as e:
                logger.error(f"Error checking tweets for {name}: {e}")

    @commands.command(name='test_twitter')
    async def test_twitter_api(self, ctx):
        """Test if Twitter API is working properly"""
        if not self.twitter_tracker.bearer_token:
            await ctx.send("❌ No Twitter Bearer Token found. Set TWITTER_BEARER_TOKEN environment variable.")
            return
            
        await ctx.send("🔍 Testing Twitter API...")
        
        try:
            # Test with a known account (Twitter's own account)
            test_username = "twitter"
            user_id = self.twitter_tracker.get_user_id(test_username)
            
            if user_id:
                await ctx.send(f"✅ Twitter API working! Found user ID: {user_id}")
                
                # Test getting tweets
                latest_tweet_id, tweet_text = self.twitter_tracker.get_latest_tweet(test_username)
                if latest_tweet_id and tweet_text:
                    await ctx.send(f"✅ Tweet fetching working! Latest tweet: {tweet_text[:100]}...")
                else:
                    await ctx.send("❌ Could not fetch tweets")
            else:
                await ctx.send("❌ Could not get user ID from Twitter API")
                
        except Exception as e:
            await ctx.send(f"❌ Twitter API test failed: {str(e)}")
            logger.error(f"Twitter API test error: {e}")

    async def cog_load(self):
        self.periodic_data_pull.start()
        self.cleanup_old_data.start()
        self.check_new_tweets.start()


def main():
    try:
        bot = CryptoBot()
        
        # Error handling for bot startup
        discord_token = os.getenv('DISCORD_TOKEN')
        if discord_token is None:
            raise ValueError("DISCORD_TOKEN environment variable is not set")
        
        logger.info("Starting bot...")
        bot.run(discord_token)
        
    except KeyboardInterrupt:
        logger.info("Bot shutting down...")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        # Don't exit immediately, give time for logs to be written
        import time
        time.sleep(5)

if __name__ == "__main__":
    main() 