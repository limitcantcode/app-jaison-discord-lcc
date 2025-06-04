import datetime

'''Get back the UNIX timestamp in ms'''
def get_current_time() -> int:
    return int(datetime.datetime.now().replace(microsecond=0).timestamp())