# Code related to generating discord invite links 
# based off of lists of RAs and what not.
import discord
from discord import Colour, Permissions
import asyncio
import requests

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
    
    
def read_from_haste(link: str):
    """Read a list of RAs from a RAW hastebin link containing a return-delimited list of RAs for a server. It is VERY important this link is the RAW link, or parsing will FAIL.

    Args:
        link (str): Link to raw hastebin with return-separated RA list..
        
    Returns:
        list[str]: List of RAs.
    """
    # Request the hastebin text.
    res = requests.get(link)
    
    # On success return an array split on returns
    if res.status_code == 200:
        return res.text.split("\n") 
    else:
        # Otherwise the request returned an error code. This should probably be try-excepted in the main file.
        raise requests.RequestException(f"Request did not return a success code, returned status: {res.status_code}")
    
    
async def make_categories(guild: discord.Guild, ras: list[str]):
    """Make categories for each RA in an RA list, consisting of a text channel and voice channel.

    Args:
        guild (discord.Guild): The guild in which to create the categories, namely the calling guild.
        ras (list[str]): List of RA names.
    """
    # Lines to add to the text file that is uploaded
    ras_with_links = []
    
    # Iterate over all of the RAs in the hastebin response
    for ra_line in ras:
        # Will split out the first and last names of the RA
        first_name = ""
        last_name = ""
        # In case it is comma separated
        if ',' in ra_line:
            try:
                # Split on comma and parse first/last out
                names = ra_line.split(',')
                first_name = names[1]
                last_name = names[0]
            except IndexError:
                # If there is no second item in the split (there was only one name)
                # then use the whole line (minus ',') as the name
                first_name = last_name = ra_line.replace(',','')
        else:
            try:
                names = ra_line.split(' ')
                first_name = names[1]
                last_name = names[0]
            except IndexError:
                first_name = last_name = ra_line
        
        # Create the RA's category
        category = await guild.create_category(f"RA {first_name.title()}'s Community")
        
        # Create the text and voice channels
        text_channel = await category.create_text_channel("chat")
        await category.create_voice_channel("Voice")
        
        # Generate an invite.
        invite = await text_channel.create_invite()
        ras_with_links.append(f"{ra_line} : {invite.url}\n")
        
        # Generate a role to associate with the community.
        # TODO: Generate accurate permissions for this.
        await guild.create_role(name=f"RA {first_name.title()}'s Community", color=Colour.blue(), permissions=Permissions.general())
    
    # Create the text file associating the RAs to links that we will upload.
    with open("ras-with-links.txt",'w') as ra_file:
        ra_file.writelines(ras_with_links)
        
    # TODO: We probably need to save this data in our database as well. Doing so 
    # would require either passing the DB object and session into this utility function
    # so it can access the bot's main database session, or moving this code all into the main bot file,
    # which is a fine solution, I just put it here to make the main bot file as clean as possible.
    
    

