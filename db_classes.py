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

    def __repr__(self):
        return f"User: {{\n\tid: {self.ID}\n\tusername: {self.username}\n\temail: {self.email}\n\tverified: {self.verified}}}"