'''
Code related to the handling of emoji synchronization across guilds
'''

from io import BytesIO
from tkinter import Image
import discord
import requests
from util.log import Log


async def sync_add(bot: discord.Bot, guild: discord.Guild, emoji: discord.Emoji):
    for guild in bot.guilds:
        emoji_names = [emoji.name for emoji in await guild.fetch_emojis()]

        # Will not do anything as there is already an emoji with this name
        if emoji.name in emoji_names:
            return
        
        # Create emoji

        # CAN DELETE AFTER TESTING read()
        # response = requests.get(emoji.url)
        # img = Image.open(BytesIO(response.content))
        try:
            guild.create_custom_emoji(name=emoji.name, image=emoji.read())
            Log.ok(f'Emoji: {emoji.name} successfully added')
        except:
            return