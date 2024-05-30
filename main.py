import functions_framework, base64, warnings, smtplib

from config import Market
from optimizers import Fit_Regressor, Shares_Optimizer
from database import Indexes
from message import send_message
from email.mime.text import MIMEText

import numpy as np

@functions_framework.cloud_event
def hello_pubsub(cloud_event):
    warnings.filterwarnings("ignore")

    #analysis
    config = Market()
    market_df, options = config.get_data(pred_options = ["UnitedStates", "Taiwan", "Universe"])
    market_state, score = Fit_Regressor(market_df, options, 0.05)
    analysis_df = Indexes(list(market_df['USDTWD=X'])[-1])
    analysis_df.loc[analysis_df.index[-1],:] = ['TWD', 'TWSE', '', 1, 1, 1, 1, 1]

    #message
    timestamps = market_df.index
    period = int((timestamps[-1] - timestamps[0])/ np.timedelta64(1, 'Y'))
    report = f'【System Info】\n Start Date: {timestamps.astype(str)[0]} \n End Date: {timestamps.astype(str)[-1]} \n Cycle: {period} years\n'
    report += '\n【Market Statement】'
    confidence_level = int(score * 100)
    for i in market_state:
      j, k = i.strip('^').strip('/Pred'), round(market_state.loc['Trend', i], 2)
      report += f'\n {j}: {k}'
    report += f'\n (confidence level: {confidence_level}%)'
    send_message(report)

    #e-mail
    html = ''

    df = Shares_Optimizer(analysis_df, market_state, options, score, ['UnitedStates', 'Taiwan'])
    df = df.iloc[:-4, ].loc[:, ["name", 'market', "pe_ratio", "beta", "sharpo", "X"]].round(2)
    bull = df.where(df['X'] > 0).dropna().loc[:, ["name", 'market', "beta", "sharpo", "X"]]
    bull.columns = ["Name", 'Market', "Beta", "Sharpe Ratio", "Suggest Position"]
    html += "台/美股投資組合推薦<br>" + bull.to_html() + "<br>"

    df = Shares_Optimizer(analysis_df, market_state, options, score, ['UnitedStates'])
    df = df.iloc[:-4, ].loc[:, ["name", 'market', "pe_ratio", "beta", "sharpo", "X"]].round(2)
    bull = df.where(df['X'] > 0).dropna().loc[:, ["name", 'market', "beta", "sharpo", "X"]]
    bull.columns = ["Name", 'Market', "Beta", "Sharpe Ratio", "Suggest Position"]
    html += "美股投資組合推薦<br>" + bull.to_html() + "<br>"

    df = Shares_Optimizer(analysis_df, market_state, options, score, ['Taiwan'])
    df = df.iloc[:-4, ].loc[:, ["name", 'market', "pe_ratio", "beta", "sharpo", "X"]].round(2)
    bull = df.where(df['X'] > 0).dropna().loc[:, ["name", 'market', "beta", "sharpo", "X"]]
    bull.columns = ["Name", 'Market', "Beta", "Sharpe Ratio", "Suggest Position"]
    html += "台股投資組合推薦<br>" + bull.to_html() + "<br>"

    html += "本系統上的所有資訊僅供參考之用，並不構成財務或投資建議。在做出任何投資決定之前，我們建議您尋求獨立的財務建議。"

    #send email
    whitelist = ["markov.chen1996@gmail.com", "Kepitlo@gmail.com"]

    mime=MIMEText(html, "html", "utf-8")
    mime["Subject"]="本日投資組合及分配比例 (系統自動發送)"
    mime["From"]="QuantML System"
    mime["To"]="markov.chen1996@gmail.com"
    msg=mime.as_string()
    smtp=smtplib.SMTP("smtp.gmail.com", 587)
    smtp.ehlo()
    smtp.starttls()
    smtp.login("markov.chen1996@gmail.com", 'zwkd lwtp vkqs uafa')
    from_addr="markov.chen1996@gmail.com"
    to_addr=whitelist
    status=smtp.sendmail(from_addr, to_addr, msg)
    smtp.quit()
    print(status)
    print(html)