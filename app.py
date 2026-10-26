import pandas as pd
import streamlit as st
from pathlib import Path
st.set_page_config(page_title='A股强势股筛选 V2.0',layout='wide')
st.title('A股强势股量化筛选 V2.0')
st.caption('日线候选池｜非实时交易信号｜免费数据可能延迟或失效')
path=Path('results.csv')
if not path.exists():
    st.info('尚未生成筛选结果。请先运行 python screener.py --limit 100')
else:
    df=pd.read_csv(path,dtype={'代码':str})
    threshold=st.slider('最低评分',0,100,50,5)
    if df.empty: st.warning('本次无有效结果，检查行情接口与状态文件。')
    else: st.dataframe(df[df['评分']>=threshold],hide_index=True,use_container_width=True)
    st.caption('评分仅为规则匹配度，不是收益预测；筛选股票不等于建议买入。')
