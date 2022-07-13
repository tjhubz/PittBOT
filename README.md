# PittBOT

**This is the bot that will be used for all official Pitt Discord guilds.**\
https://www.maskup.pitt.edu/residence-life/


## What it does

The bot will handle:
- Student verification (https://github.com/gg2001/EmailBot)
  - Students must enter their pitt email, to which the bot will then verify using a code. If it could also get the student's name from their email and set it as their nickname that would be great.
- Automatic role assignment (https://github.com/eco-community/invite-role-bot)
  - Each RA will have their own invite link to give to their residents. When that invite is used it will give them the role that gives them access to their floor's chat.
- Synchronized event creation (https://discord.com/developers/docs/resources/guild-scheduled-event)
  - Since ResLife hosts multiple events throughout the year (as do RAs) it would be cool if they could be set up as a scheduled event within their respective server.
- Automatic assistance with common questions (FAQ system) - this is not something that needs to happen
  - For instance, if someone asks "What are meal exchanges?" it would inform them what they are and how to use them.
- Slur prevention
  - Self explanitory

## Contributing 
If you are interested in contributing, see [DEV.md](DEV.md) to get started, and [join the Discord][discord-link]!

### Current Goals
Right now, we want to get the core functionality mentioned above working. Top priority is student verification and automatice role assignment. When those are complete, we'll start working on the other features listed. As we move through those features, if you think the bot could use a new feature, feel free to join the [discord][discord-link] and let us know!

[discord-link]: https://discord.gg/JDQTkTw3Ek

