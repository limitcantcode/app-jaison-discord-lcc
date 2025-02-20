## About The Project

Discord Bot app plugin for [Project J.A.I.son](https://github.com/limitcantcode/jaison-core). Can text and chat in voice call.

### Installation

This project was tested on python3.12
 
1. Create and activate your virtual environment using `conda` or `venv`.
2. Install dependencies `pip install -r requirements.txt`
3. Setup [Discord bot](https://discord.com/developers/applications). Ensure your bot has the right OAuth2 permissions when it joins your server (Scope -> Bot, Bot Permissions -> Administrator if unsure). Invite your bot to your server.
4. Setup `.env` file following `.env-template`. You can find you Discord Bot token after creating a bot as shown below:

<img src="./assets/discord_1.png" alt="discord bot token location" height="200"/>

5. Setup `config.yaml` to where [jaison-core](https://github.com/limitcantcode/jaison-core) is running. `jaison-api-endpoint` should start with `http(s)://` and `jaison-ws-endpoint` with `ws://`. If not on Windows, add the filepath to [libopus](https://github.com/shardlab/discordrb/wiki/Installing-libopus) in `config.yaml`.

## Usage

After setting things up, you can simply run `python ./src/main.py`

For runtime options, run `python ./src/main.py --help`

Texting works like texting a friend. As long as the bot can see the channel, they will respond.

Have the bot join the channel using `/join_vc`. Have them leave using `/leave_vc`. Talking is also like talking to a friend. No need to time recordings, just talk and wait.

## Contributing

Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".
Don't forget to give the project a star! Thanks again!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

Distributed under the MIT License. See `LICENSE.txt` for more information.

## Contact

Project J.A.I.son: https://github.com/limitcantcode/jaison-core

Join the community Discord: https://discord.gg/Z8yyEzHsYM
