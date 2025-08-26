import discord
import logging
import requests
from .base import BaseCommandGroup
from utils.config import config

# Grouping of slash commands into a command list
class ResponseCommandGroup(BaseCommandGroup):
    def __init__(self, params={}):
        super().__init__(params)

        self.command_list = [
            request_response
        ]

@discord.app_commands.command(name="request_response", description="Request a response.")
async def request_response(interaction, output_audio: bool = False) -> None:
    try:
        response = requests.post(
            config.jaison_api_endpoint+"/api/response",
            headers={"Content-type":"application/json"},
            json={"include_audio": output_audio}
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        parsed_response = response.json()
        reply = "Response job sent successfully: {}".format(parsed_response['response']['job_id'])
        logging.info(reply)
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"Failed to send response job: {str(err)}")
        await interaction.response.send_message(f"Failed to send response job: {str(err)}")
