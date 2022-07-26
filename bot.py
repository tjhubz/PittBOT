import discord
import discord.ext
import orjson
import os
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from util.db import DbUser, Base
import util.invites
import http.client
import mimetypes
import base64
import requests


bot = discord.Bot(intents=discord.Intents.all())

# ------------------------------- INITIALIZATION -------------------------------

TOKEN = "default" # In a production environment, replace this with the real token
QUALTRICS_OAUTH_SECRET = "default"
QUALTRICS_CLIENT_ID = "default"
SENDGRID_SECRET = "default"
DEBUG = False
VERSION = "#.#.#"
DATABASE_PATH = None

# ------------------------------- DATABASE -------------------------------

with open("config.json", "r") as config:
    data = orjson.loads(config.read())

    # Extract mode. During development (and for any 
    # contributors while they work) the mode should be set
    # in the config to "debug", which forces the token to be
    # acquired from an environment variable so that the token is NOT
    # pushed to the public repository. During production/deployment,
    # the mode should be set to "production", and the token will be placed
    # directly into the code.
    match str(data["mode"]).lower():
        case "debug":
            DEBUG = True
            TOKEN = os.getenv("PITTBOT_TOKEN")
            QUALTRICS_OAUTH_SECRET = os.getenv("QUALTRICS_OAUTH_SECRET")
            QUALTRICS_CLIENT_ID = os.getenv("QUALTRICS_CLIENT_ID")
            SENDGRID_SECRET = os.getenv("SENDGRID_TOKEN")
        case "production":
            DEBUG = False
    
    # Version, so that it only has to be updated in one place.
    VERSION = data["version"]

    # A SQLite3 database will be used to track users and
    # and information that is needed about them persistently 
    # (residence, email address, etc.)
    # This is a path to the database RELATIVE to THIS (bot.py) file.
    DATABASE_PATH = data["database_path"] or "dbs/test.db"
    
# Database initialization
db = sqlalchemy.create_engine(f"sqlite:///{DATABASE_PATH}")
# Database session init
Session = sessionmaker(bind=db)
session = Session()
# Create tables
Base.metadata.create_all(db)

# ------------------------------- GLOBAL VARIABLES  -------------------------------

# Guild to invites associativity
invites_cache = dict()

# Invite codes to role objects associativity
invite_to_role = dict()

# Associate each guild with its landing channel
guild_to_landing = dict()


# ------------------------------- COMMANDS -------------------------------

# These are just for testing and will be 
# removed as soon as we know the bot works
@bot.slash_command()
async def hello(ctx, name: str = None):
    name = name or ctx.author.mention
    await ctx.respond(f"Hello {name}!")

@bot.user_command(name="Say Hello")
async def hi(ctx, user):
    await ctx.respond(f"{ctx.author.mention} says hello to {user.name}!")
    
@bot.slash_command()
@discord.guild_only()
@discord.ext.commands.has_permissions(manage_channels=True)
async def make_categories(ctx, link: str):
    # Defer a response to prevent the 3 second timeout gate from being closed.
    await ctx.defer()
    
    # If we actually are in a guild (this is a redundant check and can probably be
    # removed, figuring the @discord.guild_only() decorator is provided, but I figured
    # a graceful close just in case)
    if ctx.guild:
        guild = ctx.guild
        # Read the list of RAs from a RAW hastebin file. It is SIGNIFICANT that the
        # link is to a RAW hastebin, or it will not be parsed correctly.
        if "raw" not in link:
            await ctx.send_followup("Uh oh! You need to send a `raw` hastebin link. Click the 'Just Text' button on hastebin to get one.")
            return
        
        # Guard request in case of status code fail
        try:
            ras = util.invites.read_from_haste(link)
        except requests.RequestException:
            await ctx.send_followup("The given link returned a failure status code when queried. Are you sure it's valid?")
            return
        
        # Make the categories. This also makes their channels, the roles, and a text file
        # called 'ras-with-links.txt' that returns the list of RAs with the associated invite links.
        invite_role_dict = await util.invites.make_categories(guild, ras, guild_to_landing[guild.id])
        if not invite_role_dict:
            await ctx.send_followp("Failed to make invites. Check that a #verify channel exists.")
            return
        
        # Update invite cache, important for on_member_join's functionality
        invites_cache[guild.id] = await guild.invites()
        
        # Iterate over the invites, adding the new role object 
        # to our global dict if it was just created.
        for invite in invites_cache[guild.id]:
            if invite.code in invite_role_dict:
                invite_to_role[invite.code] = invite_role_dict[invite.code]
        
        # Upload the file containing the links and ra names as an attachment, so they
        # can be distributed to the RAs to share.
        await ctx.send_followup(file=discord.File("ras-with-links.txt"))
    else:
        await ctx.respond("Sorry! This command has to be used in a guild context.")

