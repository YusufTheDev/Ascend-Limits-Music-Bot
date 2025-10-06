import os
from dotenv import load_dotenv
from keep_alive import keep_alive

keep_alive()

load_dotenv()

import discord
from discord.ext import commands

from bot.music_cog import MusicCog

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="your queue 🎵")
    )


@bot.event
async def setup_hook():
    await bot.add_cog(MusicCog(bot))


bot.run(TOKEN)
