import os
from sqlite3 import IntegrityError
import discord
import discord.ext
import orjson
import sqlalchemy
import requests
from sqlalchemy.orm import sessionmaker
import util.invites
from util.log import Log
from util.db import DbGuild, DbInvite, DbUser, Base


bot = discord.Bot(intents=discord.Intents.all())

# ------------------------------- INITIALIZATION -------------------------------

TOKEN = os.getenv("PITTBOT_TOKEN")
DEBUG = False
VERSION = "0.1.0"
DATABASE_PATH = "dbs/main.db"
HUB_SERVER_ID = 996607138803748954
LONG_DELETE_TIME = 60.0
SHORT_DELETE_TIME = 15.0

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
        case "production":
            DEBUG = True

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
invites_cache = {}

# Invite codes to role objects associativity
invite_to_role = {}

# Associate each guild with its landing channel
guild_to_landing = {}

# This will not actually persistently associate every user with the guild they're in
# Rather, it will be used during verification to associate a verifying user
# with a guild, so that even if they are DMed verification rather
# than doing it in the server, we can still know what guild they're verifying for.
# A user CANNOT BE VERIFYING FOR MORE THAN ONE GUILD AT ONCE
user_to_guild = {}

# Cache of user IDs to their pitt email addresses
user_to_email = {}

# ------------------------------- CLASSES -------------------------------


class VerifyModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_item(discord.ui.InputText(label="Pitt Email Address"))

    async def callback(self, interaction: discord.Interaction):
        user_to_email[interaction.user.id] = self.children[0].value
        if "@pitt.edu" in self.children[0].value:
            await interaction.response.send_message(
                f"Welcome {interaction.user.mention}! Thank you for verifying.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Only @pitt.edu emails will be accepted. Please retry by pressing the green button.",
                ephemeral=True
            )

    async def on_timeout(self):
        self.stop()
        

