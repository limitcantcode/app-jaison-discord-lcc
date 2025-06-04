import discord
import logging
from .base import BaseCommandGroup

# Grouping of slash commands into a command list
class ConfigCommandGroup(BaseCommandGroup):
    def __init__(self, params={}):
        super().__init__(params)

        self.command_list = [
            config_load,
            config_save,
            vc_response_latency,
            vc_idle_interval
        ]
        
# Config
# /api/config config_load config_save
# vc response latency
# idle time interval

@discord.app_commands.command(name="config_load", description="Load a configuration")
async def config_load(interaction) -> None:
    try:
        interaction.client.clear_history()
        logging.info(f"History cleared successfully")
        await interaction.response.send_message("History cleared successfully")
    except Exception as err:
        logging.error(f"Failed to clear history: {str(err)}")
        await interaction.response.send_message("Failed to clear history.")
        
@discord.app_commands.command(name="config_save", description="Save a configuration")
async def config_save(interaction) -> None:
    try:
        interaction.client.clear_history()
        logging.info(f"History cleared successfully")
        await interaction.response.send_message("History cleared successfully")
    except Exception as err:
        logging.error(f"Failed to clear history: {str(err)}")
        await interaction.response.send_message("Failed to clear history.")

@discord.app_commands.command(name="vc_response_latency", description="Request responses after this many seconds of a pause")
async def vc_response_latency(interaction) -> None:
    try:
        interaction.client.clear_history()
        logging.info(f"History cleared successfully")
        await interaction.response.send_message("History cleared successfully")
    except Exception as err:
        logging.error(f"Failed to clear history: {str(err)}")
        await interaction.response.send_message("Failed to clear history.")

@discord.app_commands.command(name="vc_idle_interval", description="Request responses when nothing is said after this many seconds.")
async def vc_idle_interval(interaction) -> None:
    try:
        interaction.client.clear_history()
        logging.info(f"History cleared successfully")
        await interaction.response.send_message("History cleared successfully")
    except Exception as err:
        logging.error(f"Failed to clear history: {str(err)}")
        await interaction.response.send_message("Failed to clear history.")
