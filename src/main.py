from src.utils.args import args
from dotenv import load_dotenv
load_dotenv(dotenv_path=args.env)

import os
import asyncio
from src.utils.bot import DiscordBot


async def main():
    discord_bot = DiscordBot()
    await discord_bot.login(os.getenv("DISCORD_BOT_TOKEN"))
    await discord_bot.connect()

asyncio.run(main())