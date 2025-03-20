import datetime
import logging
import uuid
from typing import Dict, Callable
from discord.ext import voice_recv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.time import get_current_time

'''
Custom audio sink for managing call audio and triggering callback during silence.
This sink will save all recorded audio to buffer in memory. This buffer can be read
directly from this class at any time. Audio buffer will not be truncated until freshen(idx)
is called, to which all data up to and including idx will be truncated.
Audio is tracked per user in the call in the dictionary buf.
'''
class BufferSink(voice_recv.AudioSink):
    # Requires a callback function <fun(buf: BufferSink)> that will be called during silence
    # Callback accepts one arguement, and that is this BufferSink instance
    def __init__(self, scheduler: AsyncIOScheduler, stale_cb: Callable, user_timeout_cb: Callable):
        self.buf_d: Dict[str, UserAudioBuffer] = dict()
        self.channels: int = 1
        self.sample_width: int = 2
        self.sample_rate: int = 96000

        self.scheduler = scheduler
        self.stale_timer = None
        self.stale_cb = stale_cb
        self.user_timeout_cb = user_timeout_cb

    def wants_opus(self) -> bool:
        return False

	# just append data to the byte array
    def write(self, user, data) -> None:
        self.stale_timer = self.scheduler.add_job(
            self.stale_cb,
            'date',
            run_date=datetime.datetime.now()+datetime.timedelta(seconds=1.0),
            args=[],
            id='vc_buffer_timer',
            replace_existing=True
        )
        if user.display_name not in self.buf_d:
            self.buf_d[user.display_name] = UserAudioBuffer(self, user.display_name, self.scheduler, self.user_timeout_cb)
        self.buf_d[user.display_name].write(bytes(data.pcm))
        
    def cleanup(self) -> None:
        logging.info("BufferSink cleaning up")
        self.scheduler.remove_all_jobs()
        
class UserAudioBuffer:
    def __init__(
        self,
        sink: BufferSink,
        name: str,
        scheduler: AsyncIOScheduler,
        timeout_cb: Callable[["UserAudioBuffer",BufferSink], None]
    ):
        self.sink:BufferSink = sink
        self.id = "{}__ab__{}".format(name, uuid.uuid4())
        self.name: str = name
        self.timestamp: int = get_current_time()
        self.audio_bytes: bytes = b''
        
        self.scheduler = scheduler
        self.timeout_cb: Callable[["UserAudioBuffer",BufferSink], None] = timeout_cb
        self.timeout = None
        
    def write(self, audio_bytes: bytes):
        self.audio_bytes += audio_bytes
        self.timeout = self.scheduler.add_job(
            self.timeout_cb,
            'date',
            run_date=datetime.datetime.now()+datetime.timedelta(seconds=0.5),
            args=[self, self.sink],
            id=self.id,
            replace_existing=True
        )