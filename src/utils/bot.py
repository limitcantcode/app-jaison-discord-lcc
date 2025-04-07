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
from typing import Dict, Set
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
        self.audio_input_queue: asyncio.Queue = None
        self.audio_input_task: asyncio.Task = None
        self.audio_output_job_id: str = None
        self.audio_output_complete_event: asyncio.Event = None
        self.audio_output_queue: asyncio.Queue = None
        self.audio_player_task: asyncio.Task = None
        self.audio_finish_event: asyncio.Event = None
        self.keep_alive_task: asyncio.Task = None
        
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
        self.audio_output_queue = asyncio.Queue()
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
            reply = f"Failed to start a text message: {response['status']} {response['message']}"
            logging.error(reply)
            await self.send_text_to_channel(message.channel, reply)
            return
        
        response = requests.post(
            self.config.jaison_api_endpoint+'/api/response',
            headers={"Content-type":"application/json"},
            json={
                "output_audio": False
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
        self.response_request_id += 1
        await self.audio_input_queue.put({
            "type": "response_request",
            "response_request_id": self.response_request_id
        })
        
    def cancel_inflight_response(self):
        if self.audio_output_job_id is not None and self.audio_output_complete_event.is_set():
            requests.delete(
                self.config.jaison_api_endpoint+'/app/job',
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
                            json={"output_audio": True}
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
        
    async def queue_audio(self, job_id, audio_bytes: bytes = b'', sr: int = -1, sw: int = -1, ch: int = -1, finish: bool = False):
        if finish: 
            await self.audio_output_queue.put({
                "job_id": job_id,
                "finish": True
            })
        elif len(audio_bytes) > 0:
            await self.audio_output_queue.put({
                "job_id": job_id,
                "audio_bytes": audio_bytes,
                "sr": sr,
                "sw": sw,
                "ch": ch
            })
    
    async def _play_audio_loop(self):
        while True:
            next_audio: Dict = await self.audio_output_queue.get()
            if next_audio.get('finish', False): # next_audio['job_id'] == self.audio_output_job_id and next_audio.get('finish', False):
                self.audio_output_complete_event.set()
                continue
            
            if self.vc is not None:
                self.audio_finish_event.clear()
                self.audio_output_complete_event.clear()
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
                                    
                                if event['response'].get('output_type') == 'text_final' and self.job_data.get(job_id, {}).get('output_text', False) is True:
                                    if event['response']['finished'] is True and event['response']['success'] is True:
                                        await self.send_text_to_channel(
                                            self.job_data[job_id]['text_channel'],
                                            self.job_data[job_id]['text_content']
                                        )
                                        del self.job_data[job_id]
                                    elif event['response']['finished'] is True and event['response']['success'] is False:
                                        await self.send_text_to_channel(
                                            self.job_data[job_id]['text_channel'],
                                            "Something is wrong with my AI"
                                        )
                                    else:
                                        self.job_data[job_id]['text_content'] += event['response']['content']
                                elif event['response'].get('output_type') == 'tts_final':
                                    if event['response']['finished'] is False:
                                        await self.queue_audio(
                                            event['response']['job_id'],
                                            audio_bytes=base64.b64decode(event['response']['audio_bytes']),
                                            sr=event['response']['sr'],
                                            sw=event['response']['sw'],
                                            ch=event['response']['ch']
                                        )
                                    else:
                                        await self.queue_audio(
                                            event['response']['job_id'],
                                            finish=True
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
    def clear_history(self):
        response = requests.delete(
            self.config.jaison_api_endpoint + '/api/context'
        ).json()
        
        if response['status'] != 200:
            raise Exception(f"{response['status']} {response['message']}")
    