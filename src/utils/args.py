import argparse

args = argparse.ArgumentParser()
args.add_argument('--config', default="config.yaml", type=str, help="Filepath to VTS configuration file")
args.add_argument('--env', default=None, type=str, help="Filepath to .env file if not default")
args.add_argument('--log_level', default='INFO', choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'], help="Level of logs to output")
args.add_argument('--log_file', default="output.log", type=str, help="Filepath to log output file")
args = args.parse_args()