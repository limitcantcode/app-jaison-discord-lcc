import discord
import logging
import requests
from datetime import datetime
from .base import BaseCommandGroup
from utils.config import config

# Grouping of slash commands into a command list
class ContextCommandGroup(BaseCommandGroup):
    def __init__(self, params={}):
        super().__init__(params)

        self.command_list = [
            context_request_add,
            context_conversation_add,
            context_custom_add,
            context_custom_remove,
            context_custom_register
        ]

@discord.app_commands.command(name="context_request_add", description="Make a request")
async def context_request_add(interaction, content: str) -> None:
    try:
        response = requests.post(
            config.jaison_api_endpoint+"/api/context/request",
            headers={"Content-type":"application/json"},
            json={
                "content": content
            }
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        parsed_response = response.json()
        reply = "Add request context job sent successfully: {}".format(parsed_response['response']['job_id'])
        logging.info(reply)
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"Failed to send add request context job: {str(err)}")
        await interaction.response.send_message(f"Failed to send add request context job: {str(err)}")
        
@discord.app_commands.command(name="context_conversation_add", description="Send text dialogue")
async def context_conversation_add(interaction, user: str, content: str) -> None:
    try:
        response = requests.post(
            config.jaison_api_endpoint+"/api/context/conversation/text",
            headers={"Content-type":"application/json"},
            json={
                "user": user,
                "timestamp": datetime.now().timestamp(),
                "content": content
            }
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        parsed_response = response.json()
        reply = "Add conversation context job sent successfully: {}".format(parsed_response['response']['job_id'])
        logging.info(reply)
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"Failed to send add conversation context job: {str(err)}")
        await interaction.response.send_message(f"Failed to send add conversation context job: {str(err)}")

@discord.app_commands.command(name="context_custom_register", description="Register a new custom context")
async def context_custom_register(interaction, context_id: str, name: str, description: str) -> None:
    try:
        response = requests.put(
            config.jaison_api_endpoint+"/api/context/custom",
            headers={"Content-type":"application/json"},
            json={
                "context_id": context_id,
                "context_name": name,
                "context_description": description
            }
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        parsed_response = response.json()
        reply = "Register custom context job sent successfully: {}".format(parsed_response['response']['job_id'])
        logging.info(reply)
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"Failed to send register custom context job: {str(err)}")
        await interaction.response.send_message(f"Failed to send register custom context job: {str(err)}")

@discord.app_commands.command(name="context_custom_remove", description="Remove a custom context")
async def context_custom_remove(interaction, context_id: str) -> None:
    try:
        response = requests.delete(
            config.jaison_api_endpoint+"/api/context/custom",
            headers={"Content-type":"application/json"},
            json={
                "context_id": context_id
            }
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        parsed_response = response.json()
        reply = "Remove custom context job sent successfully: {}".format(parsed_response['response']['job_id'])
        logging.info(reply)
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"Failed to send remove custom context job: {str(err)}")
        await interaction.response.send_message(f"Failed to send remove custom context job: {str(err)}")
        
@discord.app_commands.command(name="context_custom_add", description="Add information to a custom context")
async def context_custom_add(interaction, context_id: str, content: str) -> None:
    try:
        response = requests.post(
            config.jaison_api_endpoint+"/api/context/custom",
            headers={"Content-type":"application/json"},
            json={
                "context_id": context_id,
                "context_contents": content,
                "timestamp": datetime.now().timestamp()
            }
        )
        if response.status_code != 200: raise Exception("{} {}".format(response.status_code, response.reason))
        
        parsed_response = response.json()
        reply = "Add custom context job sent successfully: {}".format(parsed_response['response']['job_id'])
        logging.info(reply)
        await interaction.response.send_message(reply)
    except Exception as err:
        logging.error(f"Failed to send add custom context job: {str(err)}")
        await interaction.response.send_message(f"Failed to send add custom context job: {str(err)}")