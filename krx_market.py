"""KRX 일별매매정보 조회와 국내시장 요약 화면."""
from datetime import datetime, timedelta
import hashlib
import time

import pandas as pd
import requests
import streamlit as st

from kiwoom import SEOUL

ENDPOINTS = {'코스피': 'stk_bydd_trd', '코스닥': 'ksq_bydd_trd'}
BASE = 'https://data-dbg.krx.co.kr/svc/apis/sto/'
COLUMNS = {'ISU_CD': '종목코드', 'ISU_NM': '종목명', 'MKT_NM': '시장',
           'TDD_CLSPRC': '종가', 'FLUC_RT': '등락률', 'ACC_TRDVAL': '거래대금',
           'ACC_TRDVOL': '거래량'}


class KrxError(RuntimeError):
    pass


def parse_rows(rows, day, market):
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    required = {'ISU_CD', 'ISU_NM', 'TDD_CLSPRC', 'FLUC_RT', 'ACC_TRDVAL', 'ACC_TRDVOL', 'BAS_DD'}
    if not required.issubset(frame.columns):
        raise KrxError('KRX 응답에 필요한 종목·가격·기준일 필드가 없습니다.')
    dates = frame['BAS_DD'].astype(str).str.replace(r'[^0-9]', '', regex=True)
    if not dates.eq(day.strftime('%Y%m%d')).all():
        raise KrxError('KRX 응답 기준일이 요청 날짜와 다릅니다. 다시 조회해 주세요.')
    frame = frame.rename(columns=COLUMNS)
    if '시장' not in frame:
        frame['시장'] = market
    for column in ['종가', '등락률', '거래대금', '거래량']:
        cleaned = frame[column].astype(str).str.replace(',', '', regex=False).str.replace('%', '', regex=False).str.strip()
        frame[column] = pd.to_numeric(cleaned, errors='coerce')
    # 거래가 없거나 숫자가 없는 종목은 순위 산정에서 제외합니다.
    frame = frame.dropna(subset=['종가', '등락률', '거래대금', '거래량'])
    return frame[(frame['종가'] > 0) & (frame['거래량'] > 0) & (frame['거래대금'] > 0)][list(COLUMNS.values())]


def fetch_day(key, market, day):
    try:
        response = requests.get(BASE + ENDPOINTS[market],
            headers={'AUTH_KEY': key, 'Accept': 'application/json'},
            params={'basDd': day.strftime('%Y%m%d')}, timeout=(10, 25))
    except requests.RequestException:
        raise KrxError(f'{market}: KRX 서버에 연결하지 못했습니다. 잠시 후 다시 조회해 주세요.') from None
    if response.status_code in (401, 403):
        raise KrxError(f'{market}: KRX 인증 또는 API 이용 권한 오류입니다(HTTP {response.status_code}). 인증키와 해당 일별매매정보의 이용승인을 확인해 주세요.')
    if response.status_code == 429:
        raise KrxError('KRX 호출 한도에 도달했습니다. 잠시 후 다시 조회해 주세요.')
    if not response.ok:
        raise KrxError(f'{market}: KRX 서버 오류입니다(HTTP {response.status_code}).')
    try:
        data = response.json()
    except ValueError:
        raise KrxError(f'{market}: KRX가 JSON 데이터를 반환하지 않았습니다. 인증키·서비스 이용승인 또는 서버 상태를 확인해 주세요.') from None
    if not isinstance(data, dict) or not isinstance(data.get('OutBlock_1'), list):
        raise KrxError(f'{market}: KRX 응답에 일별매매정보가 없습니다. 인증키와 해당 서비스 이용승인을 확인해 주세요.')
    return parse_rows(data['OutBlock_1'], day, market)


def latest_market(key, choice, requested):
    markets = list(ENDPOINTS) if choice == '전체' else [choice]
    # 두 시장을 함께 조회할 때에는 동일 기준일 데이터만 합칩니다.
    for offset in range(15):
        day = requested - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        frames = []
        for market in markets:
            frame = fetch_day(key, market, day)
            if frame.empty:
                break
            frames.append(frame)
            if len(markets) > 1:
                time.sleep(0.2)
        if len(frames) == len(markets):
            return day, pd.concat(frames, ignore_index=True).drop_duplicates(['시장', '종목코드'])
    raise KrxError('선택일과 이전 14일에 순위를 계산할 수 있는 데이터가 없습니다. 날짜 또는 KRX 서비스 이용 상태를 확인해 주세요.')


def rankings(frame):
    rises = frame[frame['등락률'] > 0].sort_values(['등락률', '거래대금', '종목코드'], ascending=[False, False, True]).head(10)
    falls = frame[frame['등락률'] < 0].sort_values(['등락률', '거래대금', '종목코드'], ascending=[True, False, True]).head(10)
    traded = frame.sort_values(['거래대금', '종목코드'], ascending=[False, True]).head(10)
    return rises, falls, traded


