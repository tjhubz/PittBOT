import discord
import orjson
import os
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from db_classes import DbUser, Base
import http.client
import mimetypes
import base64

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
    DATABASE_PATH = data["database_path"] or "test.db"
    
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
async def verify(ctx):
    # Verification will usually happen when a user joins a server with the bot.
    # However, in case something fails or the bot does not have permission to view
    # join events in a server, it is a good idea to have a slash command set up that 
    # will allow a user to manually trigger the verification process themselves.
    ...

if DEBUG:
    print(f"""Bootstrapping bot...
---------------------------------------
{VERSION=}
{DATABASE_PATH=}
---------------------------------------
""")

# Uncomment this line when we start running the bot
bot.run(TOKEN)