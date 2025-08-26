import discord
import logging
import requests
from .base import BaseCommandGroup
from utils.config import config

# Grouping of slash commands into a command list
class OperationCommandGroup(BaseCommandGroup):
    def __init__(self, params={}):
        super().__init__(params)

        self.command_list = [
            operation_load,
            operation_reload_from_config,
            operation_unload
        ]
    
@discord.app_commands.command(name="operation_load", description="Load a specific operation")
async def operation_load(interaction, op_type: str, op_id: str) -> None:
    try:
        response = requests.post(
            config.jaison_api_endpoint+"/api/operations/load",
            headers={"Content-type":"application/json"},
            json={"ops": [{'role': op_type, "id": op_id}]}
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        parsed_response = response.json()
        reply = "Operation load job sent successfully: {}".format(parsed_response['response']['job_id'])
        logging.info(reply)
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"Failed to send operation load job: {str(err)}")
        await interaction.response.send_message(f"Failed to send operation load job: {str(err)}")
        
@discord.app_commands.command(name="operation_reload_from_config", description="Reload all operations")
async def operation_reload_from_config(interaction) -> None:
    try:
        response = requests.post(
            config.jaison_api_endpoint+"/api/operations/reload",
            headers={"Content-type":"application/json"}
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        parsed_response = response.json()
        reply = "Operation reload job sent successfully: {}".format(parsed_response['response']['job_id'])
        logging.info(reply)
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"Failed to send operation reload job: {str(err)}")
        await interaction.response.send_message(f"Failed to send operation reload job: {str(err)}")

@discord.app_commands.command(name="operation_unload", description="Unload a specific operation")
async def operation_unload(interaction, op_type: str, op_id: str = None) -> None:
    try:
        response = requests.post(
            config.jaison_api_endpoint+"/api/operations/unload",
            headers={"Content-type":"application/json"},
            json={"ops": [{'role': op_type, "id": op_id}]}
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        parsed_response = response.json()
        reply = "Operation unload job sent successfully: {}".format(parsed_response['response']['job_id'])
        logging.info(reply)
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"Failed to send operation unload job: {str(err)}")
        await interaction.response.send_message(f"Failed to send operation unload job: {str(err)}")