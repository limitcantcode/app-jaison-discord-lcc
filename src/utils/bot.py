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
from commands import add_commands
from commands.sink import BufferSink
from utils.logging import logger
from utils.config import config
from utils.helper.audio import format_audio
from utils.time import get_current_time

class DiscordBot(discord.Client):

    def __init__(self):
        if config.opus_filepath is not None: discord.opus.load_opus(config.opus_filepath)

        logger.debug("Activating with all intents...")
        super().__init__(intents=discord.Intents.all())
        logger.debug("Reloading command tree...")
        self.tree, self.tree_params = add_commands(self, os.getenv("DISCORD_SERVER_ID"))
        self.config = config

        self.vc = None
        self.DEFAULT_TEXT_CHANNEL = discord.Object(os.getenv("DISCORD_DEFAULT_TEXT_CHANNEL"))
        self.jaison_event_task = asyncio.create_task(self._event_listener())
        self.keep_alive_task = asyncio.create_task(self._keep_alive_vc_listening())
        self.run_data = dict()
        self.run_queue = list()

    # Handler for bot activation
    async def on_ready(self):
        await self.tree.sync(**self.tree_params)
        logger.debug(f"Command tree resynced with params: {self.tree_params}")
        logger.info("Discord Bot is ready!")

    # Handler for any new messages
    async def on_message(self, message):
        # Skip messages from self
        if self.application_id == message.author.id:
            return

        # Generate response
        user = message.author.display_name or message.author.global_name
        content = message.content
        logger.debug(f"Message by user {user}: {content}")
        
        await message.channel.typing()
        response = requests.post(
            self.config.jaison_api_endpoint+'/run',
            headers={"Content-type":"application/json"},
            json={
                "process_dialog": True,
                "input_user": user,
                "input_time": get_current_time(),
                "input_text": content,
                "output_text": True,
                "output_audio": False
            }
        ).json()

        if response['status'] == 500:
            logger.error(f"Failed to start a run: {response['message']}")
            return

        self._add_response_job(
            response['response']['run_id'],
            output_text=True,
            output_audio=False,
            text_channel=message.channel,
            voice_client=None
        )

    async def voice_cb(self, sink: BufferSink):
        await self.request_voice_response(sink)

    # Track runs sent to jaison-core
    def _add_response_job(
        self,
        run_id: str,
        output_text: bool = False,
        output_audio: bool = False,
        text_channel: discord.TextChannel = None,
        voice_client: discord.VoiceClient = None
    ):
        existing = self.run_data.get(run_id)
        completion_future = None
        futures_prior = None
        if existing:
            text_channel = text_channel or existing['text_channel']
            voice_client = voice_client or existing['voice_client']
            completion_future = existing['completion_future']
            futures_prior = existing['futures_prior']
        else:
            completion_future = asyncio.Future()
            futures_prior = list(self.run_queue)
            self.run_queue.append(completion_future)

        self.run_data[run_id] = {
            "text_result": "",
            "audio_result": b"",
            "audio_sr": None,
            "audio_sw": None,
            "audio_channels": None,
            "text_success": True,
            "audio_success": True,
            "output_text": output_text,
            "output_audio": output_audio,
            "text_channel": text_channel,
            "voice_client": voice_client,
            "completion_future": completion_future,
            "futures_prior": futures_prior
        }

    '''
    Response pipeline initiator

    Sends all audio to jaison-core in order of beginning speech,
    requesting a response after the last audio input.

    TODO: breaks in multi-turn conversations with multiple people as multiple lines per person turn into 1 long line
    '''
    async def request_voice_response(self, sink: BufferSink):
        logger.debug("Running Discord bot's voice callback...")
        global stt
        # TODO preprocess and determine if its worth getting a response for

        # Once you know you want to try and respond
        voice_data = dict()
        for user in sink.buf:
            try:
                idx = len(sink.buf[user][1])
                if idx > 0:
                    voice_data[sink.buf[user][0]] = (user, sink.buf[user][1][:idx])
                    sink.freshen(user, idx=idx)
            except Exception as err:
                logger.error("Failed to save audio recording to file", exc_info=True, stack_info=True)
                continue
        
        if len(voice_data) == 0: return

        sorted_timestamps = sorted(voice_data.keys())
        for i in range(len(sorted_timestamps)):
            ts = sorted_timestamps[i]
            data = voice_data[ts]
            should_generate_response = i == len(sorted_timestamps)-1
            response = requests.post(
                self.config.jaison_api_endpoint+'/run',
                headers={"Content-type":"application/json"},
                json={
                    "process_dialog": True,
                    "input_user": data[0],
                    "input_time": ts,
                    "input_audio_bytes": base64.b64encode(data[1]).decode('utf-8'),
                    "input_audio_sample_rate": sink.sample_rate,
                    "input_audio_sample_width": sink.sample_width,
                    "input_audio_channels": sink.channels,
                    "output_text": should_generate_response,
                    "output_audio": should_generate_response
                }
            ).json()

            if response['status'] == 500:
                logger.error(f"Failed to start a run: {response['message']}")
                continue

            self._add_response_job(
                response['response']['run_id'],
                output_text=should_generate_response,
                output_audio=should_generate_response,
                text_channel=None,
                voice_client=self.vc
            )
    
    # Play audio, but wait for all previous responses to finish playing
    async def play_audio(self, run_id):
        await asyncio.gather(*self.run_data[run_id]["futures_prior"])
        data = self.run_data[run_id]
        audio = format_audio(
            data['audio_result'],
            data['audio_sr'],
            data['audio_sw'],
            data['audio_channels']
        )

        source = discord.PCMAudio(audio)
        cb = self.create_cb(run_id)
        self.vc.play(source, after=cb)

    # Creates callback to unblock and cleanup after playing audio response
    def create_cb(self, run_id):
        def cb(error=None):
            if error:
                logger.error(f"Something went wrong using response for {run_id}: {error}")
            run = self.run_data[run_id]
            run['completion_future'].set_result(None)
            self.run_queue.pop(0)
            del self.run_data[run_id]
            logger.debug(f"Completed {run_id}")
        return cb
    
    # Send text message to a channel
    async def send_text_to_channel(self, run_id):
        await asyncio.gather(*self.run_data[run_id]["futures_prior"])
        message, channel = self.run_data[run_id]['text_result'], self.run_data[run_id]['text_channel']
        await channel.send(message)
        self.create_cb(run_id)()

    '''
    Main event-listening loop handling JAIson responses.
    '''
    async def _event_listener(self):
        while True:
            try:
                async with websockets.connect(self.config.jaison_ws_endpoint) as ws:
                    logger.info("Connected to JAIson ws server")

                    while True:
                        data = json.loads(await ws.recv())
                        event, status = data[0], data[1]
                        logger.debug(f"Event received {str(event):.200}")
                        match event['message']:
                            case "run_start":
                                if event['response']['run_id'] not in self.run_data:
                                    if not event['response']['output_text'] and not event['response']['output_audio']: continue
                                    self._add_response_job(
                                        event['response']['run_id'],
                                        output_text=event['response']['output_text'],
                                        output_audio=event['response']['output_audio'],
                                        text_channel=None if event['response']['output_audio'] else self.DEFAULT_TEXT_CHANNEL,
                                        voice_client=self.vc
                                    )
                            case "run_finish":
                                pass
                            case "run_cancel":
                                run = self.run_data[event['response']['run_id']]
                                run['completion_future'].set_result(None)
                                self.run_queue.remove(run['completion_future'])
                                del run
                            case "run_t2t_chunk":
                                if self.run_data[event['response']['run_id']]['text_success'] != event['response']['success']:
                                    self.run_data[event['response']['run_id']] = self.run_data[event['response']['run_id']] | {
                                        'text_success': event['response']['success'],
                                        "text_result": event['response']['chunk']
                                    }
                                else:
                                    self.run_data[event['response']['run_id']]['text_result'] += event['response']['chunk']
                            case "run_t2t_stop":
                                if (
                                    self.run_data[event['response']['run_id']]['output_text'] 
                                    and self.run_data[event['response']['run_id']]['text_channel']
                                ):
                                    await self.send_text_to_channel(event['response']['run_id'])
                            case "run_tts_chunk":
                                if self.run_data[event['response']['run_id']]['audio_success'] != event['response']['success']:
                                    self.run_data[event['response']['run_id']] = self.run_data[event['response']['run_id']] | {
                                        'audio_success': event['response']['success'],
                                        "audio_result": base64.b64decode(event['response']['chunk']),
                                        "audio_sr": event['response']['sample_rate'],
                                        "audio_sw": event['response']['sample_width'],
                                        "audio_channels": event['response']['channels']
                                    }
                                else:
                                    self.run_data[event['response']['run_id']] = self.run_data[event['response']['run_id']] | {
                                        "audio_result": self.run_data[event['response']['run_id']]['audio_result'] + base64.b64decode(event['response']['chunk']),
                                        "audio_sr": event['response']['sample_rate'],
                                        "audio_sw": event['response']['sample_width'],
                                        "audio_channels": event['response']['channels']
                                    }
                            case "run_tts_stop":
                                await self.play_audio(event['response']['run_id'])
                            case _:
                                pass
            except OSError:
                logger.error("Server closed suddenly. Attempting reconnect in 5 seconds", exc_info=True)
                self.run_data = dict()
                self.run_queue = list()
                await asyncio.sleep(5)
            except Exception as err:
                logger.error("Event listener encountered an error", exc_info=True)
                self.run_data = dict()
                self.run_queue = list()

    # Needed to keep voice-call listening socket alive during periods of long talking
    # Credit to https://github.com/imayhaveborkedit/discord-ext-voice-recv/issues/8#issuecomment-2614267950
    async def _keep_alive_vc_listening(self):
        while True:
            try:
                await asyncio.sleep(5)
                if self.vc and self.vc.is_connected() and not self.vc.is_playing():
                    self.vc.send_audio_packet(b"\xf8\xff\xfe", encode=False)
            except Exception as err:
                logger.error("keep_alive heartbeat failed", exc_info=True)