import requests
from requests.adapters import HTTPAdapter

import argparse
from coverme.log_folder import LogFolder
import pathlib
from coverme.config import coverme_config
from loguru import logger
from coverme import definitions
from coverme import conguru
from coverme.version import __version__


template = {}

def main(argv):
    parser = argparse.ArgumentParser(description="Tool for covered calls")
    parser.add_argument('--config', '-c', help='App config.', type=str,
                        default=str(definitions.CONFIG_DIR / "config.yml"))
    parser.add_argument("--cache", dest="use_cache", action="store_true",
                        help="Force to use locally cached data")
    args = parser.parse_args(argv)


    # Conguru
    conguru.conguru_init(args, argv, coverme_config, template, definitions.LOG_DIR, __version__)

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
