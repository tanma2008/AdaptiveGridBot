import okx.MarketData as MarketData
import pandas as pd
from datetime import datetime, timedelta, timezone

FLAG='1'
market=MarketData.MarketAPI(flag=FLAG, debug=False)

def fetch(bar, hours, out):
    rows=[]; after=''
    target=datetime.now(timezone.utc)-timedelta(hours=hours)
    while True:
        r=market.get_history_candlesticks(instId='ETH-USDT', after=after, bar=bar, limit='300')
        if r.get('code')!='0': raise RuntimeError(r)
        data=r.get('data',[])
        if not data: break
        rows.extend(data)
        oldest=int(data[-1][0])
        if datetime.fromtimestamp(oldest/1000,timezone.utc)<=target: break
        after=str(oldest)
        if len(data)<300: break
    cols=['timestamp','open','high','low','close','volume','volCcy','volCcyQuote','confirm']
    df=pd.DataFrame(rows,columns=cols).drop_duplicates('timestamp')
    df['timestamp']=pd.to_datetime(pd.to_numeric(df['timestamp']),unit='ms',utc=True)
    for c in ['open','high','low','close','volume','volCcy','volCcyQuote']: df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.sort_values('timestamp').reset_index(drop=True)
    df=df[df['timestamp']>=pd.Timestamp(target)]
    df.to_csv(out,index=False)
    print(out,len(df),df.timestamp.min(),df.timestamp.max())

fetch('1H',24*190,'eth_usdt_1h_v049_6m.csv')
fetch('1D',24*190,'eth_usdt_1d_v049_6m.csv')
