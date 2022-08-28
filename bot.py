# pylint: disable=missing-class-docstring,missing-function-docstring

from collections import OrderedDict
import os
from sqlite3 import IntegrityError
from typing import Sequence
from urllib.request import urlopen
import discord
import discord.ext
from discord.ui import Button, View, Modal, InputText
import orjson
import sqlalchemy
import requests
from sqlalchemy.orm import sessionmaker
import util.invites
from util.log import Log
from util.db import DbGuild, DbInvite, DbUser, DbCategory, DbVerifyingUser, Base
from util.emojis import sync_add, sync_delete, sync_name


bot = discord.Bot(intents=discord.Intents.all())

# ------------------------------- INITIALIZATION -------------------------------

TOKEN = os.getenv("PITTBOT_TOKEN")
DEBUG = False
VERSION = "0.1.2"
DATABASE_PATH = "dbs/main.db"
HUB_SERVER_ID = 996607138803748954
BOT_COMMANDS_ID = 1006618232129585216
ERRORS_CHANNEL_ID = 1008400699689799712
LONG_DELETE_TIME = 60.0
SHORT_DELETE_TIME = 15.0
VERIFICATION_MESSAGE = "Click the button below to get verified!"

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

os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
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

# Category ID to role ID (IMPORTANT!) associativity
category_to_role = {}

# Associate each guild with its landing channel
guild_to_landing = {}

# This will not actually persistently associate every user with the guild they're in
# Rather, it will be used during verification to associate a verifying user
# with a guild, so that even if they are DMed verification rather
# than doing it in the server, we can still know what guild they're verifying for.
# A user CANNOT BE VERIFYING FOR MORE THAN ONE GUILD AT ONCE
user_to_guild = {}

# Cache of user IDs to their preferred nicknames
user_to_nickname = {}

# Cache of user IDs to overriden invite codes
# used to skip checks if verify is called by the dropdown view in the
# case of a possible race condition
override_user_to_code = {}

# Non-override cache of users to invites built when a member
# joins
user_to_invite = {}

# Assigned invites associativity
user_to_assigned_invite = {}

# Assigned roles associativity
user_to_assigned_role = {}

# Cache of emojis that were modified/deleted during a current synchronization
synced_emoji_cache = []

# ------------------------------- CLASSES -------------------------------


