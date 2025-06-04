'''
Discord Bot Main Class to interface with Discord
'''

import discord
import asyncio
from asyncio import CancelledError
import os
import json
import requests
import base64
import websockets
import logging
from typing import Dict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from commands import add_commands
from audio.sink import BufferSink, UserAudioBuffer
from audio.source import PCMByteBufferAudio
from utils.config import config
from utils.helper.audio import format_audio
from utils.time import get_current_time

AUDIO_PACKET_SIZE = 4096

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
        self.audio_input_queue: asyncio.Queue = None
        self.audio_input_task: asyncio.Task = None
        self.audio_output_job_id: str = None
        self.audio_output_complete_event: asyncio.Event = None
        self.audio_player_task: asyncio.Task = None
        self.audio_output: PCMByteBufferAudio = None
        self.audio_ready: asyncio.Event = None
        
        self.response_request_id: int = 0

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
        self.audio_input_queue = asyncio.Queue()
        self.audio_input_task = asyncio.create_task(self._input_audio_loop())
        self.audio_output_job_id = None
        self.audio_output_complete_event = asyncio.Event()
        self.audio_output_complete_event.set()
        
        self.audio_player_task = asyncio.create_task(self._play_audio_loop())
        self.audio_output = PCMByteBufferAudio()
        self.audio_ready = asyncio.Event()
        
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
            reply = f"Failed to start a text message: {response['status']} {response['message']}"
            logging.error(reply)
            await self.send_text_to_channel(message.channel, reply)
            return
        
        response = requests.post(
            self.config.jaison_api_endpoint+'/api/response',
            headers={"Content-type":"application/json"},
            json={
                "include_audio": False
            }
        ).json()
        if response['status'] != 200:
            reply = f"Failed to start a texting response job: {response['status']} {response['message']}"
            logging.error(reply)
            await self.send_text_to_channel(message.channel, reply)
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
        include_audio: bool = False,
        text_channel: discord.TextChannel = None
    ):
        self.job_data[job_id] = { # Specific tracking for text messages. Audio will be naive
            "output_text": output_text,
            "include_audio": include_audio,
            "text_content": "",
            "text_channel": text_channel
        }
        
    '''Send text message to channel'''
    async def send_text_to_channel(self, channel: discord.TextChannel, content: str):
        await channel.send(content)
        
    '''Start generating response during pause in conversation'''
    async def voice_cb(self):
        self.response_request_id += 1
        await self.audio_input_queue.put({
            "type": "response_request",
            "response_request_id": self.response_request_id
        })
        
    def cancel_inflight_response(self):
        if self.audio_output_job_id is not None and self.audio_output_complete_event.is_set():
            requests.delete(
                self.config.jaison_api_endpoint+'/api/job',
                headers={"Content-type":"application/json"},
                json={
                    "job_id": self.audio_output_job_id,
                    "reason": "Preventing interruption in conversation"
                }
            )
            self.audio_output_job_id = None
    
    async def _input_audio_loop(self):
        while True:
            try:
                input_d = await self.audio_input_queue.get()
                if input_d['type'] == 'audio_input':
                    response = requests.post(
                        self.config.jaison_api_endpoint+'/api/context/conversation/audio',
                        headers={"Content-type":"application/json"},
                        json={
                            "user": input_d['name'],
                            "timestamp": input_d['timestamp'],
                            "audio_bytes": base64.b64encode(input_d['audio_bytes']).decode('utf-8'),
                            "sr": input_d['sr'],
                            "sw": input_d['sw'],
                            "ch": input_d['ch'],
                        }
                    ).json()
                    
                    if response['status'] != 200:
                        raise Exception(f"Failed to start add voice data to conversation: {response['status']} {response['message']}")
                elif input_d['type'] == 'response_request':
                    if input_d['response_request_id'] == self.response_request_id:
                        self.cancel_inflight_response()
                        await self.audio_output_complete_event.wait()
                        response = requests.post(
                            self.config.jaison_api_endpoint+'/api/response',
                            headers={"Content-type":"application/json"},
                            json={"include_audio": True}
                        ).json()

                        if response['status'] != 200:
                            raise Exception(f"Failed to start a response job: {response['status']} {response['message']}")
                            
                        self.audio_output_job_id = response['response']['job_id']
                else:
                    raise Exception(f"Unexpected input dictionary in queue: {input_d}")
            except CancelledError:
                raise
            except Exception as err:
                logging.error("Error occured while processing job queue", exc_info=True)
    
    '''Save dialogue per person when the individual finishes speaking'''
    async def user_timeout_cb(self, user_audio_buf: UserAudioBuffer, sink: BufferSink):            
        sink.buf_d.pop(user_audio_buf.name)
        await self.audio_input_queue.put({
            "type": "audio_input",
            "name": user_audio_buf.name,
            "timestamp": user_audio_buf.timestamp,
            "audio_bytes": user_audio_buf.audio_bytes,
            "sr": sink.sample_rate,
            "sw": sink.sample_width,
            "ch": sink.channels
        })
        
    async def queue_audio(self, job_id, audio_bytes: bytes = b'', sr: int = -1, sw: int = -1, ch: int = -1):
        audio = format_audio(
            audio_bytes,
            sr,
            sw,
            ch
        )
        self.audio_output.write(audio)
        self.audio_ready.set()
                
    async def _play_audio_loop(self):
        while True:
            if len(self.audio_output.stream) == 0:
                self.audio_ready.clear()
                await self.audio_ready.wait()
                
            
            if not self.vc.is_playing():
                self.audio_output_complete_event.clear()
                self.vc.play(self.audio_output, after=self._create_cb())
                await self.audio_output_complete_event.wait()

    #Creates callback to unblock
    def _create_cb(self):
        def cb(error=None):
            if error:
                logging.error(f"Something went wrong playing audio: {error}")
            self.audio_output_complete_event.set()
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
                        response = event.get("response", {})
                        job_id = response.get('job_id')
                        result = response.get("result", {})
                        
                        if job_id is None:
                            logging.warning(f"Got unexpected event: {str(event)}")
                            continue
                        
                        match event.get('message', ""):
                            case "response": # Response pipeline
                                if "start" in response and job_id not in self.job_data:
                                    self._add_text_job( # Assume any not made here are for audio
                                        job_id,
                                        output_text=False,
                                        include_audio=response.get("start", {}).get("include_audio", False),
                                        text_channel=self.DEFAULT_TEXT_CHANNEL,
                                    )
                                    
                                if "content" in result:
                                    self.job_data[job_id]['text_content'] += " " + result['content']
                                    
                                if "audio_bytes" in result:
                                    await self.queue_audio(
                                        job_id,
                                        audio_bytes=base64.b64decode(result['audio_bytes']),
                                        sr=result['sr'],
                                        sw=result['sw'],
                                        ch=result['ch']
                                    )
                                    
                                if response.get("finished", False):
                                    if response.get("success", False) and self.job_data[job_id]['output_text']:
                                        await self.send_text_to_channel(
                                            self.job_data[job_id]['text_channel'],
                                            self.job_data[job_id]['text_content'] or "Something is wrong with my AI"
                                        )
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