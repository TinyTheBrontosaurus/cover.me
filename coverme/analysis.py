import datetime
import pandas as pd


# Specific to market
SHARES_PER_CONTRACT = 100
FEE_PER_CONTRACT = 0.65  # E*Trade is $0.65/contract as of June 2020
FEE_PER_SHARE = FEE_PER_CONTRACT / SHARES_PER_CONTRACT

# Constants
DAYS_PER_YEAR = 365
TO_PERCENT = 100


class Analysis:
    def __init__(self, quotes: dict, expirations: dict, option_chains: dict):
        self.symbols = list(quotes.keys())
        self.quotes = quotes
        self.expirations = expirations
        self.option_chains = option_chains
        self.today = datetime.date.today()

    @property
    def df_quotes(self) -> pd.DataFrame:
        """
        Convert the quotes structure to a table
        :return: Quotes as a dataframe
        """


        last_prices = [self.quotes[symbol]['quotes']['quote']['last'] for symbol in self.symbols]
        return pd.DataFrame({
            'symbol': self.symbols,
            'last': last_prices,
            'today': [self.today for _ in self.symbols]
        })

    @property
    def df_options_chain(self):
        """
        Conver the options chain to a dataframe. Only grab a subset and only grab calls
        :return: Options chain as a dataframe
        """

        # Only grab certain fields
        to_grab = ["underlying", "ask", "asksize", "bid", "bidsize", "last", "strike", "expiration_date"]
        table = {x: [] for x in to_grab}
        for option_chain in self.option_chains.values():
            for expiration_chain in option_chain.values():
                for contract in expiration_chain['options']['option']:
                    # Only tracking calls
                    if contract['option_type'] == "put":
                        continue
                    for key in to_grab:
                        if key == "expiration_date":
                            contract[key] = datetime.date.fromisoformat(contract[key])
                        table[key].append(contract[key])
        return pd.DataFrame(table)

    @property
    def df_apr(self) -> pd.DataFrame:
        """
        A joint table that performs analysis on the options chain based upon the current stock price
        :return: The joint table
        """
        df_apr = pd.merge(self.df_options_chain, self.df_quotes, left_on="underlying", right_on="symbol",
                          suffixes=("_option", "_stock"))

        # Expected premium per share, minus the fee. "Net premium" is the instance proceeds, and minimum proceeds
        # The "bid" is a conservative estimate of what one can expect to trade at at the moment
        df_apr["net_premium"] = df_apr["bid"] - FEE_PER_SHARE

        # "Max proceeds" is the most one can make, per share, considering the stock exceeds the strike price and the
        # option is exercised. Includes the premium and the fee
        df_apr["max_proceeds"] = df_apr["strike"] - df_apr["last_stock"] + df_apr["net_premium"]

        # Filter out any net premiums do not exceed max proceeds. Likely from an overly low strike price combined with
        # a low premium.
        df_apr["net_premium_adj"] = df_apr[['net_premium', 'max_proceeds']].min(axis=1)

        # The number of days one must commit to the option before the expire
        df_apr["commitment_period"] = df_apr["expiration_date"] - df_apr['today']

        # A number that converts from an instantaneous ratio to a APR based upon the commitment
        # (and to percentage units)
        df_apr["ratio_to_apr"] = DAYS_PER_YEAR / df_apr["commitment_period"].dt.days * TO_PERCENT

        # Calculate each of the above as a ratio of the last stock--effectively normalizing high- and low-priced stocks
        # with each other
        df_apr["net_premium_ratio"] = df_apr["net_premium"] / df_apr["last_stock"]
        df_apr["max_proceeds_ratio"] = df_apr["max_proceeds"] / df_apr["last_stock"]
        df_apr["net_premium_adj_ratio"] = df_apr["net_premium_adj"] / df_apr["last_stock"]

        # Convert the ratio units to an apr (a proper percentage now)
        df_apr["net_premium_adj_apr"] = df_apr['net_premium_adj_ratio'] * df_apr["ratio_to_apr"]
        df_apr["max_proceeds_apr"] = df_apr['max_proceeds_ratio'] * df_apr["ratio_to_apr"]

        # Convert to a per-contract value
        # "How much cash-money is received as premium"
        df_apr["net_premium_per_contract"] = df_apr["bid"] * SHARES_PER_CONTRACT - FEE_PER_CONTRACT
        # "How many assets are tied up
        df_apr["commitment_value_per_contract"] = df_apr["last_stock"] * SHARES_PER_CONTRACT

        return df_apr

    @property
    def df_apr_objective_omit(self) -> pd.DataFrame:

        df_output = self.df_apr

        # Add some rules for good deals that are objectively beaten
        df_output["worse_apr_strike"] = None
        df_output["worse_premium_expiry"] = None
        df_output["worse_strike_expiry"] = None

        for rowi, row in df_output.iterrows():
            # For a fixed expiry date, an option with both a greater APR and and greater strike price is objectively better
            df_output.loc[
                (row['expiration_date'] == df_output['expiration_date']) &
                (row['net_premium_adj_apr'] >= df_output["net_premium_adj_apr"]) &
                (row['strike'] >= df_output["strike"]) &
                # Needs to be the same symbol
                (row['symbol'] == df_output['symbol']) &
                # Don't check itself
                (rowi != df_output.index),
                'worse_apr_strike'] = rowi

            # For a fixed strike price, an option with both a great premium / contract and a sooner expiry date is
            # objectively better
            df_output.loc[
                (row['expiration_date'] <= df_output['expiration_date']) &
                (row['net_premium'] >= df_output["net_premium"]) &
                (row['strike'] == df_output["strike"]) &
                # Needs to be the same symbol
                (row['symbol'] == df_output['symbol']) &
                # Don't check itself
                (rowi != df_output.index),
                'worse_premium_expiry'] = rowi

            # For a fixed APR (with 1%), an option with a sooner expiry date and a >= strike price is possibly better
            df_output.loc[
                (row['expiration_date'] <= df_output['expiration_date']) &
                ((row['net_premium_adj_apr'] - df_output["net_premium_adj_apr"]).abs() < 1) &
                (row['strike'] >= df_output["strike"]) &
                # Needs to be the same symbol
                (row['symbol'] == df_output['symbol']) &
                # Don't check itself
                (rowi != df_output.index),
                'worse_strike_expiry'] = rowi

        return df_output