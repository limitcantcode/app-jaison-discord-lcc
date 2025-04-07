
import discord
import logging
import requests
from .base import BaseCommandGroup
from utils.config import config

# Grouping of slash commands into a command list
class InfoCommandGroup(BaseCommandGroup):
    def __init__(self, params={}):
        super().__init__(params)

        self.command_list = [
            get_loaded_operations,
            get_current_config
        ]
    
@discord.app_commands.command(name="get_loaded_operations", description="List loaded operations")
async def get_loaded_operations(interaction) -> None:
    try:
        response = requests.get(
            config.jaison_api_endpoint+"/api/operations"
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        loaded_operations_d = response.json()['response']
        logging.info("get_loaded_operations successful: {}".format(loaded_operations_d))
        reply = ""
        for op_type, op_id in loaded_operations_d.items():
            reply += f"**{op_type}:** {str(op_id)}\n"
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"get_loaded_operations failed: {str(err)}")
        await interaction.response.send_message(f"get_loaded_operations failed: {str(err)}")

@discord.app_commands.command(name="get_current_config", description="List loaded configuration")
async def get_current_config(interaction) -> None:
    try:
        response = requests.get(
            config.jaison_api_endpoint+"/api/config"
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        config_d = response.json()['response']
        logging.info("get_current_config successful: {}".format(config_d))
        reply = ""
        for op_type, op_id in config_d.items():
            reply += f"**{op_type}:** {str(op_id)}\n"
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"get_current_config failed: {str(err)}")
        await interaction.response.send_message(f"get_current_config failed: {str(err)}")