class ManualRoleSelectModal(discord.ui.Modal):
    def __init__(self, choice_strings=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        choices = []
        for choice in choice_strings:
            choices.append(discord.SelectOption(label=choice, value=choice))
        
        self.return_role = None
        self.add_item(discord.ui.Select(placeholder="Select a community", options=choices))

    async def callback(self, interaction: discord.Interaction):
        self.return_role = self.children[0].value

class UnsetupConfirmation(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Type Yes to Confirm"))

    async def callback(self, interaction: discord.Interaction):
        if self.children[0].value.lower() == "yes":
            try:
                guild_obj = (
                    session.query(DbGuild).filter_by(ID=interaction.guild.id).one()
                )
            except Exception as ex:
                guild_obj = None

            if guild_obj:
                guild_obj.is_setup = False
                guild_obj.landing_channel_id = None
                guild_obj.ra_role_id = None
                session.merge(guild_obj)
                try:
                    session.commit()
                except Exception as ex:
                    await interaction.response.send_message(
                        "An unexpected database error occurred.", ephemeral=True
                    )
                    print(ex.with_traceback())
                    return
                else:
                    await interaction.response.send_message(
                        f"Setup status has been reset for guild with ID {interaction.guild.id}",
                        ephemeral=True,
                    )
            else:
                await interaction.response.send_message(
                    "The guild you are trying to reset does not exist.", ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "Operation cancelled.", ephemeral=True
            )

    async def on_timeout(self):
        self.stop()


class VerifyView(discord.ui.View):
    @discord.ui.button(label="Verify", style=discord.ButtonStyle.green)
    async def verify_callback(self, button, interaction):
        await verify(interaction)


# ------------------------------- COMMANDS -------------------------------

# This has to, for some reason, stay here,
# or else the discord.ext module cannot load for the next command.
# One command without the .ext module loaded NEEDS to be registered
# before .ext can be loaded. Weird bug in discord.py/its forks, I guess.
@bot.slash_command(description="Verify yourself to start using ResLife servers!")
async def verify(ctx):
    # Verification will usually happen when a user joins a server with the bot.
    # However, in case something fails or the bot does not have permission to view
    # join events in a server, it is a good idea to have a slash command set up that
    # will allow a user to manually trigger the verification process themselves.

    try:
        author = ctx.author
    except AttributeError:
        author = ctx.user

    try:
        user = session.query(DbUser).filter_by(ID=author.id).one()
    except Exception as ex:
        user = None

    if user:
        if user.verified:
            await ctx.response.send_message(
                "You're already verified! Congrats 🎉", ephemeral=True
            )
            return

    if author.id in user_to_guild:
        # The verification was initialized on join
        guild = user_to_guild[author.id]
    elif ctx.guild:
        guild = ctx.guild
    else:
        await ctx.response.send_message(
            "We weren't able to figure out which server you were trying to verify for. Press the green 'verify' button inside the server's `#verify` channel.",
            ephemeral=True
        )
    
    # Get invite snapshot ASAP after guild is determined
    # Invites after user joined
    invites_now = await guild.invites()
    
    # Invites before user joined
    old_invites = invites_cache[guild.id]

    member = discord.utils.get(guild.members, id=author.id)

    if not member:
        await ctx.response.send_message(
            f"It doesn't look like we could verify that you are in the server {guild.name}. Press the green 'verify' button inside the server's `#verify` channel.",
            ephemeral=True
        )

    email = "default"

    modal = VerifyModal(title="Verification", timeout=60)

    await ctx.response.send_modal(modal)

    # You have to actually await on_timeout, so I'm not sure what to do if the timeout fails.
    await modal.wait()

    if member.id in user_to_email:
        email = user_to_email[member.id]
    else:
        # Fatal error, this should never happen.
        await ctx.followup.send(
            f"Your user ID {member.id} doesn't show up in our records! Please report this error to your RA with Error #404",
            ephemeral=True
        )
        Log.error(f"Failed to verify user {member.name}, dumping: {user_to_email=}")
        email = "FAILED TO VERIFY"
        verified = False

    if "@pitt.edu" not in email:
        return

    # Set the user's nickname to their email address on successful verification
    nickname = email[: email.find("@pitt.edu")]
    await member.edit(nick=nickname)

    verified = True

    # This is a kind of janky method taken from this medium article:
    # https://medium.com/@tonite/finding-the-invite-code-a-user-used-to-join-your-discord-server-using-discord-py-5e3734b8f21f
    # Unfortunately, I cannot find a native API way to get the invite link used by a user. If you find one, please make a PR 😅
    
    potential_invites = []

    for invite in old_invites:
        Log.info(f"Checking {invite.code}")
        # O(n²), would love to make this faster
        if (
            invite.uses
            < util.invites.get_invite_from_code(invites_now, invite.code).uses
        ):
            
            # This is POTENTIALLY the right code

            # Who joined and with what link
            Log.info(f"Potentially invite Code: {invite.code}")

            potential_invites.append(invite)

    num_overlap = len(potential_invites)
    
    Log.info(f"{potential_invites=}")
    
    assigned_role = None
    
    if num_overlap == 1:
        invite = potential_invites[0]
        if invite_to_role[invite.code]:
            assigned_role = invite_to_role[invite.code]
            Log.ok(f"Invite link {invite.code} is cached with '{assigned_role.name}', assigning this role.")
        else:
            try:
                inv_object = session.query(DbInvite).filter_by(code=inv.code).one()
            except Exception as ex:
                inv_object = None
            
            if inv_object:
                assigned_role = discord.utils.get(guild.roles, id=inv_object.role_id)
                if not assigned_role:
                    Log.error(f"Databased invite '{inv.code}' did not return a role. This is an error.")
                
    elif num_overlap > 1:
        # Overlapping possibilities, there would have been a data race here before 😔
        
        # List of options 
        options = []
        options_to_roles = {}
        
        # Gather the roles associated with all the overlapping invites
        for inv in potential_invites:     
            role = invite_to_role[inv.code]
            if role:
                Log.ok(f"Invite link {inv.code} is cached with '{role.name}', adding to modal options for manual select.")
                options.append(role.name)
                options_to_roles[role.name] = role
            else:
                Log.info(f"Invite link {inv.code} was not cached, doing lookup in database.")
                try:
                    inv_object = session.query(DbInvite).filter_by(code=inv.code).one()
                except Exception as ex:
                    inv_object = None
                    
                if inv_object:
                    Log.ok(f"Invite link {inv.code} was found in the database.")
                    role = discord.utils.get(guild.roles, id=inv_object.role_id)
                    if role:
                        Log.ok(f"Databased invite '{inv.code}' returned a valid role '{role.name}', adding to modal options for manual select.")
                        options.append(role.name)
                        options_to_roles[role.name] = role
                    else:
                        Log.error(f"Databased invite '{inv.code}' did not return a role. This is an error.")
                else:
                    Log.error(f"Invite link {inv.code} was neither cached nor found in the database. This code will be ignored. This is an error. ")
        
        # Need to now show a modal with all of these options and 
        # then track the correct, selected one to be the role that is actually assigned
        modal = ManualRoleSelectModal(choice_strings=options, title="Verification", timeout=60)

        await ctx.response.send_modal(modal)

        await modal.wait()
        
        # Modal should now have a selected value
        if modal.return_role:
            Log.ok(f"Role with name '{modal.return_role}' was selected manually.")
            assigned_role = options_to_roles[modal.return_role]
            
            # Now need to find invite
            try:
                inv_object = session.query(DbInvite).filter_by(role_id=assigned_role.id).one()
            except Exception as ex:
                inv_object = None
            
            if inv_object:
                invite = next(filter(lambda inv: inv.code == inv_object.code, invites_cache[guild.id]), None)
                if not invite:
                    # Last ditch effort to get an invite object
                    current_invites = await guild.invites()
                    invite = next(filter(lambda inv: inv.code == inv_object.code, current_invites), None)
                    
                    if not invite:
                        Log.error(f"Could not get a valid invite object out of role '{assigned_role.name}' no matter what we tried. Aborting.")
                        return
                else:
                    Log.ok(f"Invite object with code '{invite.code}' fetched correctly.")
        else:
            Log.error(f"No valid role was selected manually. This is operation-fatal. Aborting.")
            return
        
    else:
        # Error
        Log.error(f"No valid invite link was found when user {member.name} with ID {member.id} joined. This is operation-fatal. Aborting.")
        Log.error(f"{num_overlap=}")
        Log.error(f"{potential_invites=}")
        # Abort
        return
        
    # Need to give the member the appropriate role
    is_user_ra = False
    # If the invite code's use was previously zero, then we should actually give the user
    # the RA role, in addition to the RA X's community role.
    if invite.uses == 0:
        # First use of invite
        is_user_ra = True
        await member.add_roles(
            discord.utils.get(guild.roles, name="RA"),
            reason=f"Member joined with first use of invite code {invite.code}",
        )
        
    if assigned_role:
        await member.add_roles(
            assigned_role,
            reason=f"Member joined with invite code {invite.code}",
        )
    else:
        Log.error("Bot was not able to determine a role from the invite link used.")

    await member.add_roles(
            discord.utils.get(guild.roles, name="resident"),
            reason=f"Member joined with {invite.code} after RA already set.",
        )

    # Take user's ability to message verification channel away.
    await guild_to_landing[guild.id].set_permissions(
        invite_to_role[invite.code],
        read_messages=False,
        send_messages=False,
    )

    # We should add user to database here
    if assigned_role:
        new_member = DbUser(
            ID=member.id,
            username=member.name,
            email=email,
            verified=verified,
            is_ra=is_user_ra,
            community=assigned_role.name,
        )
    else:
        new_member = DbUser(
            ID=member.id,
            username=member.name,
            email=email,
            verified=verified,
            is_ra=is_user_ra,
            community="resident",
        )

    # Use merge instead of add to handle if the user is already found in the database.
    # Our use case may dictate that we actually want to cause an error here and
    # disallow users to verify a second time, but this poses a couple challenges
    # including if a user leaves the server and is re-invited.
    session.merge(new_member)
    
    # Update cache
    invites_cache[guild.id] = invites_now
    
    del user_to_email[member.id]
    del user_to_guild[member.id]
    session.commit()
        

@bot.slash_command(
    description="Create categories based off of a hastebin/pastebin list of RA names."
)
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
            await ctx.send_followup(
                "Uh oh! You need to send a `raw` hastebin link. Click the 'Just Text' button on hastebin to get one.",
                ephemeral=True,
            )
            return

        # Guard request in case of status code fail
        try:
            ras = util.invites.read_from_haste(link)
        except requests.RequestException:
            await ctx.send_followup(
                "The given link returned a failure status code when queried. Are you sure it's valid?",
                ephemeral=True,
            )
            return

        # Make the categories. This also makes their channels, the roles, and a text file
        # called 'ras-with-links.txt' that returns the list of RAs with the associated invite links.
        invite_role_dict = await util.invites.make_categories(
            guild, ras, guild_to_landing[guild.id]
        )
        if not invite_role_dict:
            await ctx.send_followp(
                "Failed to make invites. Check that a #verify channel exists.",
                ephemeral=True,
            )
            return

        # Update invite cache, important for on_member_join's functionality
        invites_cache[guild.id] = await guild.invites()

        # Iterate over the invites, adding the new role object
        # to our global dict if it was just created.
        for invite in invites_cache[guild.id]:
            if invite.code in invite_role_dict:
                invite_obj = DbInvite(
                    code=invite.code,
                    guild_id=guild.id,
                    role_id=invite_role_dict[invite.code].id
                )
                session.merge(invite_obj)
                invite_to_role[invite.code] = invite_role_dict[invite.code]

        session.commit()
        # Upload the file containing the links and ra names as an attachment, so they
        # can be distributed to the RAs to share.
        await ctx.send_followup(file=discord.File("ras-with-links.txt"))
    else:
        await ctx.respond(
            "Sorry! This command has to be used in a guild context.", ephemeral=True
        )


@bot.slash_command(
    description="Manually begin initializing necessary information for the bot to work in this server."
)
@discord.guild_only()
@discord.ext.commands.has_permissions(administrator=True)
async def setup(ctx):
    # Need to find out how to automate this.
    # A good way is to make this run any time this bot joins a new guild,
    # which can be done when on_guild_join event is fired.
    # Also, adding persistence to guild_to_landing would be really cool.
    # To be entirely honest, I am not sure whether we really need a database
    # for the guild and invites at all yet, but figure we should be ready with
    # them for if we do. It seems like the guild and invite information can all easily be
    # grabbed from the discord cache.

    try:
        exists_guild = session.query(DbGuild).filter_by(ID=ctx.guild.id).one()
    except Exception as ex:
        exists_guild = None

    if exists_guild:
        if exists_guild.is_setup:
            await ctx.response.send_message(
                "This server has already been set up!", ephemeral=True
            )
            return

    # Track the landing channel (verify) of the server
    guild_to_landing[ctx.guild.id] = discord.utils.get(
        ctx.guild.channels, name="verify"
    )
    # Log.info(f"{guild_to_landing=}")

    # Cache the invites for the guild as they currently stand (none should be present)
    invites_cache[ctx.guild.id] = await ctx.guild.invites()

    ra_role = discord.utils.get(ctx.guild.roles, name="RA")

    if not ra_role:
        try:
            ra_role = await ctx.guild.create_role(
                name="RA",
                hoist=True,
                permissions=discord.Permissions.advanced(),
                color=discord.Colour.red(),
            )
        except discord.Forbidden:
            await ctx.followup.send(
                "Attempted to create an RA role but do not have valid permissions.",
                ephemeral=True,
            )

    this_guild = DbGuild(
        ID=ctx.guild.id,
        is_setup=True,
        ra_role_id=ra_role.id,
        landing_channel_id=guild_to_landing[ctx.guild.id].id,
    )

    session.merge(this_guild)

    try:
        session.commit()
    except IntegrityError as int_exception:
        Log.warning("Attempting to merge an already existent guild into the database failed:")
        print(int_exception.with_traceback())

    # Create a view that will contain a button which can be used to initialize the verification process
    view = VerifyView(timeout=None)

    await guild_to_landing[ctx.guild.id].send("Click below to verify.", view=view)

    # Finished
    await ctx.respond("Setup finished.", ephemeral=True)


@bot.slash_command(
    name="unsetup",
    description="Reset a server's setup-status. Only use this if you know what you're doing.",
)
@discord.ext.commands.has_permissions(administrator=True)
async def unsetup(ctx):
    dialog = UnsetupConfirmation(title="Confirm Unsetup", timeout=60)

    await ctx.response.send_modal(dialog)


@bot.slash_command(
    description="Reset a user's email to a specific value using their ID"
)
@discord.ext.commands.has_permissions(administrator=True)
async def set_email(ctx, user_id, email):
    try:
        user = session.query(DbUser).filter_by(ID=user_id).one()
    except:
        user = None
        await ctx.respond(
            f"User ID did not return a database row: {user_id}", ephemeral=True
        )
        return

    user.email = email

    session.merge(user)
    try:
        session.commit()
    except Exception as ex:
        await ctx.respond(
            "An unexpected database error occurred. Attempting to print traceback.",
            ephemeral=True,
        )
        print(ex.with_traceback())
    else:
        await ctx.respond(
            f"User with ID {user_id} set email to {email}", ephemeral=True
        )


@bot.slash_command(
    description="Reset a user's email to a specific value using their ID"
)
@discord.guild_only()
@discord.ext.commands.has_permissions(administrator=True)
async def set_ra(ctx, user_id):
    try:
        user = session.query(DbUser).filter_by(ID=user_id).one()
    except:
        user = None
        await ctx.respond(
            f"User ID did not return a database row: {user_id}", ephemeral=True
        )
        return

    member = discord.utils.get(ctx.guild.members, id=user_id)
    if not member:
        await ctx.respond(
            f"I couldn't find a member with the id {user_id}.", ephemeral=True
        )
        return

    try:
        await member.add_roles(
            discord.utils.get(ctx.guild.roles, name="RA"),
            reason=f"Member was manually assigned RA position",
        )
    except discord.errors.Forbidden:
        await ctx.respond(
            "I don't have permission to modify this user's roles. Ensure that my bot role is higher on the role list than the user's highest role.",
            ephemeral=True,
        )

    user.is_ra = True

    session.merge(user)

    try:
        session.commit()
    except Exception as ex:
        await ctx.respond(
            "An unexpected database error occurred. Attempting to print traceback.",
            ephemeral=True,
        )
        print(ex.with_traceback())
    else:
        await ctx.respond(
            f"User with ID {user_id} set to RA in database", ephemeral=True
        )


@bot.slash_command(
    description="Look up a user's email with their Discord ID (this is NOT their username)."
)
@discord.ext.commands.has_permissions(administrator=True)
async def lookup(ctx, user_id):
    try:
        user = session.query(DbUser).filter_by(ID=user_id).one()
        embed = discord.Embed(title="Lookup Results", color=discord.Colour.green())
        embed.add_field(name="User ID", value=f"{user_id}", inline=False)
        embed.add_field(name="Username", value=f"{user.username}", inline=False)
        embed.add_field(name="Email", value=f"{user.email}", inline=False)
        embed.add_field(name="Community", value=f"{user.community}", inline=False)
        embed.add_field(name="Is RA?", value=f"{'Yes ✅' if user.is_ra else 'No ❌'}")
        embed.add_field(
            name="Verified?", value=f"{'Yes ✅' if user.verified else 'No ❌'}"
        )
    except Exception as ex:
        embed = discord.Embed(
            title="Lookup Failed",
            description="The user ID provided did not return a user.",
            color=discord.Colour.red(),
        )
        embed.add_field(name="User ID", value=f"{user_id}", inline=False)

    await ctx.respond(embed=embed)


# ------------------------------- EVENT HANDLERS -------------------------------


# Clones scheduled events to residence hall servers when created on the hub server
# Does NOT support cloning event cover photos
@bot.event
async def on_scheduled_event_create(scheduled_event):
    # Stops the bot from cloning events created on non-hub servers
    if (scheduled_event.guild).id != HUB_SERVER_ID:
        return
    # Iterates through the residence hall servers and copies the event to each one, skipping the hub server
    for guild in bot.guilds:
        if guild.id == HUB_SERVER_ID:
            continue
        await guild.create_scheduled_event(
            name=scheduled_event.name,
            description=scheduled_event.description,
            location=scheduled_event.location,
            start_time=scheduled_event.start_time,
            end_time=scheduled_event.end_time,
        )


# Syncs updates to scheduled events across residence hall servers
# Does NOT support editing the title ("topic") of the event
# If the title must be changed, delete the event and create a new one
@bot.event
async def on_scheduled_event_update(old_scheduled_event, new_scheduled_event):
    # Stops the bot from syncing edits initiated on non-hub servers
    if (new_scheduled_event.guild).id != HUB_SERVER_ID:
        return
    # Iterates through the residence hall servers, skipping the hub server
    for guild in bot.guilds:
        if guild.id == HUB_SERVER_ID:
            continue
        # Iterates through the events in each residence hall server to find and edit the correct one
        for scheduled_event in guild.scheduled_events:
            if scheduled_event.name == new_scheduled_event.name:
                await scheduled_event.edit(
                    description=new_scheduled_event.description,
                    location=new_scheduled_event.location,
                    start_time=new_scheduled_event.start_time,
                    end_time=new_scheduled_event.end_time,
                )


# Syncs scheduled event cancellation across residence hall servers
# Cancels all events with the same name as the canceled event
@bot.event
async def on_scheduled_event_delete(deleted_event):
    # Stops the bot from syncing cancellations initiated on non-hub servers
    if (deleted_event.guild).id != HUB_SERVER_ID:
        return
    # Iterates through the residence hall servers, skipping the hub server
    for guild in bot.guilds:
        if guild.id == HUB_SERVER_ID:
            continue
        # Iterates through the events in each residence hall server to find and delete the correct one
        for scheduled_event in guild.scheduled_events:
            if scheduled_event.name == deleted_event.name:
                await scheduled_event.delete()


@bot.event
async def on_member_join(member: discord.Member):
    # Need to figure out what invite the user joined with
    # in order to assign the correct roles.

    Log.info(f"Member join event fired with {member.display_name}")

    # I'm thinking we should initiate verification here instead of
    # adding the roles, then the verify command does all of this code.

    # User is verifying for the guild they just joined
    user_to_guild[member.id] = member.guild

    # Create a dm channel between the bot and the user
    dm_channel = await member.create_dm()

    await dm_channel.send(
        content=f"Hey {member.name}! Welcome to {member.guild.name}. Before you get access to your ResLife community, we need you to verify yourself.\n\nTo do so, please see the verification channel in the server or type `/verify` and press enter.",
    )


@bot.event
async def on_guild_join(guild):
    # Automate call of setup

    # Track the landing channel (verify) of the server
    guild_to_landing[guild.id] = discord.utils.get(guild.channels, name="verify")
    # Log.info(f"{guild_to_landing=}")

    # Cache the invites for the guild as they currently stand (none should be present)
    invites_cache[guild.id] = await guild.invites()

    ra_role = discord.utils.get(guild.roles, name="RA")

    if not ra_role:
        try:
            ra_role = await guild.create_role(
                name="RA",
                hoist=True,
                permissions=discord.Permissions.advanced(),
                color=discord.Colour.red(),
            )
        except discord.Forbidden:
            Log.warning(
                "Attempted to create an RA role on join but do not have valid permissions."
            )

    this_guild = DbGuild(
        ID=guild.id,
        is_setup=True,
        ra_role_id=ra_role.id,
        landing_channel_id=guild_to_landing[guild.id].id,
    )

    session.merge(this_guild)

    try:
        session.commit()
    except IntegrityError as int_exception:
        Log.warning("Attempting to merge an already existent guild into the database failed:")
        print(int_exception.with_traceback())

    # Create a view that will contain a button which can be used to initialize the verification process
    view = VerifyView(timeout=None)

    # Finished
    await guild_to_landing[guild.id].send(
        content="Click the button below to get verified!", view=view
    )


@bot.event
async def on_ready():
    # Build a default invite cache
    for guild in bot.guilds:
        try:
            invites_cache[guild.id] = await guild.invites()
            for invite in invites_cache[guild.id]:
                try:
                    invite_obj = (
                        session.query(DbInvite).filter_by(code=invite.code).one()
                    )
                except:
                    continue
                else:
                    if invite_obj:
                        invite_to_role[invite.code] = discord.utils.get(
                            guild.roles, id=invite_obj.role_id
                        )
            Log.info(f"{invite_to_role=}")
        except discord.errors.Forbidden:
            continue

        # A little bit of a hack that prevents us from needing a database for guilds yet
        guild_to_landing[guild.id] = discord.utils.get(guild.channels, name="verify")

        # Create a view that will contain a button which can be used to initialize the verification process
        view = VerifyView(timeout=None)

        # Finished
        try:
            await guild_to_landing[guild.id].send(
                content="Click the button below to get verified!", view=view
            )
        except AttributeError:
            continue

    # Log.info(f"{guild_to_landing=}")


if DEBUG:
    print(
        f"""Bootstrapping bot...
---------------------------------------
{VERSION=}
{DATABASE_PATH=}
---------------------------------------
Hello :)
"""
    )

bot.run(TOKEN)
