import argparse
import configparser
import pathlib
import webbrowser
import json
from rauth import OAuth1Service, OAuth1Session


ROOT_DIR = pathlib.Path(__file__).parent.parent


def main(argv):
    parser = argparse.ArgumentParser(description="Tool for covered calls")
    parser.add_argument("--auth", action="store_true", help="Force a redo of authorization from etrade.com")
    args = parser.parse_args(argv)

    config_filename = ROOT_DIR / "coverme" / 'config.ini'
    config = configparser.ConfigParser()
    config.read(str(config_filename))

    session = open_session(
        config['DEFAULT']['CONSUMER_KEY'],
        config['DEFAULT']['CONSUMER_SECRET'],
        force_new_session=args.auth
    )
    base_url = config['DEFAULT']['PROD_BASE_URL']

    etrade = EtradeApi(session, base_url)

    print(etrade.quote('AAPL'))
    print(etrade.quote('CHAP'))
    print(etrade.search("CH"))
    #print(etrade.why_not())
    print(etrade.option_chain('GOOGL'))


def open_session(consumer_key: str, consumer_secret: str, force_new_session: bool = False) -> OAuth1Session:
    session_filename = ROOT_DIR / '.session'

    if force_new_session or not session_filename.is_file():
        """Allows user authorization for the sample application with OAuth 1"""
        etrade = OAuth1Service(
            name="etrade",
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            request_token_url="https://api.etrade.com/oauth/request_token",
            access_token_url="https://api.etrade.com/oauth/access_token",
            authorize_url="https://us.etrade.com/e/t/etws/authorize?key={}&token={}",
            base_url="https://api.etrade.com")

        # Step 1: Get OAuth 1 request token and secret
        request_token, request_token_secret = etrade.get_request_token(
            params={"oauth_callback": "oob", "format": "json"})

        # Step 2: Go through the authentication flow. Login to E*TRADE.
        # After you login, the page will provide a text code to enter.
        authorize_url = etrade.authorize_url.format(etrade.consumer_key, request_token)
        webbrowser.open(authorize_url)
        text_code = input("Please accept agreement and enter text code from browser: ")

        # Step 3: Exchange the authorized request token for an authenticated OAuth 1 session
        session = etrade.get_auth_session(request_token,
                                          request_token_secret,
                                          params={"oauth_verifier": text_code})

        # Save it for later
        serialized_session = {
            'consumer_key': session.consumer_key,
            'consumer_secret': session.consumer_secret,
            'access_token': session.access_token,
            'access_token_secret': session.access_token_secret
        }
        with session_filename.open('w') as f:
            json.dump(serialized_session, f)

    # Always use the serialized session to minimize code paths
    with session_filename.open('r') as f:
        serialized_session = json.load(f)

    session = OAuth1Session(**serialized_session)

    return session

class EtradeApi:
    def __init__(self, session: OAuth1Session, base_url: str):
        self.session = session
        self.base_url = base_url

    def quote(self, symbol: str):
        # URL for the API endpoint
        url = self.base_url + f"/v1/market/quote/{symbol}.json"
        return self._get(url)

    def option_chain(self, symbol: str):
        url = self.base_url + f"/v1/market/optionchains?underlier=AAPL"#.json?underlier={symbol}"
        return self._get(url)

    def search(self, search: str):
        url = self.base_url + f"/v1/market/lookup/{search}.json"#.json?underlier={symbol}"
        return self._get(url)


    def why_not(self):
        url = "https://api.etrade.com/v1/market/optionchains.json?expirationMonth=09&expirationYear=2020&chainType=PUT&skipAdjusted=true&underlier=GOOG"
        return self._get(url)

    def _get(self, url):
        # Make API call for GET request
        response = self.session.get(url)

        if response is not None and response.status_code == 200:
            return response.json()
        else:
            raise IOError(f"Bad response: {response.text}")

