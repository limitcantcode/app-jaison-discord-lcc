import discord
import logging
from .base import BaseCommandGroup

class NotInVCException(Exception):
    pass

# Grouping of slash commands into a command list
class ManageCommandGroup(BaseCommandGroup):
    def __init__(self, params={}):
        super().__init__(params)

        self.command_list = [
            clear_history
        ]

'''
Clear cache conversation history
'''
@discord.app_commands.command(name="clear_history", description="Clear cache conversation history.")
async def clear_history(interaction) -> None:
    try:
        interaction.client.clear_history()
        logging.info(f"History cleared successfully")
        await interaction.response.send_message("History cleared successfully")
    except Exception as err:
        logging.error(f"Failed to clear history: {str(err)}")
        await interaction.response.send_message("Failed to clear history.")
