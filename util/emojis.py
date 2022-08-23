'''
Utility functions for handling of emoji synchronization across guilds
'''

from tkinter import Image
import discord
from .log import Log

async def sync_add(bot: discord.Bot, emoji: discord.Emoji):
    for guild in bot.guilds:
        # Check if this emoji already exists
        guild_emojis = await guild.fetch_emojis()
        exists = False
        for guild_emoji in guild_emojis:
            if guild_emoji.name == emoji.name:
                exists = True
                break
        
        # If the emoji exists, we can skip creation
        if exists:
            continue

        # Create emoji
        try:
            await guild.create_custom_emoji(name=emoji.name, image=await emoji.read())
            Log.ok(f'Emoji: {emoji.name} successfully added in {guild.name}')
        except:
            Log.warning(f'Could not create emoji {emoji.name} in {guild.name}')
            continue

async def sync_delete(bot: discord.Bot, emoji: discord.Emoji):
    for guild in bot.guilds:
        guild_emojis = await guild.fetch_emojis()
        del_emoji = None

        # Check if the guild contains an emoji that matches this one
        for guild_emoji in guild_emojis:
            if guild_emoji.name == emoji.name:
                del_emoji = guild_emoji
                break

        if del_emoji:
            # Delete the emoji in the server if possible
            # Could be forbidden to delete the emoji or get HTTP Exception
            try:
                await del_emoji.delete()
                Log.ok(f'Emoji: {emoji.name} in {guild.name} successfully deleted')
            except:
                Log.warning(f'Could not delete emoji {emoji.name} in {guild.name}')
                continue

async def sync_name(bot: discord.Bot, old_name: str, new_emoji: discord.Emoji):
    for guild in bot.guilds:
        
        # Check the guild for an emoji with the same name
        guild_emojis = await guild.fetch_emojis()
        for emoji in guild_emojis:
            
            # If the name matches, update it and move on to the next guild
            if emoji.name == old_name:  # TODO: Check if we should check that the image is the same
                await emoji.edit(name=new_emoji.name)
                Log.ok(f'Updated emoji name {old_name} to {new_emoji.name} in guild {guild.id}')
                break

