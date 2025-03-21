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
            clear_conversation
        ]

'''
Clear cache conversation history
'''
@discord.app_commands.command(name="clear_conversation", description="Clear cache conversation history.")
async def clear_conversation(interaction) -> None:
    try:
        interaction.client.clear_conversation()
        logging.info(f"Conversation history cleared successfully")
        await interaction.response.send_message("Conversation history cleared successfully")
    except Exception as err:
        logging.error(f"Failed to delete conversation: {str(err)}")
        await interaction.response.send_message("Failed to clear conversation history.")
