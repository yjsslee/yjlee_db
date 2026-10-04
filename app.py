import hashlib
import html
import os
import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from kiwoom import KiwoomClient, KiwoomError, SEOUL, number

st.set_page_config(page_title='이유진의 관심종목 대시보드', page_icon='📈', layout='wide')
STOCKS = {'삼성전자': '005930', 'SK하이닉스': '000660', '두산에너빌리티': '034020'}
SECRET_EXAMPLE = 'KIWOOM_APP_KEY = "모의투자용 App Key"\nKIWOOM_APP_SECRET = "모의투자용 App Secret"'

st.markdown('''<style>
.stApp {background:#F5F7FA;color:#263238;}
.block-container {max-width:1400px;padding-top:2.5rem;}
h1,h2,h3 {color:#17365D!important;}
.subtitle {color:#738096;margin-top:-8px;margin-bottom:22px;}
.stock-card {background:#fff;border:1px solid #E7ECF2;border-radius:14px;padding:26px;margin-bottom:18px;min-height:215px;}
.stock-name {font-size:23px;font-weight:700;color:#17365D;}
.stock-code {font-size:14px;color:#738096;margin-top:5px;}
.stock-price {font-size:36px;font-weight:750;margin:13px 0 4px;}
.stock-change {font-size:19px;font-weight:650;}
.badge {display:inline-block;background:#E7EDF5;color:#17365D;border-radius:8px;padding:6px 12px;font-size:14px;}
[data-testid="stVerticalBlockBorderWrapper"] {background:white;border-radius:14px;}
div[data-testid="stMetricValue"] {font-size:25px;}
</style>''', unsafe_allow_html=True)

def secret_value(name):
    try:
        return str(st.secrets.get(name, os.getenv(name, ''))).strip()
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.getenv(name, '').strip()

def won(value):
    return '—' if value is None else f'{value:,.0f}원'

def show_card(name, code, data=None):
    change = number(data.get('pred_pre')) if data else None
    rate = number(data.get('flu_rt')) if data else None
    sign = str(data.get('pre_sig', '')) if data else ''
    if change is not None and sign in ('4', '5'):
        change = -abs(change)
    elif change is not None and sign in ('1', '2'):
        change = abs(change)
    if rate is not None and change is not None and change != 0:
        rate = abs(rate) * (1 if change > 0 else -1)
    color = '#D9363E' if (change or 0) > 0 else '#246BCE' if (change or 0) < 0 else '#738096'
    label = '조회 전' if data is None else '등락 정보 없음'
    if change is not None and rate is not None:
        label = f'{change:+,.0f}원 ({rate:+.2f}%)'
    price = won(number(data.get('cur_prc'), True)) if data else '—'
    st.markdown(f'''<div class="stock-card"><div class="stock-name">{html.escape(name)}</div>
    <div class="stock-code">{code}</div><div class="stock-price">{price}</div>
    <div class="stock-change" style="color:{color}">{label}</div></div>''', unsafe_allow_html=True)

