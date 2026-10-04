"""모의투자 보유종목 화면. 계좌 자료는 세션에만 보관합니다."""
import hashlib
import hmac
import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from kiwoom import KiwoomClient, KiwoomError, SEOUL, number

PALETTE = ['#B6CCBF', '#C8C1DD', '#E7C6B3', '#B8CDD9', '#D8CFB2', '#D8BCCB', '#BFCFC8', '#CED6E3']


def normalize_holdings(rows):
    records = []
    for row in rows:
        quantity = number(row.get('rmnd_qty'))
        if quantity is None:
            raise KiwoomError('보유수량이 없는 종목이 있습니다. 다시 조회해 주세요.')
        if quantity <= 0:
            continue
        cost, value, pnl = (number(row.get(key)) for key in ('pur_amt', 'evlt_amt', 'evltv_prft'))
        records.append({'종목코드': str(row.get('stk_cd', '')).removeprefix('A'),
            '종목명': str(row.get('stk_nm', '이름 없음')), '보유수량': quantity,
            '매입가': number(row.get('pur_pric'), True), '현재가': number(row.get('cur_prc'), True),
            '매입금액': cost, '평가금액': value, '평가손익': pnl,
            '수익률(%)': pnl / cost * 100 if pnl is not None and cost and cost > 0 else None})
    return pd.DataFrame(records, columns=['종목코드', '종목명', '보유수량', '매입가', '현재가', '매입금액', '평가금액', '평가손익', '수익률(%)'])


def fmt(value, suffix='원', signed=False):
    if value is None or pd.isna(value):
        return '—'
    return (f'{value:+,.0f}' if signed else f'{value:,.0f}') + suffix


