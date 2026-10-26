"""A股日线量价初筛：公开行情源可能限流或改变字段。"""
import argparse
import json
from pathlib import Path
import pandas as pd
import akshare as ak


def eligible(code, name, price):
    code, name = str(code).zfill(6), str(name).upper()
    return (code.startswith(('600','601','603','605','000','001','002','003'))
            and 'ST' not in name and '退' not in name and pd.notna(price) and 0 < float(price) < 50)


def score_stock(df):
    d = df.copy().sort_values('日期')
    for c in ['收盘','成交量','最高','最低']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.dropna(subset=['收盘','成交量'])
    if len(d) < 25:
        return None
    close = d['收盘']; vol = d['成交量']
    ma5, ma10, ma20 = (close.rolling(n).mean().iloc[-1] for n in (5,10,20))
    # 最近两天回调，之前三天上涨：缩量是候选信号，不代表主力吸筹。
    rise = d.iloc[-5:-2]; pull = d.iloc[-2:]
    rise_returns = rise['收盘'].pct_change().dropna()
    pull_returns = pull['收盘'].pct_change().dropna()
    rise_vol = rise['成交量'].mean(); pull_vol = pull['成交量'].mean()
    ratio = float(pull_vol/rise_vol) if rise_vol > 0 else 99
    trend = bool(ma5 > ma10 > ma20)
    rising = bool(len(rise_returns)==2 and (rise_returns > 0).all() and rise['收盘'].iloc[-1] > d['收盘'].iloc[-6])
    correcting = bool(close.iloc[-1] <= rise['收盘'].iloc[-1] and close.iloc[-1] >= ma10)
    shrink = bool(0 < ratio <= 0.67)
    score = 30*trend + 25*rising + 25*shrink + 20*correcting
    return {'日期':str(d['日期'].iloc[-1]),'收盘':round(float(close.iloc[-1]),2),
            '均线多头':trend,'前段上涨':rising,'缩量回调':shrink,'守住十日线':correcting,
            '回调量比':round(ratio,3),'评分':score}


def run(limit=100, output='results.csv'):
    spot = ak.stock_zh_a_spot_em()
    spot['最新价'] = pd.to_numeric(spot['最新价'],errors='coerce')
    universe = spot[spot.apply(lambda r:eligible(r['代码'],r['名称'],r['最新价']),axis=1)]
    results=[]; errors=[]
    for _,r in universe.head(limit).iterrows():
        code=str(r['代码']).zfill(6)
        try:
            df=ak.stock_zh_a_hist(symbol=code,period='daily',adjust='qfq')
            s=score_stock(df)
            if s: results.append({'代码':code,'名称':r['名称'],**s})
        except Exception as exc:
            errors.append({'代码':code,'错误':str(exc)[:120]})
    out=pd.DataFrame(results)
    if not out.empty: out=out.sort_values(['评分','回调量比'],ascending=[False,True])
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    out.to_csv(output,index=False,encoding='utf-8-sig')
    Path(output+'.status.json').write_text(json.dumps({'扫描数':len(universe.head(limit)),'成功数':len(results),'失败数':len(errors),'失败样例':errors[:10]},ensure_ascii=False,indent=2),encoding='utf-8')
    return out

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=100,help='扫描前N只；0为全市场')
    parser.add_argument('--output',default='results.csv')
    a=parser.parse_args()
    print(run(limit=a.limit if a.limit>0 else 99999,output=a.output).head(20).to_string(index=False))
