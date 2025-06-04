import numpy as np
import io

def format_audio(str_bytes, src_sr, src_sw, src_channels):
    dtype = np.dtype(f'i{src_sw}')
    audio_array = np.frombuffer(str_bytes, dtype=dtype) # parse bytes
    audio_array = (audio_array.reshape([int(audio_array.shape[0]/src_channels), src_channels])/src_channels).sum(1) # average across channels into 1 channel
    audio_array = np.interp(np.arange(0, len(audio_array), float(src_sr)/48000), np.arange(0, len(audio_array)), audio_array) # resample
    audio_array = audio_array.flatten().repeat(2) # Discord wants 2 channel audio
    match src_sw: # Rescale volume
        case 1:
            audio_array = audio_array.astype(np.int16) * 256
        case 2:
            audio_array = audio_array.astype(np.int16)
        case 4:
            audio_array = (audio_array / 65536).astype(np.int16)
        case _:
            raise Exception("Invalid sample width given: {src_sw}")

    return audio_array.tobytes()