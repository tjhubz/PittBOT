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

bot = discord.Bot()

TOKEN = "default" # In a production environment, replace this with the real token
QUALTRICS_OAUTH_SECRET = "default"
QUALTRICS_CLIENT_ID = "default"
SENDGRID_SECRET = "default"
DEBUG = False
VERSION = "#.#.#"
DATABASE_PATH = None

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
        await util.invites.make_categories(guild, ras)
        
        # Upload that file as an attachment.
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

if DEBUG:
    print(f"""Bootstrapping bot...
---------------------------------------
{VERSION=}
{DATABASE_PATH=}
---------------------------------------
""")

# Uncomment this line when we start running the bot
bot.run(TOKEN)