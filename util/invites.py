# Code related to generating discord invite links 
# based off of lists of RAs and what not.
import discord
import asyncio

# This file should have NO STATE. All functions are
# intentionally pure (or at least faux-pure) because
# they are just utility functions for the bot and will be
# used across different guilds.

def read_ras(filepath: str):
    """Read list of RAs from a file path.

    Args:
        filepath (str): path to input file containing list of RAs

    Returns:
        list[str]: RA names as a python list
    """
    with open(filepath, 'r') as infile:
        return infile.readlines()

async def make_channels(guild: discord.Guild, ras: list[str]):
    """Make channels associated with each RA for the given guild.
    
    REQUIRES GUILD CONTEXT AND manage_channels PERMISSION!
    THESE MUST BE VERIFIED BY THE CALLER.

    Args:
        guild_id (int): Guild ID for which the channel generation will take place
        ras (list[str]): List of RAs.
    """
    # This is obviously super rudimentary and needs a ton of work, but it does work
    # as advertised right now. It makes a bunch of top level channels based off of the RA names.
    # TODO: finish this method's logic.
    for RA in ras:
        await guild.create_text_channel(name=f"{RA.replace(' ','-')}-channel")
    
    

