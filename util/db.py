from sqlalchemy import Column, BigInteger, String, Integer, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class DbUser(Base):
    """Represents a user in the bot's SQLite3 database.
    ## Attributes

    `ID: BigInteger` = the user's discord ID
    `username: str`  = the user's discord username
    `email: str`     = the user's Pitt email address
    `verified: bool` = whether the user has verified their email address
    `is_ra: bool`    = whether the user is an RA or not
    `community: str` = the RA's community this user is a part of
    """

    __tablename__ = "users"

    # This will be the same as the user's discord ID (which is NOT their username)
    ID = Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    # User's discord username
    username = Column("username", String)
    # User's PITT email address
    email = Column("email", String)
    # Whether the user has been verified or not
    verified = Column("verified", Boolean)
    # Is this user an RA?
    is_ra = Column("isRA", Boolean)
    # Which community is this user a part of
    community = Column("community", String)

    def __repr__(self):
        return f"User: {{\n\tid: {self.ID}\n\tusername: {self.username}\n\temail: {self.email}\n\tverified: {self.verified}}}"


class DbGuild(Base):
    """Represents a guild in the bot's SQLite3 database.
    ## Attributes

    `ID: BigInteger`                 = the guild's discord ID
    `is_setup: Boolean`              = whether this guild has undergone setup
    `RA_role_id: BigInteger`         = the ID for this server's RA role
    `landing_channel_id: BigInteger` = the ID for this server's verification channel
    """

    __tablename__ = "guilds"

    # Guild ID
    ID = Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    # Whether the Guild has undergone initial setup or not
    is_setup = Column("setup", Boolean)
    # RA Role ID
    RA_role_id = Column("raRoleID", BigInteger().with_variant(Integer, "sqlite"))
    # Landing channel ID
    landing_channel_id = Column(
        "landingChannelID", BigInteger().with_variant(Integer, "sqlite")
    )

    def __repr__(self):
        return f"""Guild: {{
    id: {self.ID}
    setup?: {self.is_setup}
    RA role: {self.RA_role_id}
    landing channel: {self.landing_channel_id}
}}
"""


class DbInvite(Base):
    """Represents an invite in the bot's SQLite3 database.
    ## Attributes

    `code: BigInteger`      = this invite's code (URL postfix)
    `guild_id: BigInteger`  = guild ID for the guild this invite belongs to
    `role_id: BigInteger`   = role ID for the community role this invite is associated with
    `uses: Integer`         = number of times this invite has been used
    """

    __tablename__ = "invites"

    # Invite code
    code = Column(
        "code", BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    # Which guild it belongs to
    guild_id = Column("guildID", BigInteger().with_variant(Integer, "sqlite"))
    # The role ID that this invite is associated with
    role_id = Column("roleID", BigInteger().with_variant(Integer, "sqlite"))
    # Uses
    uses = Column("uses", Integer)

    def __repr__(self):
        return f"""Invite: {{
    code: {self.code}
    guild_id: {self.guild_id}
    role_id: {self.role_id}
    uses: {self.uses}
}}
"""