def render_market(secret_value):
    st.title('국내시장 요약')
    st.caption('KRX 일별매매정보로 살펴보는 종목 순위 · 장중 실시간 자료가 아닌 일별 데이터입니다.')
    key = secret_value('KRX_API_KEY') or secret_value('KRX_AUTH_KEY')
    if not key:
        st.info('기존 키움 Secrets 아래에 KRX 인증키를 한 줄 추가해 주세요.')
        st.code('KRX_API_KEY = "발급받은 KRX 인증키"', language='toml')
        st.caption('키움 설정 두 줄은 유지하세요. KRX의 유가증권·코스닥 일별매매정보 이용승인이 필요합니다.')
        return
    with st.form('krx_query'):
        market_col, date_col = st.columns(2)
        choice = market_col.selectbox('시장', ['코스피', '코스닥', '전체'])
        requested = date_col.date_input('조회 기준일', value=datetime.now(SEOUL).date() - timedelta(days=1),
            min_value=datetime(2010, 1, 4).date(), max_value=datetime.now(SEOUL).date())
        submitted = st.form_submit_button('시장 데이터 조회', type='primary')
    identity = hashlib.sha256(key.encode()).hexdigest()
    if st.session_state.get('krx_identity') != identity:
        st.session_state.krx_identity = identity
        st.session_state.pop('krx_result', None)
        st.session_state.krx_cache = {}
    if submitted:
        cache_key = (choice, requested.isoformat())
        cached = st.session_state.krx_cache.get(cache_key)
        try:
            with st.spinner('KRX에서 최근 제공일의 시장 데이터를 조회하고 있습니다…'):
                if cached and time.time() - cached['time'] < 600:
                    result = cached
                else:
                    day, frame = latest_market(key, choice, requested)
                    result = {'day': day, 'frame': frame, 'choice': choice, 'requested': requested, 'time': time.time()}
                    st.session_state.krx_cache[cache_key] = result
                st.session_state.krx_result = result
        except KrxError as exc:
            st.session_state.pop('krx_result', None)
            st.error(str(exc))
    result = st.session_state.get('krx_result')
    if not result:
        st.info('시장을 선택하고 ‘시장 데이터 조회’를 누르면 순위가 표시됩니다.')
    else:
        day, frame = result['day'], result['frame']
        st.markdown(f"**{result['choice']} · 데이터 기준일: {day:%Y-%m-%d}**")
        if day != result['requested']:
            st.caption(f"요청일 {result['requested']:%Y-%m-%d}에 데이터가 없어 이전 제공일을 표시합니다.")
        summary = st.columns(4)
        summary[0].metric('거래 종목', f'{len(frame):,}개')
        summary[1].metric('상승 종목', f"{(frame['등락률'] > 0).sum():,}개")
        summary[2].metric('하락 종목', f"{(frame['등락률'] < 0).sum():,}개")
        summary[3].metric('거래대금 합계', f"{frame['거래대금'].sum() / 1e12:,.2f}조원")
        for container, title, table in zip(st.columns(3), ['상승률 상위 10종목', '하락률 상위 10종목', '거래대금 상위 10종목'], rankings(frame)):
            with container:
                st.subheader(title)
                if table.empty:
                    st.info('해당하는 종목이 없습니다.')
                    continue
                display = table[['종목명', '시장', '종가', '등락률']].copy()
                display['종가'] = display['종가'].map(lambda x: f'{x:,.0f}원')
                display['등락률'] = display['등락률'].map(lambda x: f'{x:+.2f}%')
                display['거래대금(억원)'] = table['거래대금'].map(lambda x: f'{x / 1e8:,.1f}')
                display.index = range(1, len(display) + 1)
                st.dataframe(display, width='stretch', height=390)
        st.caption('거래량·거래대금이 0이거나 필수 숫자가 없는 종목은 제외합니다. 거래대금 단위: 억원. 전체 조회는 두 시장의 동일 기준일을 사용합니다.')
    with st.expander('KRX 연결 도움말'):
        st.markdown('''- Secrets 변수 이름은 **KRX_API_KEY**입니다(`KRX_AUTH_KEY`도 지원).
- KRX **유가증권 일별매매정보**와 **코스닥 일별매매정보**의 이용승인을 확인하세요.
- 코스피만 승인되었다면 시장을 **코스피**로 선택하세요.
- 인증·이용권한 오류와 데이터가 없는 날짜는 구분해서 안내합니다.
- 입력한 날짜에 데이터가 없으면 이전 14일까지 확인합니다.''')