def render_watchlist():
    title, refresh = st.columns([5, 1])
    with title:
        st.title('이유진의 관심종목 대시보드')
        st.markdown('<div class="subtitle">관심종목의 주가 흐름을 한눈에 확인하세요</div>', unsafe_allow_html=True)
    with refresh:
        st.markdown('<div class="badge">키움 모의투자</div>', unsafe_allow_html=True)
        reload_data = st.button('↻ 새로고침', width='stretch')

    key, secret = secret_value('KIWOOM_APP_KEY'), secret_value('KIWOOM_APP_SECRET')
    if not key or not secret:
        for col, (name, code) in zip(st.columns(3), STOCKS.items()):
            with col:
                show_card(name, code)
        st.info('연결 설정이 필요합니다. Streamlit의 Settings → Secrets에 아래 두 값을 입력해 주세요.')
        st.code(SECRET_EXAMPLE, language='toml')
        st.caption('모의투자용 키를 사용하세요. 저장한 뒤 앱을 새로고침하면 실제 API 조회를 시작합니다.')
        return

    identity = hashlib.sha256((key + '\0' + secret).encode()).hexdigest()
    if st.session_state.get('identity') != identity:
        st.session_state.identity = identity
        st.session_state.client = KiwoomClient(key, secret)
        st.session_state.quotes = {}
        st.session_state.histories = {}
        st.session_state.quote_time = 0
    if reload_data:
        st.session_state.quotes = {}
        st.session_state.histories = {}
        st.session_state.quote_time = 0
        st.session_state.client.expiry = 0

    client = st.session_state.client
    errors = {}
    if time.time() - st.session_state.quote_time >= 60:
        with st.spinner('모의투자 서버에서 주가를 조회하고 있습니다…'):
            quotes = {}
            for name, code in STOCKS.items():
                try:
                    quotes[code] = client.quote(code)
                except KiwoomError as exc:
                    errors[name] = str(exc)
            st.session_state.quotes = quotes
            if quotes:
                st.session_state.quote_time = time.time()
        st.session_state.quote_errors = errors

    for col, (name, code) in zip(st.columns(3), STOCKS.items()):
        with col:
            show_card(name, code, st.session_state.quotes.get(code))
            if name in st.session_state.get('quote_errors', {}):
                st.error(st.session_state.quote_errors[name])

    if st.session_state.quotes:
        stamp = datetime.fromtimestamp(st.session_state.quote_time, SEOUL).strftime('%Y-%m-%d %H:%M:%S')
        st.caption(f'주가 조회 시각: {stamp} (한국시간) · 새로고침 버튼으로 갱신 · 휴장 중에는 최근 제공 시세가 표시됩니다.')
    else:
        st.warning('주가 연결이 완료되지 않았습니다. 아래 연결 도움말을 확인해 주세요.')

    with st.container(border=True):
        st.subheader('주가 흐름')
        left, right = st.columns([3, 2])
        with left:
            name = st.selectbox('종목 선택', list(STOCKS), label_visibility='collapsed')
        with right:
            period = st.radio('조회 기간', ['1개월', '3개월', '6개월'], index=1, horizontal=True, label_visibility='collapsed')
        code = STOCKS[name]
        months = int(period[0])
        try:
            cached = st.session_state.histories.get(code)
            if cached is None or time.time() - cached['time'] >= 300:
                with st.spinner('일봉 차트를 조회하고 있습니다…'):
                    frame = client.history(code)
                    st.session_state.histories[code] = {'time': time.time(), 'frame': frame}
            else:
                frame = cached['frame']
            cutoff = pd.Timestamp(datetime.now(SEOUL).date()) - pd.DateOffset(months=months)
            selected = frame[frame['날짜'] >= cutoff]
            if selected.empty:
                st.info('선택 기간의 일봉 데이터가 없습니다.')
            else:
                fig = go.Figure(go.Scatter(x=selected['날짜'], y=selected['종가'], mode='lines',
                    line={'color': '#17365D', 'width': 2.5},
                    hovertemplate='%{x|%Y-%m-%d}<br>종가 %{y:,.0f}원<extra></extra>'))
                fig.update_layout(height=390, margin={'l': 15, 'r': 15, 't': 20, 'b': 20},
                    paper_bgcolor='white', plot_bgcolor='white', font={'color': '#738096'},
                    xaxis={'title': None, 'gridcolor': '#EDF1F5', 'tickformat': '%m월 %d일'},
                    yaxis={'title': None, 'gridcolor': '#EDF1F5', 'ticksuffix': '원', 'tickformat': ','})
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
                st.caption(f"{name} · 수정주가 일봉 종가 · 최신 일봉 {selected['날짜'].max():%Y-%m-%d} · {len(selected)}개 거래일")
        except KiwoomError as exc:
            st.error(str(exc))
        st.divider()
        quote = st.session_state.quotes.get(code, {})
        for col, (label, field) in zip(st.columns(4), [('시가', 'open_pric'), ('고가', 'high_pric'), ('저가', 'low_pric'), ('거래량', 'trde_qty')]):
            value = number(quote.get(field), True)
            col.metric(label, ('—' if value is None else f'{value:,.0f}주') if field == 'trde_qty' else won(value))

    with st.expander('연결 도움말'):
        st.markdown('''1. **Settings → Secrets**에 `KIWOOM_APP_KEY`, `KIWOOM_APP_SECRET`이 있는지 확인하세요.
    2. 두 키 모두 **모의투자용 REST API**에서 발급한 값이어야 합니다.
    3. 키움의 API 사용신청과 모의투자 이용 상태를 확인하세요.
    4. 오류에 **IP**가 언급되면 키움에 등록한 허용 IP와 앱 서버의 발신 IP를 확인해야 합니다. 내 PC의 IP와 Streamlit 서버 IP는 다를 수 있습니다.
    5. 설정을 수정한 뒤 **새로고침**을 누르세요. 서버 점검 중이면 나중에 다시 조회해 주세요.''')
    st.caption('데이터 출처: 키움증권 REST API · 모의투자 서버의 KRX 종목 시세')



from krx_market import render_market

watch_tab, market_tab = st.tabs(["관심종목", "국내시장 요약"])
with watch_tab:
    render_watchlist()
with market_tab:
    render_market(secret_value)
