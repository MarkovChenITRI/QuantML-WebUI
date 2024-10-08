from resources import GetCodeIndexes, GetEPS, GetPE, GetPrice, GetBeta, GetSharpo
from sklearn.linear_model import LinearRegression
from scipy.optimize import linprog
from neo4j import GraphDatabase
import pandas as pd
import numpy as np
import yfinance as yf

class GlobalMarket():
    def __init__(self):
        self.CODES = {"Forex": ['GC=F', 'USDCNY=X', 'USDJPY=X', 'USDEUR=X', 'USDHKD=X', 'USDKRW=X'],
                      "Debt": ['^TNX'],
                      "Futures": ['GC=F', 'CL=F'],
                      "Crypto": ['BTC-USD', 'ETH-USD'],
                      "Stock": ['^HSI', '^HSCE', '000001.SS', '399001.SZ',    # China
                                '^DJI', '^GSPC', '^IXIC',                     # UnitedStates
                                '^TWII',                                      # Taiwan
                                '^N225',                                      # Japan
                                '^KS11',                                      # Korea
                                ]}

    def summary(self, retry_time = 3):
        print(f'GlobalMarket.summary()')
        self.df = GetCodeIndexes("USDTWD=X").tz_convert('Asia/Taipei')
        self.df.index = self.df.index.date
        for market in self.CODES:
            for code in self.CODES[market]:
                for _ in range(retry_time):
                    #try:
                    self.add(code)
                    break
                    #except:
                    #    pass
        return self.df

    def add(self, code):
      if code not in self.df.columns:
        temp_df = GetCodeIndexes(code).tz_convert('Asia/Taipei')
        temp_df.index = temp_df.index.date
        temp_df = temp_df[~temp_df.index.duplicated(keep='first')]
        self.df = pd.concat([self.df, temp_df.loc[self.df.index[0]:, ]], axis=1).sort_index()
        print(' -', code, 'added to dataset.', self.df.shape)
      self.df = self.df.ffill().dropna()


    def predict(self,  code, delay = None):
      self.add(code)
      if delay is None:
        df = self.df.copy()
      else:
        df = self.df.copy().iloc[: delay, ]
      print('Prediction Used Date:', df.index[-1])
      long_index, short_index = int(df.shape[0] - 90), int(df.shape[0] - 5)
      y_col, X_col = [f'{code}/Pred'], [i for i in df if 'State' in i or 'Bias' in i]
      input, label = np.array(df.copy().loc[: , X_col]), np.array(df.copy().loc[: , y_col])
      model = LinearRegression().fit(input[: short_index], label[: short_index])
      pred, short_score, long_score = model.predict(input[-1: ])[0][0], model.score(input[short_index: ], label[short_index: ]), model.score(input[long_index: ], label[long_index: ])
      return pred, int(list(df[code])[-1]), short_score, long_score

class UtilityMarket():
    def __init__(self):
        AURA_CONNECTION_URI = "neo4j+s://6d2f5b5d.databases.neo4j.io"
        AURA_USERNAME = "neo4j"
        AURA_PASSWORD = "ZzZ6zeBZ1N7fB_UAHezzHY0LajAXj2z7tmI2HwHPWa8" #@param ["ZzZ6zeBZ1N7fB_UAHezzHY0LajAXj2z7tmI2HwHPWa8"]
        self.driver = GraphDatabase.driver(AURA_CONNECTION_URI, auth=(AURA_USERNAME, AURA_PASSWORD))
    
    def auto_update(self, code, market, USD): 
        temp_df = yf.Ticker(code)
        UPDATE, PRICE = GetPrice(temp_df, market, USD)
        EPS = GetEPS(temp_df, market, USD)
        PE_RATIO = GetPE(temp_df)
        BETA = GetBeta(temp_df)
        SHARPO = GetSharpo(code)
        return UPDATE, PRICE, EPS, PE_RATIO, BETA, SHARPO

    def summary(self, USD = 32, retry_time = 3):
        print(f'UtilityMarket.summary()')
        summary_table = []
        with self.driver.session() as session:
            utility = [i['u'] for i in session.run("MATCH (u:utility) RETURN u").data()]
            for u in utility:
                print(u)
                UPDATE, PRICE, EPS, PE_RATIO, BETA, SHARPO = self.auto_update(u['code'], u['market'], USD)
                summary_table.append([u['name'], u['market'], UPDATE, PRICE, EPS, PE_RATIO, BETA, SHARPO])

            self.df = pd.DataFrame(summary_table, columns=['name', 'market', 'update', 'price', 'eps', 'pe_ratio', 'beta', 'sharpo'])
            self.df = self.df.replace(np.nan, None)
            for col in self.df.loc[:, ['price', 'eps', 'pe_ratio', 'beta', 'sharpo']]:
                self.df[col] = self.df[col].fillna(np.mean(self.df[col]))

            for name, market, update, price, eps, pe_ratio, beta, sharpo in self.df.values.tolist():
                session.run("MATCH (u:utility WHERE u.name='{name}')  set u.update='{update}' set u.price='{price}' set u.eps='{eps}'\
                            set u.pe_ratio='{pe_ratio}'  set u.beta='{beta}'  set u.sharpo='{sharpo}'".format(name=name, 
                                                                                                            update=update,
                                                                                                            price=str(price), 
                                                                                                            eps=str(eps), 
                                                                                                            pe_ratio=str(pe_ratio),
                                                                                                            beta=str(beta),
                                                                                                            sharpo=str(sharpo),
                                                                                                            )
                            )

        return self.df

    def predict(self, df, futures_df, valid_market):
        df['chosed'] = [1 if market in valid_market else 0 for market in df['market']]
        df = df[df['chosed'] == 1]
        market_risks = {market: np.mean(df[df['market'] == market]['beta']) for market in set(list(df['market']))}
        df['risk_limit'] = [max([0.0000001, market_risks[market] * futures_df.loc[market, 'status']]) for market in df['market']]
        df.loc[df.index[-1],:] = ['TWD', '', ''] + [1 for i in range(7)]
        df['risk'] = list(df['beta'] - df['risk_limit']) / df['risk_limit']

        df["X"] = linprog(c      =  list(df['sharpo'] * df['chosed'] * -1),
                    A_ub   =  [list(df['risk']),   [1 for _ in range(df.shape[0])]], #coefficient of variables for each constraint
                    b_ub   =  [1, 1],    #y value of constraints
                    bounds =  [(0, 1) for _ in range(df.shape[0])], #interval of each variable
                    method =  "highs").x
        df = df.set_index('name')
        df["X"] = np.round(df["X"], 2)
        return df.loc[:, ['price', 'eps', 'pe_ratio', 'beta', 'sharpo', 'X']]
