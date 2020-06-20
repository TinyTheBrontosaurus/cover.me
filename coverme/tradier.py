import requests
from requests.adapters import HTTPAdapter

import argparse
from coverme.log_folder import LogFolder
import pathlib
import confuse
import coverme
from coverme.config import coverme_config
from loguru import logger
from coverme import definitions
from coverme.version import __version__
import shutil


template = {}

def main(argv):
    parser = argparse.ArgumentParser(description="Tool for covered calls")
    parser.add_argument('--config', '-c', help='App config.', type=pathlib.Path,
                        default=definitions.CONFIG_DIR / "config.yml")
    parser.add_argument("--cache", dest="use_cache", action="store_true",
                        help="Force to use locally cached data")
    args = parser.parse_args(argv)


    # Parse the config using confuse, bailing on failure
    try:

        if args.config:
            coverme_config.set_file(args.config)
        coverme_config.set_args(args, dots=True)

        logger.debug('configurations from {}', [x.filename for x in coverme_config.sources])

        valid_config = coverme_config.get(template)

        coverme.config.filename = args.config

    except confuse.ConfigError as ex:
        logger.critical("Problem parsing config: {}", ex)
        return

    # Cache old log path
    coverme.config.log_name = coverme_config['name'].get()

    try:
        LogFolder.get_latest_log_folder(definitions.LOG_DIR / coverme_config.config.log_name)
    except FileNotFoundError:
        pass

    # Create log path
    LogFolder.set_path(definitions.LOG_DIR, coverme_config.config.log_name)

    # Initialize logger
    logger.add(LogFolder.folder / "event.log", level="INFO")
    logger.info("Running program: {}", coverme_config['name'].get())
    logger.info("Version: {}", __version__)
    logger.info("Log folder: {}", LogFolder.folder)

    # Don't lost to stderr anymore
    logger.remove(0)

    # Copy configs
    # Straight copy
    orig_config = pathlib.Path(args.config)
    shutil.copyfile(str(orig_config), str(LogFolder.folder / orig_config.name))
    logger.info("CLI args: {}", argv)

    # Copy resulting config
    with open(LogFolder.folder / "config.yml", 'w') as f:
        f.write(coverme_config.dump())


    # Read config
    session = open_session(
        coverme_config['tradier']['key'].get()
    )
    base_url = coverme_config['tradier']['base_url'].get()
    market_api = TradierApi(session, base_url)

    symbols = coverme_config['symbols'].get()

    print(market_api.quote('AAPL'))
    print(market_api.quote('CHAP'))
    expirations = market_api.options_expirations('CHAP')
    print(expirations)
    for expiration in expirations["expirations"]["date"]:
        option = market_api.option_chain('CHAP', expiration)
        print(option)


def open_session(api_key: str) -> requests.Session:
    session = requests.Session()
    session.mount('https://', HTTPAdapter(max_retries=1))
    session.headers.update({'Authorization': 'Bearer ' + api_key, 'Accept': 'application/json'})

    return session

class TradierApi:
    def __init__(self, session: requests.Session, base_url: str):
        """
        https://documentation.tradier.com/brokerage-api/overview/market-data
        """
        self.session = session
        self.base_url = base_url

    def quote(self, symbol: str):
        # URL for the API endpoint
        url = self.base_url + f"/v1/markets/quotes"
        params = {"symbols": symbol}
        return self._get(url, params)

    def options_expirations(self, symbol: str):
        # URL for the API endpoint
        url = self.base_url + f"/v1/markets/options/expirations"
        params = {"symbol": symbol}
        return self._get(url, params)

    def option_chain(self, symbol: str, expiration: str):
        url = self.base_url + f"/v1/markets/options/chains"
        params = {"symbol": symbol, "expiration": expiration}
        return self._get(url, params)

    def _get(self, url, params):
        # Make API call for GET request
        response = self.session.get(url, params=params)

        if response is not None and response.status_code == 200:
            return response.json()
        else:
            raise IOError(f"Bad response: {response.text}")




#
# symbol = "CHAP"
#
# url = 'https://sandbox.tradier.com/v1/markets/options/expirations'
# params = {'symbol': symbol}
# r = session.get(url, params=params)
#
# url = 'https://api.tradier.com/v1/markets/options/chains'
# params = {'symbol': symbol, 'expiration': expiration}
# r = session.get(url, params=params)
