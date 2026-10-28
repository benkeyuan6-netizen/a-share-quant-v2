"""A股沪深主板强势股盘后初筛 V2.0。数据来自 AKShare。"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd


def stock_pool():
    df = ak.stock_info_a_code_name()
    if not {'code', 'name'}.issubset(df.columns):
        raise ValueError(f'股票列表字段变化: {list(df.columns)}')
    df = df[['code', 'name']].copy()
    df['code'] = df['code'].astype(str).str.zfill(6)
    df['name'] = df['name'].astype(str)
    prefix = ('000', '001', '002', '003', '600', '601', '603', '605')
    ok = df['code'].str.startswith(prefix)
    ok &= ~df['name'].str.contains(r'ST|退', case=False, regex=True)
    return df[ok].drop_duplicates('code').reset_index(drop=True)


def score_one(code, name):
    symbol = ('sh' if code.startswith('6') else 'sz') + code
    d = ak.stock_zh_a_daily(symbol=symbol, adjust='qfq')
    if d is None or len(d) < 30:
        return None, '历史数据不足'
    d = d.sort_values('date').tail(45).copy()
    for col in ('close', 'open', 'high', 'low', 'volume'):
        d[col] = pd.to_numeric(d[col], errors='coerce')
    d = d.dropna(subset=['close', 'open', 'high', 'low', 'volume'])
    if len(d) < 30:
        return None, '有效数据不足'
    c, v = d['close'], d['volume']
    price = float(c.iloc[-1])
    if not 0 < price < 50 or v.iloc[-1] <= 0:
        return None, None
    ma5, ma10, ma20 = [float(c.tail(n).mean()) for n in (5, 10, 20)]
    # 前3个交易日上涨，最近2个交易日缩量回调
    rise = d.iloc[-5:-2]
    pull = d.iloc[-2:]
    rise_gain = float(rise['close'].iloc[-1] / d['close'].iloc[-6] - 1)
    pull_gain = float(pull['close'].iloc[-1] / rise['close'].iloc[-1] - 1)
    rise_vol = float(rise['volume'].mean())
    pull_vol = float(pull['volume'].mean())
    vol_ratio = pull_vol / rise_vol if rise_vol > 0 else 999
    baseline_vol = float(d['volume'].iloc[-15:-5].mean())
    expansion = rise_vol / baseline_vol if baseline_vol > 0 else 0
    trend = ma5 > ma10 > ma20
    launch = rise_gain >= 0.03 and expansion >= 1.2
    correction = -0.06 <= pull_gain <= 0.015
    shrink = 0.25 <= vol_ratio <= 0.75
    support = price >= ma10 * 0.98
    score = 30 * trend + 25 * launch + 20 * correction + 15 * shrink + 10 * support
    return {
        '代码': code, '名称': name, '日期': str(d['date'].iloc[-1])[:10],
        '收盘价': round(price, 2), '评分': score,
        '均线多头': trend, '放量启动': launch, '温和回调': correction,
        '缩量整理': shrink, '守住支撑': support,
        '5日均线': round(ma5, 2), '10日均线': round(ma10, 2),
        '20日均线': round(ma20, 2), '启动涨幅%': round(rise_gain * 100, 2),
        '回调涨幅%': round(pull_gain * 100, 2),
        '回调量比': round(vol_ratio, 3), '启动放量倍数': round(expansion, 2),
    }, None


def run(limit, output, pause):
    pool = stock_pool()
    total = min(limit, len(pool)) if limit else len(pool)
    print(f'股票池 {len(pool)} 只，本次计划扫描 {total} 只', flush=True)
    rows, errors = [], []
    for i, row in enumerate(pool.head(total).itertuples(index=False), 1):
        code, name = row.code, row.name
        try:
            result, warning = score_one(code, name)
            if result:
                rows.append(result)
            if warning:
                errors.append({'代码': code, '问题': warning})
        except Exception as exc:
            errors.append({'代码': code, '问题': str(exc)[:240]})
        if i % 10 == 0 or i == total:
            print(f'已扫描 {i}/{total}，有效 {len(rows)}，异常 {len(errors)}', flush=True)
        if pause and i < total:
            time.sleep(pause)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = pd.DataFrame(rows)
    if not data.empty:
        data = data.sort_values(['评分', '启动放量倍数'], ascending=[False, False])
    data.to_csv(out, index=False, encoding='utf-8-sig')
    report = {'运行时间': datetime.now().isoformat(timespec='seconds'),
              '计划扫描': total, '成功读取': len(rows), '异常数': len(errors),
              '错误样本': errors[:30], '结果文件': str(out),
              '说明': '技术初筛，非交易建议；成功读取不等于数据为最新交易日'}
    out.with_suffix('.status.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n扫描状态:', json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if not data.empty:
        print('\n评分前10只（非买入推荐）:')
        print(data.head(10)[['代码', '名称', '日期', '收盘价', '评分', '均线多头', '放量启动', '缩量整理']].to_string(index=False))
    else:
        print('无有效结果，请先检查错误记录，不能解释为市场没有候选股。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=10, help='扫描数量，0表示全部')
    parser.add_argument('--output', default='results/v2_candidates.csv')
    parser.add_argument('--pause', type=float, default=0.2)
    args = parser.parse_args()
    run(args.limit, args.output, args.pause)