@bot.slash_command()
async def verify(ctx):
    # Verification will usually happen when a user joins a server with the bot.
    # However, in case something fails or the bot does not have permission to view
    # join events in a server, it is a good idea to have a slash command set up that 
    # will allow a user to manually trigger the verification process themselves.
    await ctx.respond(f"Oh no! looks like this command isn't implemented yet. Check back later.")
    
@bot.slash_command(description="Manually begin initializing necessary information for the bot to work in this server.")
@discord.guild_only()
@discord.ext.commands.has_permissions(administrator=True)
async def setup(ctx):
    # Need to find out how to automate this.
    # A good way is to make this run any time this bot joins a new guild,
    # which can be done when on_guild_join event is fired.
    # Also, adding persistence to guild_to_landing would be really cool.
    # TODO: We need to make ORM models for Guilds and Invites in order to 
    # persist guild_to_landing and invite_to_role.
    
    guild_to_landing[ctx.guild.id] = discord.utils.get(ctx.guild.channels, position=0)
    print(f"{guild_to_landing=}")
    invites_cache[ctx.guild.id] = await ctx.guild.invites()
    await ctx.respond("All set!")
    
    
# ------------------------------- EVENT HANDLERS -------------------------------

@bot.event
async def on_member_join(member: discord.Member):
    # Need to figure out what invite the user joined with
    # in order to assign the correct roles.
    
    print(f"Member join event fired with {member.display_name}")
    
    # This is a kind of janky method taken from this medium article:
    # https://medium.com/@tonite/finding-the-invite-code-a-user-used-to-join-your-discord-server-using-discord-py-5e3734b8f21f
    # Unfortunately, I cannot find a native API way to get the invite link used by a user. If you find one, please make a PR 😅
    
    # Invites before user joined
    old_invites = invites_cache[member.guild.id]
    
    # Invites after user joined
    invites_now = await member.guild.invites()
    
    for invite in old_invites:
        print(f"Checking {invite.code}")
        # O(n²), would love to make this faster
        if invite.uses < util.invites.get_invite_from_code(invites_now, invite.code).uses:
            
            # Who joined and with what link
            print(f"Member {member.name} Joined")
            print(f"Invite Code: {invite.code}")
            
            # Need to give the member the appropriate role
            if invite.code in invite_to_role:
                # If the invite code's use was previously zero, then we should actually give the user 
                # the RA role, in addition to the RA X's community role.
                if invite.uses == 0:
                    # First use of invite
                    await member.add_roles(discord.utils.get(member.guild.roles, name='RA'), reason=f"Member joined with first use of invite code {invite.code}")
                await member.add_roles(invite_to_role[invite.code], reason=f"Member joined with invite code {invite.code}")
            else:
                # This is a pretty fatal error, and really shouldn't occur if everything has gone right up to here.
                print(f"{invite.code} not in invite_to_role:\n{invite_to_role=}")
            
            # Update cache
            invites_cache[member.guild.id] = invites_now
            
            # Short circuit out
            return
    
    
    
@bot.event
async def on_ready():
    # Build a default invite cache
    for guild in bot.guilds:
        invites_cache[guild.id] = await guild.invites()

if DEBUG:
    print(f"""Bootstrapping bot...
---------------------------------------
{VERSION=}
{DATABASE_PATH=}
---------------------------------------
""")

bot.run(TOKEN)
