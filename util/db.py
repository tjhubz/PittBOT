"""Database models for persistent storage.
"""

# pylint: disable=too-few-public-methods

from sqlalchemy import Column, BigInteger, String, Integer, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class DbUser(Base):
    """Represents a user in the bot's MySQL database.
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
    ID = Column("id", BigInteger, primary_key=True)
    # User's discord username
    username = Column("username", String(50))
    # User's PITT email address
    email = Column("email", String(30))
    # Whether the user has been verified or not
    verified = Column("verified", Boolean)
    # Is this user an RA?
    is_ra = Column("isRA", Boolean)
    # Which community is this user a part of
    community = Column("community", String(50))
    # When did this user join the server?
    joined_at = Column("joined_at", DateTime, default=func.now())
    # When was this user last updated?
    updated_at = Column("updated_at", DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"User: {{\n\tid: {self.ID}\n\tusername: {self.username}\n\temail: {self.email}\n\tverified: {self.verified}}}"


class DbGuild(Base):
    """Represents a guild in the bot's MySQL database.
    ## Attributes

    `ID: BigInteger`                 = the guild's discord ID
    `is_setup: Boolean`              = whether this guild has undergone setup
    `RA_role_id: BigInteger`         = the ID for this server's RA role
    `landing_channel_id: BigInteger` = the ID for this server's verification channel
    """

    __tablename__ = "guilds"

    # Guild ID
    ID = Column("id", BigInteger, primary_key=True)
    # Whether the Guild has undergone initial setup or not
    is_setup = Column("setup", Boolean)
    # RA Role ID
    ra_role_id = Column("raRoleID", BigInteger)
    # Landing channel ID
    landing_channel_id = Column(
        "landingChannelID", BigInteger
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
    """Represents an invite in the bot's MySQL database.
    ## Attributes

    `code: BigInteger`      = this invite's code (URL postfix)
    `guild_id: BigInteger`  = guild ID for the guild this invite belongs to
    `role_id: BigInteger`   = role ID for the community role this invite is associated with
    `uses: Integer`         = number of times this invite has been used
    """

    __tablename__ = "invites"

    # Invite code
    code = Column("code", String(10), primary_key=True)
    # Which guild it belongs to
    guild_id = Column("guildID", BigInteger)
    # The role ID that this invite is associated with
    role_id = Column("roleID", BigInteger)

    def __repr__(self):
        return f"""Invite: {{
    code: {self.code}
    guild_id: {self.guild_id}
    role_id: {self.role_id}
}}
"""


class DbCategory(Base):
    """Represents a category in the bot's MySQL database.
    ## Attributes

    `ID: BigInteger`        = the category ID for this category
    `role_id: BigInteger`   = role ID for the community role this category is associated with
    """

    __tablename__ = "categories"

    # Category ID
    ID = Column("id", BigInteger, primary_key=True)
    # Community role ID category is associated with
    role_id = Column("roleID", BigInteger)

    def __repr__(self):
        return f"""Category: {{
    id: {self.ID}
    role_id: {self.role_id}
}}
"""

class DbVerifyingUser(Base):
    """Represents a user that is in the verification process,
    or data used for verification, in the bot's MySQL database.
    ## Attributes


    """
    __tablename__ = "verifyingusers"

    # User ID
    ID = Column("id", BigInteger, primary_key=True)
    # Invite code user used to join
    invite_code = Column("invite", String(10))

    def __repr__(self):
        return f"""VerifyingUser: {{
    user_id: {self.ID}
    invite_code: {self.invite_code}
}}
"""

class DbEvent(Base):
    __tablename__ = "events"

    event_number = Column("event_number", Integer, primary_key=True)
    created_at = Column("created_at", DateTime, default=func.now())
    event_name = Column("event_name", String(100))
    event_type = Column("event_type", String(10))  # 'campus' or 'building'
    location = Column("location", String(100))
    creator_name = Column("creator_name", String(50))
    creator_id = Column("creator_id", BigInteger)
    date = Column("date", Date)
    start_time = Column("start_time", DateTime)
    end_time = Column("end_time", DateTime)
    image_added = Column("image_added", Boolean)
    subscribers = Column("subscribers", Integer, default=0)
    status = Column("status", String(10))
    attendance = Column("attendance", Integer)

    def __repr__(self):
        return f"Event: {{\n\tevent_number: {self.event_number}\n\tevent_name: {self.event_name}\n\t...}}"

class DbSubscriber(Base):
    __tablename__ = "subscribers"

    id = Column("id", Integer, primary_key=True)  # Artificial primary key
    subscription_time = Column("subscription_time", DateTime, default=func.now())
    user_id = Column("user_id", BigInteger)
    user_name = Column("user_name", String(50))
    user_email = Column("user_email", String(50))
    event_number = Column("event_number", Integer, ForeignKey('events.event_number'))

    event = relationship("DbEvent")

    def __repr__(self):
        return f"Subscriber: {{\n\tsubscription_time: {self.subscription_time}\n\tuser_id: {self.user_id}\n\tevent_number: {self.event_number}\n}}"