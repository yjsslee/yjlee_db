"""외국인·기관 순매매 금액 순위(키움 ka90009)."""
import hashlib
import time
from datetime import datetime

import pandas as pd
import streamlit as st

from kiwoom import KiwoomClient, KiwoomError, SEOUL, number

GROUPS = [('외국인 순매수', 'for_netprps'), ('외국인 순매도', 'for_netslmt'),
          ('기관 순매수', 'orgn_netprps'), ('기관 순매도', 'orgn_netslmt')]


def parse_rankings(rows):
    tables = {}
    for title, prefix in GROUPS:
        records, seen = [], set()
        for row in rows:
            code = str(row.get(prefix + '_stk_cd') or '').strip().removeprefix('A')
            name = str(row.get(prefix + '_stk_nm') or '').strip()
            amount = number(row.get(prefix + '_amt'), True)
            if not code or not name or amount is None or amount <= 0 or code in seen:
                continue
            seen.add(code)
            # 공식 금액 단위는 천만원. 억원으로 변환합니다.
            records.append({'종목코드': code, '종목명': name, '순매매금액(억원)': amount / 10})
        tables[title] = pd.DataFrame(records, columns=['종목코드', '종목명', '순매매금액(억원)']).head(10)
    return tables


def fetch_rankings(client, choice, day):
    body = {'mrkt_tp': {'전체': '000', '코스피': '001', '코스닥': '101'}[choice],
            'amt_qty_tp': '1', 'qry_dt_tp': '1', 'stex_tp': '1', 'date': day.strftime('%Y%m%d')}
    rows, continuation, seen = [], None, set()
    for _ in range(20):
        data, headers = client.query('ka90009', '/api/dostk/rkinfo', body, continuation)
        page = data.get('frgnr_orgn_trde_upper')
        if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
            raise KiwoomError('외국인·기관 순위 응답 형식이 예상과 다릅니다.')
        rows.extend(page)
        tables = parse_rankings(rows)
        if all(len(table) == 10 for table in tables.values()) or headers.get('cont-yn') != 'Y':
            return tables
        next_key = headers.get('next-key')
        if not next_key or next_key in seen:
            raise KiwoomError('외국인·기관 순위 연속조회가 완료되지 않았습니다.')
        seen.add(next_key)
        continuation = next_key
    raise KiwoomError('외국인·기관 순위 조회 한도에 도달했습니다. 다시 조회해 주세요.')


def render_investors(secret_value, market_result):
    st.divider()
    st.subheader('외국인·기관 순매수 / 순매도')
    choice, day = market_result['choice'], market_result['day']
    st.caption(f'{choice} · 요청 기준일 {day:%Y-%m-%d} · KRX 거래소 · 순매매 금액 기준')
    key, secret = secret_value('KIWOOM_APP_KEY'), secret_value('KIWOOM_APP_SECRET')
    if not key or not secret:
        st.info('외국인·기관 순위는 기존 키움 모의투자 API key와 secret이 필요합니다.')
        return
    identity = hashlib.sha256((key + '\0' + secret).encode()).hexdigest()
    cache_key = (identity, choice, day.isoformat())
    cached = st.session_state.get('investor_result')
    if cached and cached['key'] != cache_key:
        st.session_state.pop('investor_result', None)
        cached = None
    if st.button('외국인·기관 순위 조회 / 새로고침', key='investor_refresh'):
        try:
            with st.spinner('키움에서 외국인·기관 순매매 순위를 조회하고 있습니다…'):
                client = st.session_state.get('client') if st.session_state.get('identity') == identity else None
                client = client or KiwoomClient(key, secret)
                tables = fetch_rankings(client, choice, day)
                cached = {'key': cache_key, 'tables': tables, 'time': time.time()}
                st.session_state.investor_result = cached
        except KiwoomError as exc:
            st.session_state.pop('investor_result', None)
            cached = None
            st.error(str(exc))
            st.info('모의투자 서버에서 이 조회를 지원하지 않거나 이용이 제한될 수 있습니다. 실전투자 키로 자동 전환하지 않습니다.')
    if cached is None:
        st.caption('위 버튼을 누르면 외국인·기관의 순매수·순매도 순위를 불러옵니다.')
        return
    frame = market_result['frame']
    # 가격은 같은 기준일 KRX 자료와 종목명으로 정확히 연결합니다.
    prices = frame[['종목명', '종가', '등락률']]
    prices = prices[~prices['종목명'].duplicated(keep=False)]
    for start in (0, 2):
        for col, (title, _) in zip(st.columns(2), GROUPS[start:start + 2]):
            with col:
                st.markdown(f'#### {title} 상위 10종목')
                table = cached['tables'][title]
                if table.empty:
                    st.info('해당 기준일의 순위 데이터가 없습니다.')
                    continue
                display = table.merge(prices, how='left', on='종목명', sort=False)
                display['종가(기준일)'] = display['종가'].map(lambda x: '—' if pd.isna(x) else f'{x:,.0f}원')
                display['등락률'] = display['등락률'].map(lambda x: '—' if pd.isna(x) else f'{x:+.2f}%')
                amount_label = '순매수금액(억원)' if '순매수' in title else '순매도금액(억원)'
                display[amount_label] = display['순매매금액(억원)'].map(lambda x: f'{x:,.2f}')
                display = display[['종목명', '종가(기준일)', '등락률', amount_label]]
                display.index = range(1, len(display) + 1)
                st.dataframe(display, width='stretch', height=390)
    stamp = datetime.fromtimestamp(cached['time'], SEOUL).strftime('%Y-%m-%d %H:%M:%S')
    st.caption(f'순위 출처: 키움 ka90009 · 조회 시각 {stamp} (한국시간). 순매도금액은 매도 우위의 크기를 양수로 표시합니다. 가격과 등락률은 같은 요청 기준일의 KRX 자료이며, 연결되지 않은 종목은 —로 표시합니다.')
