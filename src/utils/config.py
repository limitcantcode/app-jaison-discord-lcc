import yaml
from utils.args import args

class Config():
    def __init__(self):
        with open(args.config, 'r') as f:
            self.config = yaml.safe_load(f)
        self.jaison_api_endpoint = self.config['jaison-api-endpoint']
        self.jaison_ws_endpoint = self.config['jaison-ws-endpoint']
        self.opus_filepath = self.config['opus-filepath']
        self.idle_interval = self.config['idle-interval']
        assert(self.jaison_api_endpoint is not None)
        assert(self.jaison_ws_endpoint is not None)
        assert(self.idle_interval >= 0)

config = Config()