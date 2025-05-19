from discord.player import AudioSource
from discord.opus import Encoder

class PCMByteBufferAudio(AudioSource):
    """
    Represents raw 16-bit 48KHz stereo PCM audio source.
    """

    def __init__(self) -> None:
        self.stream: bytes = b""
        
    def write(self, audio_bytes) -> None:
        self.stream += audio_bytes

    def read(self) -> bytes:
        ret = self.stream[:Encoder.FRAME_SIZE]
        self.stream = self.stream[Encoder.FRAME_SIZE:]
        if len(ret) != Encoder.FRAME_SIZE:
            return b''
        return ret