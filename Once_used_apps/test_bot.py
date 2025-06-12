# test_bot.py
import discord
from discord.ext import commands
import os
import asyncio

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print("✅ on_ready ажиллалаа")
    print(f"🤖 Bot: {bot.user}")

async def main():
    print("🚀 Bot эхэлж байна...")
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