class VerifyModal(Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # self.children[0]
        self.add_item(
            InputText(label="Pitt Email Address", placeholder="abc123@pitt.edu")
        )
        # self.children[1]
        self.add_item(
            InputText(
                label="Preferred Name", required=False, placeholder="Preferred name"
            )
        )

    async def callback(self, interaction: discord.Interaction):
        verified = False
        email = self.children[0].value
        if self.children[1].value:
            user_to_nickname[interaction.user.id] = self.children[1].value
            Log.info(
                f"User {interaction.user.name}[{interaction.user.id}] set their preferred nickname to '{self.children[1].value}'"
            )
        if "@pitt.edu" in self.children[0].value:
            Log.ok(
                f"{interaction.user.name} attempted to verify with email '{email}'. This email was not rejected."
            )
            verified = True
        else:
            Log.warning(
                f"{interaction.user.name} attempted to verify with email '{email}' but was denied"
            )
            await interaction.response.send_message(
                "Only @pitt.edu emails will be accepted. Please retry by pressing the green button.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if not guild:
            if interaction.user.id in user_to_guild:
                guild = user_to_guild[interaction.user.id]
            else:
                Log.error(
                    f"Verification modal was submitted by {interaction.user.name}[{interaction.user.id}] but was not associated with a guild."
                )
                await interaction.response.send_message(
                    "We couldn't find out which server you wanted to verify for. Please retry by pressing the green button or typing `/verify` in the verify channel.",
                    ephemeral=True,
                )

        member = discord.utils.get(guild.members, id=interaction.user.id)

        if not member:
            member = interaction.user

        logs_channel = discord.utils.get(guild.channels, name="logs")

        invite = user_to_assigned_invite[member.id]

        if not invite:
            Log.error(
                f"Verification modal was submitted by {interaction.user.name}[{interaction.user.id}] but was not associated with any invite."
            )
            if logs_channel:
                await logs_channel.send(
                    f"Verification modal was submitted by {interaction.user.name}[{interaction.user.id}] but was not associated with any invite."
                )
            await interaction.response.send_message(
                "We couldn't find out which invite link you used to join. Please retry by pressing the green button or typing `/verify` in the verify channel.",
                ephemeral=True,
            )

        assigned_role = user_to_assigned_role[member.id]

        if not assigned_role:
            Log.error(
                f"Verification modal was submitted by {interaction.user.name}[{interaction.user.id}] but was not associated with any assigned role."
            )
            if logs_channel:
                await logs_channel.send(
                    f"Verification modal was submitted by {interaction.user.name}[{interaction.user.id}] but was not associated with any assigned role."
                )
            await interaction.response.send_message(
                "We couldn't find out which community you tried to join. Please retry by pressing the green button or typing `/verify` in the verify channel.",
                ephemeral=True,
            )

        # Set the user's nickname to their email address or preferred name on successful verification
        if member.id in user_to_nickname:
            nickname = user_to_nickname[member.id]
        else:
            nickname = email[: email.find("@pitt.edu")]

        await member.edit(nick=nickname)

        # Send message in logs channel when they successfully verify
        Log.ok(f"Verified {member.name} with email '{email}'")
        if logs_channel:
            await logs_channel.send(
                content=f"Verified {member.name} with email '{email}'"
            )

        # Need to give the member the appropriate role
        is_user_ra = False
        # If the invite code's use was previously zero, then we should actually give the user
        # the RA role, in addition to the RA X's community role.
        if invite.uses == 0:
            # First use of invite
            is_user_ra = True
            ra_role = discord.utils.get(guild.roles, name="RA")
            if ra_role:
                await member.add_roles(
                    ra_role,
                    reason=f"Member joined with first use of invite code {invite.code}",
                )
            else:
                Log.error(
                    f"Guild {guild.name}[{guild.id}] has no role named 'RA' but user {member.name}[{member.id}] should have received this role"
                )

        else:
            # Otherwise resident
            residents_role = discord.utils.get(guild.roles, name="residents")
            if residents_role:
                await member.add_roles(
                    residents_role,
                    reason=f"Member joined with {invite.code} after RA already set.",
                )
            else:
                Log.error(
                    f"Guild {guild.name}[{guild.id}] does not have a role named 'residents' but user {member.name}[{member.id}] should have received this role"
                )

        if assigned_role:
            await member.add_roles(
                assigned_role,
                reason=f"Member joined with invite code {invite.code}",
            )
            if logs_channel:
                await logs_channel.send(
                    f"User {member.name}[{member.id}] has been verified with role {assigned_role}."
                )
        else:
            Log.error(
                "Bot was not able to determine a role from the invite link used. Aborting."
            )
            if logs_channel:
                await logs_channel.send(
                    f"Unable to determine a role from the invite link used by {member.name}[{member.id}]. No roles will be applied."
                )
            await interaction.response.send_message(
                "The invite used couldn't associate you with a specific community, please let your RA know!",
            )
            return

        await interaction.response.send_message(
            f"Welcome {interaction.user.mention}! Thank you for verifying. You can now exit this channel. Check out the channels on the left! If you are on mobile, click the three lines in the top left.",
            ephemeral=True,
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

        # Unset caches used for verification
        if member.id in user_to_assigned_invite:
            del user_to_assigned_invite[member.id]
        if member.id in user_to_assigned_role:
            del user_to_assigned_role[member.id]
        if member.id in user_to_guild:
            del user_to_guild[member.id]
        if member.id in override_user_to_code:
            del override_user_to_code[member.id]
        if member.id in user_to_invite:
            del user_to_invite[member.id]
        if member.id in user_to_nickname:
            del user_to_nickname[member.id]
        try:
            session.commit()
        except:
            session.rollback()
            Log.error(
                f"Could not save any database entries for {member.name}[{member.id}]. This is a critical DB error."
            )

        async def on_timeout(self):
            self.stop()


class ManualRoleSelectModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.return_code = None
        self.add_item(
            discord.ui.InputText(
                label="Invite Link",
                placeholder="Please paste the full invite link you were sent.",
            )
        )

    async def callback(self, interaction: discord.Interaction):
        whole_code = self.children[0].value
        if "https://discord.gg/" in whole_code:
            self.return_code = whole_code[19:]
        elif "discord.gg/" in whole_code:
            self.return_code = whole_code[11:]


class CommunitySelectDropdown(discord.ui.Select):
    def __init__(self, *args, choices=None, opts_to_inv=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.opts_to_inv = opts_to_inv
        self.placeholder = "Choose your community"
        self.min_values = 1
        self.max_values = 1
        self.options = []
        for choice in choices:
            self.add_option(label=choice)

    async def callback(self, interaction: discord.Interaction):
        override_user_to_code[interaction.user.id] = self.opts_to_inv[self.values[0]]
        user_to_invite[interaction.user.id] = self.opts_to_inv[self.values[0]]
        # Add row to database
        verifying_data = DbVerifyingUser(
            ID=interaction.user.id, invite_code=user_to_invite[interaction.user.id].code
        )

        session.merge(verifying_data)
        try:
            session.commit()
        except:
            session.rollback()
            Log.error(
                f"Couldn't add {interaction.userber.name}[{interaction.user.id}] to VerifyingUsers database."
            )

        Log.ok(f"{override_user_to_code=}")
        await verify(interaction)


class CommunitySelectView(discord.ui.View):
    def __init__(self, *args, choices=None, opts_to_inv=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.opts = choices
        select_menu = CommunitySelectDropdown(
            choices=self.opts, opts_to_inv=opts_to_inv
        )
        self.add_item(select_menu)

class EmojiSyncView(discord.ui.View):
    # Might be able to delete guild reference
    def __init__(self, emoji, mod_type: str, old_emoji=None, *args, **kwargs):
        super().__init__(timeout=None, *args, **kwargs)
        self.emoji = emoji
        self.old_emoji = old_emoji
        
        # Mod type will be a String of 'Add', 'Del', or 'Name' 
        self.mod_type = mod_type

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.green)
    async def accept_callback(self, button, interaction: discord.Interaction):
        await interaction.response.edit_message(content='Okay! I will sync this now.', view=None, delete_after=60)

        # Do the operation
        if self.mod_type == 'Add':
            await sync_add(bot=bot, emoji=self.emoji)
        elif self.mod_type == 'Del':
            await sync_delete(bot=bot, emoji=self.emoji)
        else:
            await sync_name(bot=bot, old_emoji=self.old_emoji, new_emoji=self.emoji)

    @discord.ui.button(label='Deny', style=discord.ButtonStyle.red)
    async def deny_callback(self, button, interaction: discord.Interaction):
        # Do nothing!
        await interaction.response.edit_message(content='Okay! This change will not be synced.', view=None, delete_after=60)

class UnsetupConfirmation(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(InputText(label="Type Yes to Confirm"))

    async def callback(self, interaction: discord.Interaction):
        if self.children[0].value.lower() == "yes":
            try:
                guild_obj = (
                    session.query(DbGuild).filter_by(ID=interaction.guild.id).one()
                )
            except Exception:
                guild_obj = None

            if guild_obj:
                guild_obj.is_setup = False
                guild_obj.landing_channel_id = None
                guild_obj.ra_role_id = None
                session.merge(guild_obj)
                try:
                    session.commit()
                except Exception as ex:
                    session.rollback()
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


class URLModal(Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(InputText(label="URL"))

        self.url = ""

    async def callback(self, interaction: discord.Interaction):
        self.url = self.children[0].value
        await interaction.response.defer()
        self.stop()


class VerifyView(View):
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

    Log.info(f"Starting verify for {author.name}[{author.id}]")

    try:
        user = session.query(DbUser).filter_by(ID=author.id).one()
    except Exception:
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
            ephemeral=True,
        )
        return

    # Get invite snapshot ASAP after guild is determined
    # Invites after user joined.
    # Notice that these snapshots will only be used in the
    # event that assigning an invite on member join fails, which should be EXCEEDINGLY rare.
    invites_now = await guild.invites()

    # Invites before user joined
    old_invites = invites_cache[guild.id]

    member = discord.utils.get(guild.members, id=author.id)

    # Get logs channel for errors
    logs_channel = discord.utils.get(guild.channels, name="logs")
    if not logs_channel:
        Log.warning(f"No channel named 'logs' was found in {guild.name}[{guild.id}]")

    if not member:
        await ctx.response.send_message(
            f"It doesn't look like we could verify that you are in the server {guild.name}. Press the green 'verify' button inside the server's `#verify` channel.",
        )
        return

    verified = False

    assigned_role = None

    try:
        verifying_user = session.query(DbVerifyingUser).filter_by(ID=member.id).one()
        invite = next(
            filter(lambda inv: inv.code == verifying_user.invite_code, old_invites),
            None,
        )
    except:
        verifying_user = None

    if member.id in user_to_invite:
        invite = user_to_invite[member.id]
        if invite.code in invite_to_role:
            assigned_role = invite_to_role[invite.code]
            Log.ok(
                f"Invite link {invite.code} is cached with '{assigned_role}', assigning this role."
            )
        else:
            try:
                inv_object = session.query(DbInvite).filter_by(code=invite.code).one()
            except Exception:
                inv_object = None

            if inv_object:
                assigned_role = discord.utils.get(guild.roles, id=inv_object.role_id)
                if not assigned_role:
                    await ctx.response.send_message(
                        "We couldn't find a role to give you, ask your RA for help!"
                    )
                    Log.error(
                        f"Databased invite '{inv_object.code}' did not return a role to assign to {member.name}[{member.id}]. This is an error."
                    )
                    if logs_channel:
                        await logs_channel.send(
                            content=f"Databased invite '{inv_object.code}' did not return a role to assign to {member.name}[{member.id}]. This is an error."
                        )
                    # Abort
                    return

    elif verifying_user and invite:
        if invite.code in invite_to_role:
            assigned_role = invite_to_role[invite.code]
            Log.ok(
                f"Invite link {invite.code} is cached with '{assigned_role}', assigning this role."
            )
        else:
            try:
                inv_object = session.query(DbInvite).filter_by(code=invite.code).one()
            except Exception:
                inv_object = None

            if inv_object:
                assigned_role = discord.utils.get(guild.roles, id=inv_object.role_id)
                if not assigned_role:
                    await ctx.response.send_message(
                        "We couldn't find a role to give you, ask your RA for help!"
                    )
                    Log.error(
                        f"Databased invite '{inv_object.code}' did not return a role to assign to {member.name}[{member.id}]. This is an error."
                    )
                    if logs_channel:
                        await logs_channel.send(
                            content=f"Databased invite '{inv_object.code}' did not return a role to assign to {member.name}[{member.id}]. This is an error."
                        )
                    # Abort
                    return
    else:

        # This should almost NEVER run
        # Such an insane cascade of problems has to occur for
        # this specific block of code to run, and it should be
        # optimally removed eventually.
        # For now, though, what this bot has taught me is that
        # what can go wrong will go wrong.

        potential_invites = []

        for possible_invite in old_invites:
            Log.info(f"Checking {possible_invite.code}")
            new_invite = util.invites.get_invite_from_code(
                invites_now, possible_invite.code
            )
            if not new_invite:
                # The invite is invalid or somehow inaccessible
                Log.warning(
                    f"Invite code {possible_invite.code} was invalid or inaccessible, it will be skipped."
                )
                continue
            # O(n²)
            if possible_invite.uses < new_invite.uses:

                # This is POTENTIALLY the right code
                invite = possible_invite  # If all else fails, grab the first one, which is usually right

                # Who joined and with what link
                Log.info(f"Potentially invite Code: {possible_invite.code}")

                potential_invites.append(possible_invite)

        num_overlap = len(potential_invites)

        Log.info(f"{potential_invites=}")

        assigned_role = None

        if member.id not in override_user_to_code:

            if num_overlap == 1:
                invite = potential_invites[0]
                if invite.code in invite_to_role:
                    assigned_role = invite_to_role[invite.code]
                    Log.ok(
                        f"Invite link {invite.code} is cached with '{assigned_role}', assigning this role."
                    )
                else:
                    try:
                        inv_object = (
                            session.query(DbInvite).filter_by(code=invite.code).one()
                        )
                    except Exception:
                        inv_object = None

                    if inv_object:
                        assigned_role = discord.utils.get(
                            guild.roles, id=inv_object.role_id
                        )
                        if not assigned_role:
                            await ctx.response.send_message(
                                "We couldn't find a role to give you, please let your RA know!"
                            )
                            Log.error(
                                f"Databased invite '{inv_object.code}' did not return a role to assign to {member.name}[{member.id}]. This is an error."
                            )
                            if logs_channel:
                                await logs_channel.send(
                                    content=f"Databased invite '{inv_object.code}' did not return a role to assign to {member.name}[{member.id}]. This is an error."
                                )
                            # Abort
                            return

            elif num_overlap > 1:
                # Code for potential overlap
                options = []
                options_to_inv = {}

                # Build options for dropdown
                for inv in potential_invites:
                    if inv.code in invite_to_role:
                        role = invite_to_role[inv.code]
                        Log.ok(
                            f"Invite link {inv.code} is cached with '{role.name}', adding to modal options for manual select."
                        )
                        options.append(role.name)
                        options_to_inv[role.name] = inv
                    else:
                        try:
                            inv_object = (
                                session.query(DbInvite).filter_by(code=inv.code).one()
                            )
                        except Exception:
                            inv_object = None

                        if inv_object:
                            Log.ok(f"Invite link {inv.code} was found in the database.")
                            role = discord.utils.get(guild.roles, id=inv_object.role_id)
                            if role:
                                Log.ok(
                                    f"Databased invite '{inv.code}' returned a valid role '{role.name}', assigning this role."
                                )
                                options.append(role.name)
                                options_to_inv[role.name] = inv
                            else:
                                Log.error(
                                    f"Databased invite '{inv.code}' did not return a role to assign to {member.name}[{member.id}]. This is an error."
                                )
                                await ctx.followup.send(
                                    f"The invite link '{inv.code}' couldn't associate you with a specific community, please let your RA know!",
                                )
                                if logs_channel:
                                    await logs_channel.send(
                                        content=f"Databased invite '{inv.code}' did not return a role to assign to {member.name}[{member.id}]. This is an error."
                                    )
                        else:
                            Log.error(
                                f"Invite link {inv.code} was neither cached nor found in the database. This code will be ignored. This is an error. "
                            )
                            await ctx.followup.send(
                                f"The invite link '{inv.code}' couldn't associate you with a specific community, please let your RA know!",
                            )
                            if logs_channel:
                                await logs_channel.send(
                                    content=f"The invite link '{inv.code}' couldn't associate {member.name}[{member.id}] with a specific community. This will probably need manual override.",
                                )

                # Send view with options and bail out of function
                # It will be re-initiated by the dropdown menu
                Log.info(f"{options=}")
                view = CommunitySelectView(
                    choices=options, opts_to_inv=options_to_inv, timeout=180
                )

                await ctx.response.send_message(
                    content="For security, we must verify which community you belong to. Please select your community below!",
                    view=view,
                    ephemeral=True,
                )

                # Bail
                return

            else:
                # Error
                Log.error(
                    f"No valid invite link was found when user {member.name}[{member.id}] verified. This is operation-abortive."
                )
                if logs_channel:
                    await logs_channel.send(
                        content=f"**WARNING**: No valid invite link was found when user {member.name}[{member.id}] verified. This will abort verification and require manual override."
                    )
                Log.error(f"{num_overlap=}")
                Log.error(f"{potential_invites=}")
                await ctx.response.send_message(
                    content="No valid invite link could associate you with a specific community, please let your RA know!",
                    ephemeral=True,
                )
                # Abort
                return

        else:
            # Member has been overriden
            invite_code = override_user_to_code[member.id].code
            Log.info(f"Got {invite_code=}")
            # This literally MUST be cached or something is SIGNIFICANTLY wrong
            invite = next(
                filter(lambda inv: inv.code == invite_code, old_invites), None
            )
            Log.info(f"Got {old_invites=}")
            if not invite:
                await ctx.response.send_message(
                    "We couldn't find a valid invite code associated with the community you selected.",
                )
                if logs_channel:
                    await logs_channel.send(
                        f"Failed to associate invite to role for user {member.name}[{member.id}], no roles were assigned."
                    )
                Log.error(
                    f"Failed to associate invite to role for user {member.name}[{member.id}], aborting and dumping: {override_user_to_code=}"
                )
                return
            if invite_code in invite_to_role:
                role = invite_to_role[invite_code]
                assigned_role = role
                Log.ok(
                    f"Overriden invite code '{invite_code}' correctly associated with '{role.name}'"
                )
                if logs_channel:
                    await logs_channel.send(
                        "User {member.name}[{member.id}] used cached invite '{invite_code}'"
                    )
            else:
                try:
                    inv_object = (
                        session.query(DbInvite).filter_by(code=invite_code).one()
                    )
                except Exception:
                    inv_object = None

                if inv_object:
                    Log.ok(f"Invite link {invite_code} was found in the database.")
                    role = discord.utils.get(guild.roles, id=inv_object.role_id)
                    if role:
                        Log.ok(
                            f"Databased invite '{invite_code}' returned a valid role '{role.name}', assigning this role."
                        )
                        assigned_role = role
                        if logs_channel:
                            await logs_channel.send(
                                "User {member.name}[{member.id}] used databased invite '{invite_code}'"
                            )
                    else:
                        Log.error(
                            f"Databased invite '{invite_code}' did not return a role. This is an error."
                        )
                        if logs_channel:
                            await logs_channel.send(
                                f"Databased invite '{invite_code}' was not associated with a role. User {member.name}[{member.id}] will need to be manually set."
                            )
                        await ctx.response.send_message(
                            f"The invite link '{invite_code}' couldn't associate you with a specific community, please let your RA know!",
                        )
                        return
                else:
                    Log.error(
                        f"Invite link {invite_code} was neither cached nor found in the database. This code will be ignored. This is an error. "
                    )
                    await ctx.response.send_message(
                        f"The invite link '{invite_code}' couldn't associate you with a specific community, please let your RA know!",
                    )
                    return

    # Begin ACTUAL VERIFICATION

    # Ensure session is committed before leaving function
    try:
        session.commit()
    except:
        session.rollback()

    user_to_assigned_invite[member.id] = invite
    user_to_assigned_role[member.id] = assigned_role

    modal = VerifyModal(title="Verification", timeout=60)

    await ctx.response.send_modal(modal)

    # Keep this line actually, invites cache will get updated after it.
    await modal.wait()

    # Update cache
    invites_cache[guild.id] = invites_now


@bot.slash_command(
    description="Create categories based off of a hastebin/pastebin list of RA names."
)
@discord.guild_only()
@discord.ext.commands.has_permissions(manage_channels=True)
async def make_categories(
    ctx,
    link: discord.Option(
        str,
        description="URL to raw hastebin or pastebin page with list of RAs in format 'lastname firstname' per line",
    ),
):
    # Necessary because of Python's dynamic name binding and the way '|=' works
    global category_to_role

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
        invite_role_dict, category_role_dict = await util.invites.make_categories(
            guild, ras, guild_to_landing[guild.id]
        )

        # Check that categories were generated correctly
        if not category_role_dict:
            await ctx.send_followp(
                "Failed to associate categories to their roles. This is an internal error.",
                ephemeral=True,
            )
            Log.error(
                "Failed to associate categories to their roles. This is an internal error."
            )
            return

        # Check that invites were generated correctly
        if not invite_role_dict:
            await ctx.send_followp(
                "Failed to make invites. Check that a #verify channel exists.",
                ephemeral=True,
            )
            Log.error("Failed to generate any new invites.")
            return

        # Update category to role cache with newly generated categories
        category_to_role |= category_role_dict

        # Serialize new items added to category_to_role here
        for category_id, role_id in category_role_dict.items():
            category_obj = DbCategory(ID=category_id, role_id=role_id)

            try:
                session.merge(category_obj)
            except Exception:
                Log.error(f"Couldn't merge {{{category_id}:{role_id}}} to database.")
        try:
            session.commit()
        except Exception:
            session.rollback()
            Log.error(f"Couldn't merge any categories into to database.")

        # Update invite cache, important for on_member_join's functionality
        invites_cache[guild.id] = await guild.invites()

        # Iterate over the invites, adding the new role object
        # to our global dict if it was just created.
        for invite in invites_cache[guild.id]:
            if invite.code in invite_role_dict:
                invite_obj = DbInvite(
                    code=invite.code,
                    guild_id=guild.id,
                    role_id=invite_role_dict[invite.code].id,
                )
                session.merge(invite_obj)
                invite_to_role[invite.code] = invite_role_dict[invite.code]
        try:
            session.commit()
        except:
            session.rollback()

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
    except Exception:
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
        session.rollback()
        Log.warning(
            "Attempting to merge an already existent guild into the database failed:"
        )
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
    description="Reset a user's email using their ID. set_user is preferred."
)
@discord.ext.commands.has_permissions(administrator=True)
async def set_email(
    ctx,
    member: discord.Option(discord.Member, "Member to set email for."),
    email: discord.Option(str, "Email address"),
):
    try:
        user = session.query(DbUser).filter_by(ID=member.id).one()
    except:
        member = ctx.guild.get_member(member.id)
        if not member:
            Log.error(f"No member returned for {member}")
            await ctx.response.send_message(
                content=f"Couldn't find a member '{member}' in this guild.",
                ephemeral=True,
            )
            return

        user = DbUser(
            ID=member.id,
            username=member.name,
            email=email,
            verified=True,
            is_ra=False,
            community="resident",  # Preferable to use set_user
        )
        session.merge(user)
        try:
            session.commit()
        except:
            session.rollback()
        return

    user.email = email

    if "@pitt.edu" in email:
        pitt_id = email[: email.find("@pitt.edu")]
    else:
        pitt_id = email

    await member.edit(nick=pitt_id)

    session.merge(user)
    try:
        session.commit()
    except Exception as ex:
        session.rollback()
        await ctx.respond(
            "An unexpected database error occurred. Attempting to print traceback.",
            ephemeral=True,
        )
        print(ex.with_traceback())
    else:
        await ctx.respond(f"User {member} set email to {email}", ephemeral=True)


@bot.slash_command(description="Manually set up and verify a user")
@discord.guild_only()
@discord.ext.commands.has_permissions(administrator=True)
async def set_user(
    ctx,
    member: discord.Option(discord.Member, "Member to edit"),
    role: discord.Option(discord.Role, "Role to assign"),
    email: discord.Option(str, "Email address"),
    is_ra: discord.Option(bool, "Is user an RA or not?"),
    nickname: discord.Option(str, "Preferred name to assign user", required=False),
):

    if not role:
        Log.error(f"No role returned for {role}: {role=}")
        await ctx.response.send_message(
            content=f"Couldn't find a role '{role}' in this guild.", ephemeral=True
        )
        return

    if not member:
        Log.error(f"No member returned for {member}")
        await ctx.response.send_message(
            content=f"Couldn't find a member '{member}' in this guild.", ephemeral=True
        )
        return
    try:
        await member.add_roles(role, reason="Manual override")
    except discord.errors.Forbidden:
        await ctx.followup.send(
            content="I don't have permission to modify this user's roles. Ensure that my bot role is higher on the role list than the user's highest role.",
            ephemeral=True,
        )

    if "@pitt.edu" in email:
        pitt_id = email[: email.find("@pitt.edu")]
    else:
        pitt_id = email

    if nickname:
        await member.edit(nick=nickname)
    else:
        await member.edit(nick=pitt_id)

    if is_ra:
        ra_role = discord.utils.get(ctx.guild.roles, name="RA")
        if not ra_role:
            Log.warning(
                f"Guild {ctx.guild.name}[{ctx.guild.id}] does not have a role named 'RA'"
            )
            await ctx.followup.send(
                content="There is no role named 'RA' in this guild, but the user was set to be an RA. User will not receive any elevated RA role.",
                ephemeral=True,
            )
        else:
            try:
                await member.add_roles(ra_role, reason="Manual override")
            except discord.errors.Forbidden:
                await ctx.followup.send(
                    content="I don't have permission to modify this user's roles. Ensure that my bot role is higher on the role list than the user's highest role.",
                    ephemeral=True,
                )
    else:
        try:
            residents_role = discord.utils.get(ctx.guild.roles, name="residents")
            if residents_role:
                await member.add_roles(residents_role, reason="Manual override")
            else:
                await ctx.followup.send(
                    content="There is no role named 'residents' in this guild, but the user was set not to be an RA. User will not receive any 'residents' role.",
                    ephemeral=True,
                )
        except discord.errors.Forbidden:
            await ctx.followup.send(
                content="I don't have permission to modify this user's roles. Ensure that my bot role is higher on the role list than the user's highest role.",
                ephemeral=True,
            )

    try:
        user = session.query(DbUser).filter_by(ID=member.id).one()
        Log.ok(f"User {member.name} was in the database.")
    except:
        Log.warning(
            f"User {member.name} wasn't found in the database, so a new row will be committed."
        )
        user = DbUser(
            ID=member.id,
            username=member.name,
            email=email,
            verified=True,
            is_ra=is_ra,
            community=role.name,
        )
        session.merge(user)
        try:
            session.commit()
        except:
            session.rollback()

        await ctx.response.send_message(
            content="All set! {member.name} has been added to the database.",
            ephemeral=True,
        )

        return

    user.email = email
    user.username = member.name
    user.verified = True
    user.is_ra = is_ra
    user.community = role.name

    session.merge(user)
    try:
        session.commit()
    except:
        session.rollback()

    await ctx.response.send_message(
        content="All set! {member.name} has been updated.", ephemeral=True
    )


@bot.slash_command(
    description="Reset a user's email to a specific value using their ID"
)
@discord.guild_only()
@discord.ext.commands.has_permissions(administrator=True)
async def set_ra(
    ctx,
    member: discord.Option(discord.Member, "User to set as an RA"),
    community: discord.Option(
        discord.Role, "The community role which this RA oversees"
    ),
):
    try:
        user = session.query(DbUser).filter_by(ID=member.id).one()
    except:
        if not member:
            Log.error(f"No member returned for {member}")
            await ctx.response.send_message(
                content=f"Couldn't find a member '{member}' in this guild.",
                ephemeral=True,
            )
            return

        if community:
            try:
                await member.add_roles(community, reason="Manual override")
            except discord.errors.Forbidden:
                await ctx.respond(
                    "I don't have permission to modify this user's roles. Ensure that my bot role is higher on the role list than the user's highest role.",
                    ephemeral=True,
                )

        user = DbUser(
            ID=member.id,
            username=member.name,
            email="NONE",
            verified=True,
            is_ra=False,
            community=community.name,
        )
        session.merge(user)
        try:
            session.commit()
        except:
            session.rollback()
        return

    if not member:
        await ctx.respond(f"I couldn't find a member {member}.", ephemeral=True)
        return

    ra_role = discord.utils.get(ctx.guild.roles, name="RA")
    if not ra_role:
        Log.warning(
            f"Guild {ctx.guild.name}[{ctx.guild.id}] does not have a role named 'RA'"
        )
        await ctx.followup.send(
            "There is no role named 'RA' in this guild, but the user was set to be an RA. User will not receive any elevated RA role.",
            ephemeral=True,
        )
    else:
        try:
            await member.add_roles(
                ra_role,
                reason="Manual override",
            )
        except discord.errors.Forbidden:
            await ctx.respond(
                "I don't have permission to modify this user's roles. Ensure that my bot role is higher on the role list than the user's highest role.",
                ephemeral=True,
            )

    if community:
        try:
            await member.add_roles(community, reason="Manual override")
            user.community = community.name
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
        session.rollback()
        await ctx.respond(
            "An unexpected database error occurred. Attempting to print traceback.",
            ephemeral=True,
        )
        print(ex.with_traceback())
    else:
        await ctx.respond(f"User {member} set to RA in database", ephemeral=True)


@bot.slash_command(
    description="Look up a user's email with their Discord ID (this is NOT their username)."
)
@discord.ext.commands.has_permissions(administrator=True)
async def lookup(ctx, member: discord.Option(discord.Member, "User to lookup")):
    try:
        user = session.query(DbUser).filter_by(ID=member.id).one()
        embed = discord.Embed(title="Lookup Results", color=discord.Colour.green())
        embed.add_field(name="User ID", value=f"{member.id}", inline=False)
        embed.add_field(name="Username", value=f"{user.username}", inline=False)
        embed.add_field(name="Email", value=f"{user.email}", inline=False)
        embed.add_field(name="Community", value=f"{user.community}", inline=False)
        embed.add_field(name="Is RA?", value=f"{'Yes ✅' if user.is_ra else 'No ❌'}")
        embed.add_field(
            name="Verified?", value=f"{'Yes ✅' if user.verified else 'No ❌'}"
        )
    except Exception:
        embed = discord.Embed(
            title="Lookup Failed",
            description="The user ID provided did not return a user.",
            color=discord.Colour.red(),
        )
        embed.add_field(name="User ID", value=f"{member.id}", inline=False)

    await ctx.respond(embed=embed)


@bot.slash_command(
    description="Manually drop a user from the database/remove them from verification list."
)
@discord.ext.commands.has_permissions(administrator=True)
async def reset_user(
    ctx,
    member: discord.Option(discord.Member, "Member to reset"),
    drop_invite_code: discord.Option(
        bool,
        "Whether to erase association with invite code",
        required=False,
        default=False,
    ),
):
    try:
        user_count = session.query(DbUser).filter_by(ID=member.id).delete()
    except:
        user_count = 0
        await ctx.respond(
            f"User ID did not return a database row or could not be deleted: {member.id}",
            ephemeral=True,
        )
        return

    if drop_invite_code:
        try:
            verifying_user_count = (
                session.query(DbVerifyingUser).filter_by(ID=member.id).delete()
            )
        except:
            verifying_user_count = 0
            await ctx.respond(
                f"User ID did not return a database row for VerifyingUsers or could not be deleted: {member.id}",
                ephemeral=True,
            )
            return

    try:
        session.commit()
    except:
        session.rollback()

    if user_count > 0:
        if verifying_user_count > 0:
            await ctx.respond(
                f"Dropped row for user with ID in both table Users and table VerifyingUsers: {member.id}",
                ephemeral=True,
            )
        else:
            await ctx.respond(
                f"Dropped row for user with ID in table Users: {member.id}",
                ephemeral=True,
            )
    elif verifying_user_count > 0:
        await ctx.respond(
            f"Dropped row for user with ID in table VerifyingUsers: {member.id}",
            ephemeral=True,
        )
    else:
        await ctx.respond(
            f"No database row exists for user {member.name}[{member.id}], nothing to drop.",
            ephemeral=True,
        )


@bot.slash_command(
    description="Manually drop a user from the database/remove them from verification list."
)
@discord.ext.commands.has_permissions(administrator=True)
async def prune_pending(ctx):
    # Get logs channel
    logs_channel = discord.utils.get(ctx.guild.channels, name="logs")

    # Defer response due to slow operation
    await ctx.defer(ephemeral=True)

    # Iterate over members
    num_pruned = 0
    pruned = []
    async for member in ctx.guild.fetch_members():
        if len(member.roles) <= 1:
            # Member will be pruned
            Log.info(
                f"Pruning member {member.name}[{member.id}] as they have one or fewer roles (@/everyone)"
            )
            if logs_channel:
                await logs_channel.send(
                    f"Pruning member {member.name}[{member.id}] as they have one or fewer roles (@/everyone)"
                )

            # Get DM channel
            dm_channel = await member.create_dm()

            # Notify them
            if dm_channel:
                try:
                    await dm_channel.send(
                        f"Oh no! It looks like your verification period expired for the server {ctx.guild.name}. Please re-join with the invite your RA sent you and press the green verify button once you join."
                    )
                except discord.Forbidden:
                    Log.warning(
                        f"Member {member.name}[{member.id}] does not allow DMs or creating a DM failed, could not notify them of prune."
                    )
                    if logs_channel:
                        await logs_channel.send(
                            f"**WARNING**: Member {member.name}[{member.id}] does not allow DMs or creating a DM failed, could not notify them of prune."
                        )
            else:
                Log.warning(
                    f"Member {member.name}[{member.id}] does not allow DMs or creating a DM failed, could not notify them of prune."
                )
                if logs_channel:
                    await logs_channel.send(
                        f"**WARNING**: Member {member.name}[{member.id}] does not allow DMs or creating a DM failed, could not notify them of prune."
                    )

            # Kick member
            try:
                await member.kick(reason="Pruned for not initiating verification")
            except discord.Forbidden:
                Log.warning(
                    f"Member {member.name}[{member.id}] cannot be kicked due to a permissions error."
                )
                continue

            num_pruned += 1
            pruned.append(member)

    # Respond with ephemeral list of members pruned
    message_content = f"**{num_pruned} members were pruned:**\n"

    for mem in pruned:
        message_content += f"{mem}\n"

    # Reply with members pruned
    await ctx.followup.send(content=message_content, ephemeral=True)


@bot.slash_command(
    description="Manually link any categories whose names match a role, for backwards compatibility."
)
@discord.ext.commands.has_permissions(administrator=True)
@discord.guild_only()
async def auto_link(ctx):
    global category_to_role

    # For backwards compatibility, search through all categories in the
    # server and if any has a name that matches a role exactly, link that
    # category to that role by hand.

    channels = await ctx.guild.fetch_channels()

    category_role_dict = {}

    # List of tuples where tuple[0] = category name and tuple [1] = linked or not linked
    changed_categories = []

    linked = 0

    for channel in channels:
        if type(channel) is discord.CategoryChannel:
            role = discord.utils.get(ctx.guild.roles, name=channel.name)
            if role:
                Log.info(
                    f"Attempting to link category {channel.name}[{channel.id}] with role {role.name}[{role.id}]"
                )
                category_role_dict[channel.id] = role.id
                linked += 1
                changed_categories.append((channel.name, True))
            else:
                changed_categories.append((channel.name, False))

    category_to_role |= category_role_dict

    # Serialize new items added to category_to_role in the database
    for category_id, role_id in category_role_dict.items():
        category_obj = DbCategory(ID=category_id, role_id=role_id)

        try:
            session.merge(category_obj)
        except Exception:
            Log.error(f"Couldn't merge {{{category_id}:{role_id}}} to database.")
            await ctx.followup.send(
                content=f"We couldn't merge {{{category_id}:{role_id}}} into the database.",
                ephemeral=True,
            )
        else:
            Log.ok(f"Linked {category_id} to {role_id}")
    try:
        session.commit()
    except Exception:
        session.rollback()
        Log.error("Couldn't merge any categories into to database.")
        await ctx.respond(
            content="We couldn't merge any categories into the database.",
            ephemeral=True,
        )
        return

    message_content = f"Linked {linked} categories to associated roles.\n"

    # Upload a list of categories and whether they were changed or not
    for category_name, link_status in changed_categories:
        status = ":white_check_mark:" if link_status else ":no_entry_sign:"
        message_content += f"\n{category_name}: {status}"

    await ctx.respond(content=message_content, ephemeral=True)


# initialize an ordered hashmap to store FAQs and their answers
questions_and_answers = OrderedDict()


# PLEASE KEEP KEYS IN ALPHABETICAL ORDER
questions_and_answers["computer_labs"] = ">>> The hours of operation for the University's computing labs are located here: \nhttps://www.technology.pitt.edu/services/student-computing-labs"
questions_and_answers["covid"] = ">>> Information about vaccines and Pitt campuses' current COVID-19 levels can be found here: \nhttps://www.coronavirus.pitt.edu/\n\nMasking indoors is **required** when your campus's community level is `High`."
questions_and_answers["dining_dollars"] = ">>> This is a list of off-campus vendors that accept Pitt Dining Dollars: \nhttps://dineoncampus.com/pitt/offcampus-vendors"
questions_and_answers["dining_hours"] = ">>> The hours of operation for campus eateries are located here: \nhttps://dineoncampus.com/pitt/hours-of-operation"
questions_and_answers["library_hours"] = ">>> The hours of operation for University libraries are located here: \nhttps://www.library.pitt.edu/hours"
questions_and_answers["panther_funds"] = ">>> You can add Panther Funds to your Pitt account using this link: \nhttps://bit.ly/PowerYourPantherCard\n\nYou can also load funds and track the balance of all of your accounts by downloading the Transact eAccounts mobile app on iOS or Android."
questions_and_answers["phone_numbers"] = ">>> These are some important phone numbers:\n\n**Panther Central:** 412-648-1100\n**Pitt Police Emergency Line:** 412-624-2121\n**Pitt Police Non-Emergency Line:** 412-624-4040\n**Pitt Student Health Services:** 412-383-1800\n**Pittsburgh Action Against Rape 24/7 Helpline:** 1-866-363-7273\n**resolve Crisis Services:** 1-888-796-8226\n**SafeRider:** 412-648-2255\n**University Counseling Center:** 412-648-7930"
questions_and_answers["printing"] = ">>> You can upload print jobs at https://print.pitt.edu/. All you have to do is upload your file to the website and then choose the job settings at the bottom right.\n\nOnce your file is uploaded, simply go to a printer and swipe your Pitt ID. Remember, you must go to a color printer to print in color!\n\nA full list of University printers and their locations is available here: https://www.technology.pitt.edu/services/pitt-print#locations"
questions_and_answers["shuttle_schedule"] = ">>> The schedule for Pitt's on-campus shuttles with real-time tracking can be found here: \nhttps://pittshuttle.com/"


# generate an array of discord option choices using the hashmap's keys
# (this is needed for the topic choices to display as options in discord when invoking /faq)
topic_list = [discord.OptionChoice(topic) for topic in questions_and_answers.keys()]


@bot.slash_command(description="Find answers to frequently asked questions.")
async def faq(
    ctx, 
    topic: discord.Option(name = "topic", description = "Topic to provide details about", choices = topic_list)
):
    await ctx.response.send_message(questions_and_answers[topic])

# TODO: server-specific mailing addresses
# @bot.slash_command(description="Display the generic mailing address format for the residence hall.")
# async def mailing_addresss(ctx):

# ------------------------------- CONTEXT MENU COMMANDS -------------------------------


@bot.user_command(name="Reset")
@discord.ext.commands.has_permissions(administrator=True)
async def ctx_reset_user(ctx, member: discord.Member):
    try:
        user_count = session.query(DbUser).filter_by(ID=member.id).delete()
    except:
        user_count = 0
        await ctx.respond(
            f"User ID did not return a database row or could not be deleted: {member.id}",
            ephemeral=True,
        )
        return
    try:
        session.commit()
    except:
        session.rollback()

    if user_count > 0:
        await ctx.respond(
            f"Dropped row for user with ID in table Users: {member.id}", ephemeral=True
        )
    else:
        await ctx.respond(
            f"No database row exists in table Users for user {member.name}[{member.id}], nothing to drop.",
            ephemeral=True,
        )


@bot.user_command(name="Reset and Drop Invite")
@discord.ext.commands.has_permissions(administrator=True)
async def ctx_reset_user_drop(ctx, member: discord.Member):
    try:
        user_count = session.query(DbUser).filter_by(ID=member.id).delete()
    except:
        user_count = 0
        await ctx.respond(
            f"User ID did not return a database row or could not be deleted: {member.id}",
            ephemeral=True,
        )
        return

    try:
        verifying_user_count = (
            session.query(DbVerifyingUser).filter_by(ID=member.id).delete()
        )
    except:
        verifying_user_count = 0
        await ctx.respond(
            f"User ID did not return a database row for VerifyingUsers or could not be deleted: {member.id}",
            ephemeral=True,
        )
        return
    try:
        session.commit()
    except:
        session.rollback()

    if user_count > 0:
        if verifying_user_count > 0:
            await ctx.respond(
                f"Dropped row for user with ID in both table Users and table VerifyingUsers: {member.id}",
                ephemeral=True,
            )
        else:
            await ctx.respond(
                f"Dropped row for user with ID in table Users: {member.id}",
                ephemeral=True,
            )
    elif verifying_user_count > 0:
        await ctx.respond(
            f"Dropped row for user with ID in table VerifyingUsers: {member.id}",
            ephemeral=True,
        )
    else:
        await ctx.respond(
            f"No database row exists for user {member.name}[{member.id}], nothing to drop.",
            ephemeral=True,
        )


# ------------------------------- EVENT HANDLERS -------------------------------


# Syncs events to residence hall servers when created on hub server
# Does NOT support voice channel events
@bot.event
async def on_scheduled_event_create(scheduled_event):
    # Ignores events created on residence hall servers
    if (scheduled_event.guild).id != HUB_SERVER_ID:
        return
    # Creates buttons to be sent in a message upon event creation
    # Buttons will allow user to optionally add cover image to event or cancel before syncing
    image_check_yes = Button(label="Yes", style=discord.ButtonStyle.green)
    image_check_no = Button(label="No", style=discord.ButtonStyle.red)
    image_check_cancel = Button(label="Cancel Event", style=discord.ButtonStyle.blurple)
    cover_view = View(image_check_yes, image_check_no, image_check_cancel)
    # Sends message with buttons in #bot-commands
    bot_commands = bot.get_channel(BOT_COMMANDS_ID)
    await bot_commands.send(
        f"Event **{scheduled_event.name}** successfully created. Would you like to upload a cover image before publishing the event to residence hall servers?",
        view=cover_view,
    )

    # Executes if 'Yes' button is clicked
    async def yes_callback(interaction: discord.Interaction):
        # Sends modal to get image URL from user
        url_modal = URLModal(title="Cover Image URL Entry")
        await interaction.response.send_modal(url_modal)
        await url_modal.wait()
        cover_url = url_modal.url
        # Executes if URL is direct image link
        if (cover_url.lower()).startswith("http"):
            # Deletes message with buttons to avoid double-clicking
            await interaction.delete_original_message()
            # Opens URL and converts contents to bytes object
            cover_bytes = urlopen(cover_url).read()
            # Adds cover image to hub event
            await scheduled_event.edit(cover=cover_bytes)
            # Iterates through residence hall servers, skipping hub server
            for guild in bot.guilds:
                if guild.id == HUB_SERVER_ID:
                    continue
                # Creates cloned event without cover image
                event_clone = await guild.create_scheduled_event(
                    name=scheduled_event.name,
                    description=scheduled_event.description,
                    location=scheduled_event.location,
                    start_time=scheduled_event.start_time,
                    end_time=scheduled_event.end_time,
                )
                # Adds cover image to cloned event
                await event_clone.edit(cover=cover_bytes)
            # Sends confirmation message in #bot-commands
            await bot_commands.send(
                f"Event **{scheduled_event.name}** successfully created **with** cover image."
            )
        # Sends warning message if URL is not direct image link
        # User can simply click a button in the original message again
        else:
            await bot_commands.send(
                """**Error: Invalid URL.**
Only direct image links are supported. Try again."""
            )

    # Executes if 'No' button is clicked
    async def no_callback(interaction: discord.Interaction):
        await interaction.response.defer()
        # Deletes message with buttons to avoid double-clicking
        await interaction.delete_original_message()
        # Iterates through residence hall servers, skipping hub server
        for guild in bot.guilds:
            if guild.id == HUB_SERVER_ID:
                continue
            # Creates cloned event
            await guild.create_scheduled_event(
                name=scheduled_event.name,
                description=scheduled_event.description,
                location=scheduled_event.location,
                start_time=scheduled_event.start_time,
                end_time=scheduled_event.end_time,
            )
        # Sends confirmation message in #bot-commands
        await bot_commands.send(
            f"Event **{scheduled_event.name}** successfully created **without** cover image."
        )

    # Executes if 'Cancel Event' button is clicked
    async def cancel_callback(interaction: discord.Interaction):
        await interaction.response.defer()
        # Deletes message with buttons to avoid double-clicking
        await interaction.delete_original_message()
        # Cancels event in hub server
        await scheduled_event.cancel()
        # Sends confirmation message in #bot-message
        await bot_commands.send(
            f"Event **{scheduled_event.name}** successfully canceled."
        )

    # Assigns an async method to each button
    image_check_yes.callback = yes_callback
    image_check_no.callback = no_callback
    image_check_cancel.callback = cancel_callback


# Syncs updates to both scheduled and active events
# Syncs manual event starts
# Does NOT support editing event title or cover image
@bot.event
async def on_scheduled_event_update(old_scheduled_event, new_scheduled_event):
    # Ignores updates initiated on residence hall servers
    if (new_scheduled_event.guild).id != HUB_SERVER_ID:
        return
    # Stores whether the event was manually started
    event_start = False
    # Iterates through the residence hall servers, skipping the hub server
    for guild in bot.guilds:
        if guild.id == HUB_SERVER_ID:
            continue
        # Iterates through the events in the server
        for scheduled_event in guild.scheduled_events:
            # Executes each time an event with the same name is found
            if scheduled_event.name == new_scheduled_event.name:
                # Syncs edits to scheduled events
                if str(new_scheduled_event.status) == "ScheduledEventStatus.scheduled":
                    if str(scheduled_event.status) == "ScheduledEventStatus.scheduled":
                        # Edits the event to match the one on the hub server
                        await scheduled_event.edit(
                            description=new_scheduled_event.description,
                            location=new_scheduled_event.location,
                            start_time=new_scheduled_event.start_time,
                            end_time=new_scheduled_event.end_time,
                        )
                # Syncs manual starts and edits to active events
                elif str(new_scheduled_event.status) == "ScheduledEventStatus.active":
                    if str(scheduled_event.status) == "ScheduledEventStatus.scheduled":
                        # Starts the event
                        await scheduled_event.start()
                        event_start = True
                    elif str(scheduled_event.status) == "ScheduledEventStatus.active":
                        # Edits the event to match the one on the hub server
                        await scheduled_event.edit(
                            description=new_scheduled_event.description,
                            location=new_scheduled_event.location,
                            end_time=new_scheduled_event.end_time,
                        )
    # Sends an appropriate confirmation in #bot-commands depending on what was updated
    bot_commands = bot.get_channel(BOT_COMMANDS_ID)
    if event_start == True:
        await bot_commands.send(
            f"Event **{new_scheduled_event.name}** successfully started."
        )
    elif (str(new_scheduled_event.status) == "ScheduledEventStatus.scheduled") or (
        str(new_scheduled_event.status) == "ScheduledEventStatus.active"
    ):
        await bot_commands.send(
            f"Event **{new_scheduled_event.name}** successfully updated."
        )
    # Syncs manual completion of active events in addition to sending a confirmation message
    elif str(new_scheduled_event.status) == "ScheduledEventStatus.completed":
        for guild in bot.guilds:
            if guild.id == HUB_SERVER_ID:
                continue
            for scheduled_event in guild.scheduled_events:
                if scheduled_event.name == new_scheduled_event.name:
                    if str(scheduled_event.status) == "ScheduledEventStatus.active":
                        await scheduled_event.complete()
        await bot_commands.send(
            f"Event **{new_scheduled_event.name}** successfully completed."
        )


# Syncs cancellation of scheduled events
# Completion of active events is handled above by on_scheduled_event_update
@bot.event
async def on_scheduled_event_delete(deleted_event):
    # Ignores cancellations not initiated on residence hall servers
    if (deleted_event.guild).id != HUB_SERVER_ID:
        return
    # Iterates through residence hall servers, skipping hub server
    for guild in bot.guilds:
        if guild.id == HUB_SERVER_ID:
            continue
        # Iterates through events in the server
        for scheduled_event in guild.scheduled_events:
            # Executes each time an event with the same name is found
            if scheduled_event.name == deleted_event.name:
                if str(scheduled_event.status) == "ScheduledEventStatus.scheduled":
                    await scheduled_event.cancel()
    # Sends confirmation message in #bot-commands
    bot_commands = bot.get_channel(BOT_COMMANDS_ID)
    await bot_commands.send(f"Event **{deleted_event.name}** successfully canceled.")


@bot.event
async def on_member_join(member: discord.Member):
    # Need to figure out what invite the user joined with
    # in order to assign the correct roles.

    Log.info(f"Member join event fired with {member.display_name}")

    # I'm thinking we should initiate verification here instead of
    # adding the roles, then the verify command does all of this code.

    # User is verifying for the guild they just joined
    user_to_guild[member.id] = member.guild

    # Get logs channel for errors
    logs_channel = discord.utils.get(member.guild.channels, name="logs")

    if not logs_channel:
        Log.warning(
            f"No channel 'logs' found in {member.guild.name}[{member.guild.id}]"
        )

    # Get invite snapshot ASAP after guild is determined
    # Invites after user joined
    invites_now = await member.guild.invites()

    # Invites before user joined
    old_invites = invites_cache[member.guild.id]

    # Will need to DM member at some point
    dm_channel = await member.create_dm()

    # This is a kind of janky method taken from this medium article:
    # https://medium.com/@tonite/finding-the-invite-code-a-user-used-to-join-your-discord-server-using-discord-py-5e3734b8f21f

    # Check for the potential invites
    potential_invites = []

    for possible_invite in old_invites:
        Log.info(f"Checking {possible_invite.code}")
        new_invite = util.invites.get_invite_from_code(
            invites_now, possible_invite.code
        )
        if not new_invite:
            # The invite is invalid or somehow inaccessible
            Log.warning(
                f"Invite code {possible_invite.code} was invalid or inaccessible, it will be skipped."
            )
            continue
        # O(n²)
        if possible_invite.uses < new_invite.uses:

            # This is POTENTIALLY the right code
            invite = possible_invite  # If all else fails, grab the first one, which is usually right

            # Who joined and with what link
            Log.info(f"Potentially invite Code: {possible_invite.code}")

            potential_invites.append(possible_invite)

    num_overlap = len(potential_invites)

    Log.info(f"{potential_invites=}")

    if num_overlap == 1:
        invite = potential_invites[0]
        user_to_invite[member.id] = invite
        # Add row to database
        verifying_data = DbVerifyingUser(ID=member.id, invite_code=invite.code)

        session.merge(verifying_data)
        try:
            session.commit()
        except:
            session.rollback()
            Log.error(
                f"Couldn't add {member.name}[{member.id}] to VerifyingUsers database."
            )
    elif num_overlap > 1:
        # Code for potential overlap
        options = []
        options_to_inv = {}

        # Build options for dropdown
        for inv in potential_invites:
            if inv.code in invite_to_role:
                role = invite_to_role[inv.code]
                Log.ok(
                    f"Invite link {inv.code} is cached with '{role.name}', adding to modal options for manual select."
                )
                options.append(role.name)
                options_to_inv[role.name] = inv
            else:
                try:
                    inv_object = session.query(DbInvite).filter_by(code=inv.code).one()
                except Exception:
                    inv_object = None

                if inv_object:
                    Log.ok(f"Invite link {inv.code} was found in the database.")
                    role = discord.utils.get(member.guild.roles, id=inv_object.role_id)
                    if role:
                        Log.ok(
                            f"Databased invite '{inv.code}' returned a valid role '{role.name}', adding this role to manual select."
                        )
                        options.append(role.name)
                        options_to_inv[role.name] = inv
                    else:
                        Log.error(
                            f"Databased invite '{inv.code}' did not return a role to assign to {member.name}[{member.id}]. This is an error."
                        )
                        if logs_channel:
                            await logs_channel.send(
                                content=f"Databased invite '{inv.code}' did not return a role to assign to {member.name}[{member.id}]. This is an error."
                            )
                else:
                    Log.error(
                        f"Invite link {inv.code} was neither cached nor found in the database. This code will be ignored. This is an error."
                    )
                    if logs_channel:
                        await logs_channel.send(
                            content=f"Invite link {inv.code} was neither cached nor found in the database. This code will be ignored. This is an error."
                        )

        # Send view with options which will forcibly initiate verification
        Log.info(f"{options=}")
        view = CommunitySelectView(
            choices=options, opts_to_inv=options_to_inv, timeout=180
        )

        await dm_channel.send(
            content="For security, we must verify which community you belong to. Please select your community below!",
            view=view,
            delete_after=60.0,
        )
        await logs_channel.send(
            content=f"User {member.name}[{member.id}] invite code was ambiguous, sending them manual selection menu...",
        )

        return

    else:
        # Error
        Log.error(
            f"No valid invite link was found when user {member.name}[{member.id}] joined."
        )
        Log.error(f"{num_overlap=}")
        Log.error(f"{potential_invites=}")
        # Update cache
        invites_cache[member.guild.id] = invites_now
        if logs_channel:
            await logs_channel.send(
                content=f"**WARNING**: No valid invite link was found when user {member.name}[{member.id}] joined. This is likely to require manual override."
            )
        return

    # Update cache
    invites_cache[member.guild.id] = invites_now

    # Log that the user has joined with said invite.
    logs_channel = discord.utils.get(member.guild.channels, name="logs")
    if not logs_channel:
        Log.warning(f"No channel 'logs' in {member.guild.name}[{member.guild.id}]")
    if member.id in user_to_invite:
        if logs_channel:
            await logs_channel.send(
                f"**OK**: User {member.name}[{member.id}] is associated with invite code {user_to_invite[member.id].code}"
            )

        Log.ok(
            f"User {member.name}[{member.id}] is associated with invite {user_to_invite[member.id].code}"
        )
    else:
        if logs_channel:
            await logs_channel.send(
                f"**ERROR**: User {member.name}[{member.id}] was neither associated with an invite code on join nor sent a manual selection menu."
            )
        Log.error(
            f"User {member.name}[{member.id}] was neither associated with an invite code on join nor sent a manual selection menu."
        )


@bot.event
async def on_guild_join(guild):
    # Automate call of setup

    # Track the landing channel (verify) of the server
    guild_to_landing[guild.id] = discord.utils.get(guild.channels, name="verify")

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
        session.rollback()
        Log.warning(
            "Attempting to merge an already existent guild into the database failed:"
        )
        print(int_exception.with_traceback())

    # Create a view that will contain a button which can be used to initialize the verification process
    view = VerifyView(timeout=None)

    # Finished
    # Delete old verification message
    async for msg in guild_to_landing[guild.id].history():
        if msg.author == bot.user and msg.content == VERIFICATION_MESSAGE:
            await msg.delete()
            break
    await guild_to_landing[guild.id].send(content=VERIFICATION_MESSAGE, view=view)


@bot.event
async def on_guild_channel_update(
    before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
):
    # We only want to handle category channel name updates
    if isinstance(before, discord.CategoryChannel) and isinstance(
        after, discord.CategoryChannel
    ):

        # Check that this category was actually associated with a role.
        if before.id in category_to_role:
            Log.info(
                f"Category {before.id} is associated with {category_to_role[before.id]} and has been updated. Role might be updated."
            )

            if before.name == after.name:
                Log.info(
                    f"Category {before.id}'s name was not changed. Role wasn't updated."
                )
                return
            else:
                Log.info(
                    f"Category {before.id}'s name was changed. Role will be updated."
                )

                # First get role
                role = discord.utils.get(
                    after.guild.roles, id=category_to_role[after.id]
                )
                # Update role name
                await role.edit(name=after.name)

                # Forcibly update role names in invite_to_role dict
                # As it turns out, this code seems to be unnecessary in most cases
                # However, the modal dropdown menus are based on role NAME, so it may
                # be necessary to keep this code. It also means that students
                # get the most up to date role name in their modal dropdowns.
                # This should hopefully reduce confusion if an RA says "Hey our channels are
                # called 'The Squad'" and then a student doesn't see 'The Squad' as an option.

                for invite_code, role_obj in invite_to_role.items():
                    if role_obj.id == role.id:
                        Log.info(f"Invalidated role object: {role_obj=}")
                        invite_to_role[invite_code] = role
                        Log.info(f"New role object: {invite_to_role[invite_code]=}")
                        Log.ok(
                            f"Invite to role cache has been updated, code {invite_code} changed."
                        )
                        # **IMPORTANT**: The bot will only update ONE INVITE CODE. There is NO REASON an invite should be
                        # associated with more than one role. If this ever happens, this break will need to change.
                        # For now, though, it makes sense not to loop over every single invite every time a category is updated.
                        break
                else:
                    # Nothing was found to update in the invites cache
                    Log.warning(
                        f"No invite was associated with {category_to_role[before.id]}, the invites cache has not been updated."
                    )

        # Category is not associated with a cached role. This is potentially erroneous.
        else:
            Log.warning(
                f"Category {before.id} was updated but is not associated with a role in cache. This could be an error."
            )

@bot.event
async def on_guild_emojis_update(guild: discord.Guild, before: Sequence[discord.Emoji], after: Sequence[discord.Emoji]):
    bot_commands = bot.get_channel(BOT_COMMANDS_ID)

    # Determine if change was made in control server
    changed_in_hub = guild.id == HUB_SERVER_ID

    # Determine operation and execute

    # Add
    if len(before) < len(after):
        emoji = discord.utils.find(lambda e: e not in before, after)
        if not emoji:
            Log.error('find() returned None on detected added emoji')
            return

        # Check that the change was not due to synchronization
        if emoji.user.id == bot.user.id:
            return
        
        # Automatically sync throughout all guilds if made in control
        if changed_in_hub:
            await sync_add(bot=bot, emoji=emoji)
            
        # Send View and wait for acceptance or denial
        else:
            # Send the view in the commands server
            await bot_commands.send(
                f'An emoji, {emoji.name} with the appearence {emoji} has been added to Guild {guild.name} Would you like to sync this change?', 
                view=EmojiSyncView(emoji=emoji, mod_type='Add')
            )

    # Delete
    elif len(before) > len(after):
        emoji = discord.utils.find(lambda e: e not in after, before)
        if not emoji:
            Log.error('find() returned None on detected deleted emoji')
            return

        # Check that the change was not due to synchronization
        if hash(emoji) in synced_emoji_cache:
            try:
                synced_emoji_cache.remove(hash(emoji))
            except:
                Log.error(f'Detected {emoji.name} hash in synced cache but remove() failed')
            return
        
        # Auto-sync
        if changed_in_hub:
            await sync_delete(cache=synced_emoji_cache, bot=bot, emoji=emoji)

        # Send View and wait for acceptance or denial
        else:
            # Check that the emoji is a synced emoji among guild
            synced = False
            hub = bot.get_guild(HUB_SERVER_ID)
            hub_emojis = hub.fetch_emojis
            for hub_emoji in hub_emojis:
                if hub_emoji.name == emoji.name:
                    synced = True
                    break
            
            if synced:
                await bot_commands.send(
                            f'An emoji, {emoji.name} with the appearence {emoji} has been deleted from Guild {guild.name}, Would you like to sync this change?',
                            view=EmojiSyncView(emoji=emoji, mod_type='Del')
                        )

    # Rename
    else:
        # Find out what emoji changed
        old_emoji = None
        new_emoji = None
        for pre_emoji in before:
            for post_emoji in after:
                if pre_emoji == post_emoji and pre_emoji.name != post_emoji.name:
                    old_emoji = pre_emoji
                    new_emoji = post_emoji
                    break

        # Confirm that we found a name change, if not log an error
        if not old_emoji or not new_emoji:
            Log.error('Registered emoji name change but no change found')
            return

        # Check that the change was not due to synchronization
        if hash(old_emoji) in synced_emoji_cache:
            try:
                synced_emoji_cache.remove(hash(old_emoji))
            except:
                Log.error(f'Detected {old_emoji.name} hash in synced cache but remove() failed')
            return

        # Check if auto-sync is needed
        if changed_in_hub:
            await sync_name(cache=synced_emoji_cache, bot=bot, old_emoji=old_emoji, new_emoji=new_emoji)

        # Send view asking if the change should be synced
        else:
            await bot_commands.send(
                f'An emojis name was changed from {old_emoji.name} to {new_emoji.name} in Guild {guild.name}. Would you like to sync this change?',
                view=EmojiSyncView(emoji=new_emoji, old_emoji=old_emoji, mod_type='Name')
            )

@bot.event
async def on_application_command_error(
    ctx: discord.ApplicationContext, error: discord.DiscordException
):
    if isinstance(error, discord.ext.commands.errors.MissingPermissions):
        Log.warning(
            f"User {ctx.user.name}[{ctx.user.id}] tried to use a command ('{ctx.command.qualified_name}') they're not allowed to."
        )
        await ctx.respond(
            "Sorry, you don't have permission to run that command.", ephemeral=True
        )
    else:
        Log.error("Unknown error thrown, propagating:")
        raise error


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
            # Delete old verification message
            async for msg in guild_to_landing[guild.id].history():
                if msg.author == bot.user and msg.content == VERIFICATION_MESSAGE:
                    await msg.delete()
                    break
            await guild_to_landing[guild.id].send(
                content=VERIFICATION_MESSAGE, view=view
            )
        except AttributeError:
            continue

    # Load categories cache from database
    for category_obj in session.query(DbCategory).all():
        category_to_role[category_obj.ID] = category_obj.role_id

    Log.info(f"{category_to_role=}")
    Log.ok("Bot is ready.")


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
