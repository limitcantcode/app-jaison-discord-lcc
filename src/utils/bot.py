'''
Discord Bot Main Class to interface with Discord
'''

import discord
import asyncio
import os
import json
import requests
import base64
import websockets
import logging
from typing import Dict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from commands import add_commands
from commands.sink import BufferSink, UserAudioBuffer
from utils.config import config
from utils.helper.audio import format_audio
from utils.time import get_current_time

class DiscordBot(discord.Client):

    def __init__(self):
        if config.opus_filepath is not None: discord.opus.load_opus(config.opus_filepath)

        logging.debug("Activating with all intents...")
        super().__init__(intents=discord.Intents.all())
        logging.debug("Reloading command tree...")
        self.tree, self.tree_params = add_commands(self, os.getenv("DISCORD_SERVER_ID"))
        self.config = config

        # Stubs before readying
        self.job_data: Dict[str, Dict] = None
        self.jaison_event_task: asyncio.Task =None
        self.DEFAULT_TEXT_CHANNEL: discord.TextChannel = None
        
        self.scheduler: AsyncIOScheduler = None
        
        self.vc: discord.VoiceClient = None
        self.audio_queue: asyncio.Queue = None
        self.audio_player_task: asyncio.Task = None
        self.audio_finish_event: asyncio.Event = None
        self.keep_alive_task: asyncio.Task = None

    # Handler for bot activation
    async def on_ready(self):
        await self.tree.sync(**self.tree_params)
        logging.debug(f"Command tree resynced with params: {self.tree_params}")
        
        logging.debug(f"Starting tasks...")
        self.job_data = dict()
        self.jaison_event_task = asyncio.create_task(self._event_listener())
        self.DEFAULT_TEXT_CHANNEL = discord.Object(os.getenv("DISCORD_DEFAULT_TEXT_CHANNEL"))
        
        self.scheduler: AsyncIOScheduler = AsyncIOScheduler()
        self.scheduler.start()
        
        self.vc = None
        self.audio_queue = asyncio.Queue()
        self.audio_player_task = asyncio.create_task(self._play_audio_loop())
        self.audio_finish_event = asyncio.Event()
        self.keep_alive_task = asyncio.create_task(self._keep_alive_vc_listening())
        
        logging.info("Discord Bot is ready!")

    '''Respond to every text message from others'''
    async def on_message(self, message):
        # Skip messages from self
        if self.application_id == message.author.id:
            return

        # Generate response
        user = message.author.display_name or message.author.global_name
        content = message.content
        logging.debug(f"Message by user {user}: {content}")
        
        await message.channel.typing()
        response = requests.post(
            self.config.jaison_api_endpoint+'/api/context/conversation/text',
            headers={"Content-type":"application/json"},
            json={
                "user": user,
                "timestamp": get_current_time(),
                "content": content
            }
        ).json()
        if response['status'] != 200:
            logging.error(f"Failed to start a text message: {response['status']} {response['message']}")
            return
        
        response = requests.post(
            self.config.jaison_api_endpoint+'/api/response',
            headers={"Content-type":"application/json"},
            json={
                "output_audio": False
            }
        ).json()
        if response['status'] != 200:
            logging.error(f"Failed to start a texting response job: {response['status']} {response['message']}")
            return

        self._add_text_job(
            response['response']['job_id'],
            output_text=True,
            text_channel=message.channel
        )

    # Track texting specific jobs
    def _add_text_job(
        self,
        job_id: str,
        output_text: bool = False,
        text_channel: discord.TextChannel = None
    ):
        self.job_data[job_id] = { # Specific tracking for text messages. Audio will be naive
            "output_text": output_text,
            "text_content": "",
            "text_channel": text_channel
        }
        
    '''Send text message to channel'''
    async def send_text_to_channel(self, channel: discord.TextChannel, content: str):
        await channel.send(content)
        
    '''Start generating response during pause in conversation'''
    async def voice_cb(self):
        response = requests.post(
            self.config.jaison_api_endpoint+'/api/response',
            headers={"Content-type":"application/json"},
            json={"output_audio": True}
        ).json()

        if response['status'] != 200:
            logging.error(f"Failed to start a response job: {response['status']} {response['message']}")
    
    '''Save dialogue per person when the individual finishes speaking'''
    async def user_timeout_cb(self, user_audio_buf: UserAudioBuffer, sink: BufferSink):
        sink.buf_d.pop(user_audio_buf.name)
        response = requests.post(
            self.config.jaison_api_endpoint+'/api/context/conversation/audio',
            headers={"Content-type":"application/json"},
            json={
                "user": user_audio_buf.name,
                "timestamp": user_audio_buf.timestamp,
                "audio_bytes": base64.b64encode(user_audio_buf.audio_bytes).decode('utf-8'),
                "sr": sink.sample_rate,
                "sw": sink.sample_width,
                "ch": sink.channels,
            }
        ).json()
        
        if response['status'] != 200:
            logging.error(f"Failed to start add voice data to conversation: {response['status']} {response['message']}")
    
    async def queue_audio(self, audio_bytes: bytes, sr: int, sw: int, ch: int):
        await self.audio_queue.put({
            "audio_bytes": audio_bytes,
            "sr": sr,
            "sw": sw,
            "ch": ch
        })
    
    async def _play_audio_loop(self):
        while True:
            next_audio: Dict = await self.audio_queue.get()
            if self.vc is not None:
                self.audio_finish_event.clear()
                audio = format_audio(
                    next_audio['audio_bytes'],
                    next_audio['sr'],
                    next_audio['sw'],
                    next_audio['ch']
                )
                source = discord.PCMAudio(audio)
                cb = self._create_cb()
                self.vc.play(source, after=cb)
                await self.audio_finish_event.wait()

    # Creates callback to unblock
    def _create_cb(self):
        def cb(error=None):
            if error:
                logging.error(f"Something went wrong playing audio: {error}")
            self.audio_finish_event.set()
        return cb

    '''
    Main event-listening loop handling JAIson responses.
    '''
    async def _event_listener(self):
        while True:
            try:
                async with websockets.connect(self.config.jaison_ws_endpoint) as ws:
                    logging.info("Connected to JAIson ws server")

                    while True:
                        data = json.loads(await ws.recv())
                        event, status = data[0], data[1]
                        
                        job_id = event.get('response', {}).get('job_id')
                        if job_id is None:
                            logging.warning(f"Got unexpected event: {str(event)}")
                            continue
                        
                        match event['message']:
                            case "response":
                                if job_id not in self.job_data:
                                    self._add_text_job( # Assume any not made here are for audio
                                        job_id,
                                        output_text=False,
                                        text_channel=self.DEFAULT_TEXT_CHANNEL,
                                    )
                                    
                                if event['response'].get('output_type') == 'text_final' and self.job_data[job_id]['output_text'] is True:
                                    if event['response']['finished'] is True and event['response']['success'] is True:
                                        await self.send_text_to_channel(
                                            self.job_data[job_id]['text_channel'],
                                            self.job_data[job_id]['text_content']
                                        )
                                    elif event['response']['finished'] is True and event['response']['success'] is True:
                                        await self.send_text_to_channel(
                                            self.job_data[job_id]['text_channel'],
                                            "Something is wrong with my AI"
                                        )
                                    else:
                                        self.job_data[job_id]['text_content'] += event['response']['content']
                                elif event['response'].get('output_type') == 'tts_final':
                                    if event['response']['finished'] is False:
                                        await self.queue_audio(
                                            base64.b64decode(event['response']['audio_bytes']),
                                            event['response']['sr'],
                                            event['response']['sw'],
                                            event['response']['ch']
                                        )
                            case "job_cancel":
                                self.job_data.pop(job_id)
                            case _:
                                pass
            except OSError:
                logging.error("Server closed suddenly. Attempting reconnect in 5 seconds", exc_info=True)
                self.job_data = dict()
                self.job_queue = list()
                await asyncio.sleep(5)
            except Exception as err:
                logging.error("Event listener encountered an error", exc_info=True)
                self.job_data = dict()
                self.job_queue = list()

    # Needed to keep voice-call listening socket alive during periods of long talking
    # Credit to https://github.com/imayhaveborkedit/discord-ext-voice-recv/issues/8#issuecomment-2614267950
    async def _keep_alive_vc_listening(self):
        while True:
            try:
                await asyncio.sleep(5)
                if self.vc and self.vc.is_connected() and not self.vc.is_playing():
                    self.vc.send_audio_packet(b"\xf8\xff\xfe", encode=False)
            except Exception as err:
                logging.error("keep_alive heartbeat failed", exc_info=True)
                
                
    ## Other functionality
    def clear_conversation(self):
        response = requests.delete(
            self.config.jaison_api_endpoint + '/api/context/conversation'
        ).json()
        
        if response['status'] != 200:
            raise Exception(f"{response['status']} {response['message']}")
    