def render_holdings(secret_value):
    st.title('내 보유종목')
    st.caption('키움 모의투자 계좌 · 보유종목의 평가금액과 수익률을 확인하세요.')
    password = secret_value('HOLDINGS_PASSWORD')
    if not password:
        st.info('보유종목을 보호할 비밀번호를 Streamlit Secrets에 추가해 주세요.')
        st.code('HOLDINGS_PASSWORD = "직접 정한 긴 비밀번호"', language='toml')
        return
    password_id = hashlib.sha256(password.encode()).hexdigest()
    if st.session_state.get('holdings_password_id') != password_id:
        st.session_state.holdings_password_id = password_id
        st.session_state.holdings_unlocked = False
        st.session_state.pop('holdings_result', None)
    if not st.session_state.get('holdings_unlocked'):
        with st.form('holdings_unlock', clear_on_submit=True):
            entered = st.text_input('보유종목 조회 비밀번호', type='password')
            unlock = st.form_submit_button('잠금 해제', type='primary')
        if unlock:
            if time.time() < st.session_state.get('holdings_retry_after', 0):
                st.error('잠시 후 다시 시도해 주세요.')
            elif hmac.compare_digest(entered.encode(), password.encode()):
                st.session_state.holdings_unlocked = True
                st.rerun()
            else:
                st.session_state.holdings_retry_after = time.time() + 3
                st.error('비밀번호가 일치하지 않습니다.')
        return
    toolbar, lock_col = st.columns([4, 1])
    query = toolbar.button('보유종목 조회 / 새로고침', type='primary')
    if lock_col.button('다시 잠그기', width='stretch'):
        st.session_state.holdings_unlocked = False
        st.session_state.pop('holdings_result', None)
        st.rerun()
    key, secret = secret_value('KIWOOM_APP_KEY'), secret_value('KIWOOM_APP_SECRET')
    if not key or not secret:
        st.session_state.pop('holdings_result', None)
        st.info('기존 모의투자용 KIWOOM_APP_KEY와 KIWOOM_APP_SECRET을 설정해 주세요.')
        return
    identity = hashlib.sha256((key + '\0' + secret).encode()).hexdigest()
    if st.session_state.get('holdings_key_id') != identity:
        st.session_state.holdings_key_id = identity
        st.session_state.pop('holdings_result', None)
    if query:
        try:
            with st.spinner('모의투자 보유종목을 조회하고 있습니다…'):
                client = st.session_state.get('client') if st.session_state.get('identity') == identity else None
                client = client or KiwoomClient(key, secret)
                summary, rows = client.holdings()
                frame = normalize_holdings(rows)
                st.session_state.holdings_result = {'summary': summary, 'frame': frame, 'time': time.time()}
        except KiwoomError as exc:
            st.session_state.pop('holdings_result', None)
            st.error(str(exc))
    result = st.session_state.get('holdings_result')
    if result is None:
        st.info('‘보유종목 조회 / 새로고침’을 눌러 계좌 데이터를 불러오세요.')
        return
    summary, frame = result['summary'], result['frame']
    stamp = datetime.fromtimestamp(result['time'], SEOUL).strftime('%Y-%m-%d %H:%M:%S')
    st.caption(f'조회 시각: {stamp} (한국시간) · 버튼을 눌러 갱신')
    cost, value, pnl = (number(summary.get(key)) for key in ('tot_pur_amt', 'tot_evlt_amt', 'tot_evlt_pl'))
    rate = pnl / cost * 100 if pnl is not None and cost and cost > 0 else None
    for column, title, text in zip(st.columns(4), ['총매입금액', '총평가금액', '총평가손익', '총수익률'],
            [fmt(cost), fmt(value), fmt(pnl, signed=True), '—' if rate is None else f'{rate:+.2f}%']):
        with column:
            with st.container(border=True):
                st.metric(title, text)
    if frame.empty:
        st.info('현재 모의투자 계좌에 보유 중인 종목이 없습니다.')
        return
    st.subheader('종목별 보유 현황')
    display = frame.copy()
    for name in ['매입가', '현재가', '매입금액', '평가금액', '평가손익']:
        display[name] = display[name].map(lambda v: fmt(v, signed=name == '평가손익'))
    display['수익률(%)'] = display['수익률(%)'].map(lambda v: '—' if pd.isna(v) else f'{v:+.2f}%')
    display['보유수량'] = display['보유수량'].map(lambda v: fmt(v, '주'))
    st.dataframe(display, hide_index=True, width='stretch')
    left, right = st.columns(2)
    with left:
        st.subheader('보유종목 비중')
        weighted = frame.dropna(subset=['평가금액']).query('평가금액 > 0').groupby('종목명', as_index=False)['평가금액'].sum()
        if frame['평가금액'].notna().all() and frame['평가금액'].gt(0).all() and not weighted.empty:
            fig = go.Figure(go.Pie(labels=weighted['종목명'], values=weighted['평가금액'], hole=0.65,
                marker={'colors': PALETTE}, textinfo='label+percent',
                hovertemplate='%{label}<br>%{value:,.0f}원 · %{percent}<extra></extra>'))
            fig.update_layout(height=350, margin={'l': 15, 'r': 15, 't': 25, 'b': 25},
                paper_bgcolor='#FFFEFC', font={'color': '#4B5752'}, showlegend=False)
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        else:
            st.info('평가금액이 없는 종목이 있어 비중 차트를 표시할 수 없습니다.')
    with right:
        st.subheader('종목별 수익률')
        returns = frame.dropna(subset=['수익률(%)']).sort_values('수익률(%)')
        if not returns.empty:
            fig = go.Figure(go.Bar(x=returns['수익률(%)'], y=returns['종목명'], orientation='h',
                marker_color=['#BB8585' if v >= 0 else '#829BB7' for v in returns['수익률(%)']],
                hovertemplate='%{y}<br>%{x:+.2f}%<extra></extra>'))
            fig.update_layout(height=max(350, len(returns) * 28), margin={'l': 15, 'r': 15, 't': 25, 'b': 25},
                paper_bgcolor='#FFFEFC', plot_bgcolor='#FFFEFC', font={'color': '#4B5752'},
                xaxis={'ticksuffix': '%', 'gridcolor': '#ECEEE9'})
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        else:
            st.info('수익률을 계산할 매입금액과 평가손익이 없습니다.')
    st.caption('수익률 = API 평가손익 ÷ 매입금액 × 100. 비중은 보유주식 평가금액 기준이며 예수금은 포함하지 않습니다.')
