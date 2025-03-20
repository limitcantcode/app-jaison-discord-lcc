from utils.args import args
from utils.logging import setup_logging
setup_logging()
from dotenv import load_dotenv
load_dotenv(dotenv_path=args.env)

import os
import asyncio
from utils.bot import DiscordBot


async def main():
    discord_bot = DiscordBot()
    await discord_bot.login(os.getenv("DISCORD_BOT_TOKEN"))
    await discord_bot.connect()

asyncio.run(main())