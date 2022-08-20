"""Code related to generating discord invite links
based off of lists of RAs and what not.
"""
import asyncio
import discord
from discord import Colour, Permissions
import requests
from .log import Log

# This file should have NO STATE. All functions are
# intentionally pure (or at least faux-pure) because
# they are just utility functions for the bot and will be
# used across different guilds.


def get_invite_from_code(invites, code):
    """Get an invite object from a given invite code. (Used when members join to associate invites to them.)

    Args:
        invites (list[Invite]): List of invites to search.
        code (str): URL fragment code for the invite.

    Returns:
        Invite: the invite with a matching code, if one exists. None otherwise.
    """
    for invite in invites:
        if invite.code == code:
            return invite
    return None


def read_from_haste(link: str):
    """Read a list of RAs from a RAW hastebin link containing a return-delimited list of RAs for a server.
    It is VERY important this link is the RAW link, or parsing will FAIL.

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

    # Otherwise the request returned an error code. This should probably be try-excepted in the main file.
    raise requests.RequestException(
        f"Request did not return a success code, returned status: {res.status_code}"
    )


async def make_categories(
    guild: discord.Guild, ras: list[str], landing_channel: discord.TextChannel
):
    """Make categories for each RA in an RA list, consisting of a text channel and voice channel.

    Args:
        guild (discord.Guild): The guild in which to create the categories, namely the calling guild.
        ras (list[str]): List of RA names.
    """
    # Lines to add to the text file that is uploaded
    ras_with_links = []
    # Dictionary that will associate RA links with category channels
    invite_to_role = {}
    # Associate category ID to role ID as per https://github.com/tjhubz/PittBOT/issues/19
    category_to_role = {}

    # Iterate over all of the RAs in the hastebin response
    for ra_line in ras:
        # Will split out the first and last names of the RA
        first_name = ""
        # In case it is comma separated
        if "," in ra_line:
            try:
                # Split on comma and parse first/last out
                names = ra_line.split(",")
                first_name = names[1].rstrip()
            except IndexError:
                # If there is no second item in the split (there was only one name)
                # then use the whole line (minus ',') as the name
                first_name = ra_line.strip().replace(",", "")
        else:
            try:
                names = ra_line.split(" ")
                first_name = names[1].rstrip()
            except IndexError:
                first_name = ra_line.strip()

        # Create the RA's category
        category = await guild.create_category(
            f"RA {first_name.title()}'s Community",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(read_messages=False)
            },
        )

        # Create the text and voice channels
        await category.create_text_channel("chat")
        await category.create_voice_channel("voice")

        # Generate an invite.
        if landing_channel:
            try:
                invite = await landing_channel.create_invite()
            # Abnormal debugging issue
            except discord.errors.NotFound:
                print(
                    "No such channel exists, dumping channel object: {landing_channel=}"
                )
        else:
            return None

        building_category = discord.utils.get(
            landing_channel.guild.categories, name="building"
        )

        info_category = discord.utils.get(landing_channel.guild.categories, name="info")

        ras_with_links.append(f"{ra_line} : {invite.url}\n")

        perms = Permissions(view_channel=True)

        # Generate a role to associate with the community.
        new_role = await guild.create_role(
            name=f"RA {first_name.title()}'s Community",
            color=Colour.blue(),
            permissions=perms,
        )

        # Set permissions for our new category
        await category.set_permissions(new_role, read_messages=True, view_channel=True)

        # Set permissions for other categories
        if building_category:
            await building_category.set_permissions(
                new_role, read_messages=True, view_channel=True
            )
        else:
            Log.warning(
                f"Guild {guild.name}[{guild.id}] does not have a category named 'building'"
            )

        if info_category:
            await info_category.set_permissions(
                new_role, read_messages=True, view_channel=True
            )
        else:
            Log.warning(
                f"Guild {guild.name}[{guild.id}] does not have a category named 'info'"
            )

        # Build associations
        # TODO: Should this associate to the entire object, or just to ID?
        invite_to_role[invite.code] = new_role
        # ID : ID association, rather than ID : object association
        category_to_role[category.id] = new_role.id

    # Create the text file associating the RAs to links that we will upload.
    with open("ras-with-links.txt", "w") as ra_file:
        ra_file.writelines(ras_with_links)

    return (invite_to_role, category_to_role)
