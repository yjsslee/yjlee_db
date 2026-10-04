"""키움 REST API 모의투자 시세 조회 전용 클라이언트."""
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

SEOUL = ZoneInfo('Asia/Seoul')
BASE_URL = 'https://mockapi.kiwoom.com'


class KiwoomError(RuntimeError):
    pass


def number(value, absolute=False):
    text = str(value or '').strip().replace(',', '').replace('%', '')
    if not text:
        return None
    try:
        result = float(text)
    except (TypeError, ValueError):
        return None
    return abs(result) if absolute else result


class KiwoomClient:
    def __init__(self, app_key, secret):
        self.app_key = app_key
        self.secret = secret
        self.token = None
        self.expiry = 0
        self.last_call = 0
        self.session = requests.Session()

    def _send(self, path, body, headers=None):
        # 모의투자 조회 간격을 넉넉하게 유지합니다.
        time.sleep(max(0, 1.1 - (time.monotonic() - self.last_call)))
        self.last_call = time.monotonic()
        try:
            response = self.session.post(BASE_URL + path, json=body,
                headers={'Content-Type': 'application/json;charset=UTF-8', **(headers or {})},
                timeout=(10, 30))
        except requests.RequestException:
            raise KiwoomError('키움 서버에 연결하지 못했습니다. 잠시 후 새로고침해 주세요.') from None
        try:
            data = response.json()
        except ValueError:
            raise KiwoomError(f'키움 서버 응답을 읽을 수 없습니다. HTTP {response.status_code}') from None
        if not isinstance(data, dict):
            raise KiwoomError('키움 서버의 응답 형식이 예상과 다릅니다.')
        if not response.ok or str(data.get('return_code', 0)) != '0':
            message = str(data.get('return_msg', '조회 실패'))
            for private in (self.app_key, self.secret, self.token):
                if private:
                    message = message.replace(private, '[비공개]')
            raise KiwoomError(f"키움 오류 {data.get('return_code', response.status_code)}: {message[:400]}")
        return data, response.headers

    def authenticate(self):
        if self.token and time.time() < self.expiry:
            return
        data, _ = self._send('/oauth2/token', {
            'grant_type': 'client_credentials', 'appkey': self.app_key, 'secretkey': self.secret})
        if not data.get('token'):
            raise KiwoomError('접근토큰이 없습니다. 모의투자용 App Key와 Secret을 확인해 주세요.')
        self.token = data['token']
        try:
            self.expiry = datetime.strptime(data['expires_dt'], '%Y%m%d%H%M%S').replace(tzinfo=SEOUL).timestamp() - 60
        except (KeyError, ValueError):
            self.expiry = time.time() + 1800

    def query(self, api_id, path, body, continuation=None):
        self.authenticate()
        headers = {'api-id': api_id, 'authorization': 'Bearer ' + self.token}
        if continuation:
            headers.update({'cont-yn': 'Y', 'next-key': continuation})
        return self._send(path, body, headers)

    def quote(self, code):
        data, _ = self.query('ka10001', '/api/dostk/stkinfo', {'stk_cd': code})
        if not number(data.get('cur_prc'), True):
            raise KiwoomError('현재가 데이터가 없습니다. 모의투자 조회 지원 여부와 종목코드를 확인해 주세요.')
        return data

    def history(self, code, months=6):
        today = datetime.now(SEOUL)
        cutoff = pd.Timestamp(today.date()) - pd.DateOffset(months=months)
        body = {'stk_cd': code, 'base_dt': today.strftime('%Y%m%d'), 'upd_stkpc_tp': '1'}
        rows, continuation, seen = [], None, set()
        for _ in range(10):
            data, headers = self.query('ka10081', '/api/dostk/chart', body, continuation)
            page = data.get('stk_dt_pole_chart_qry', [])
            if not isinstance(page, list):
                raise KiwoomError('일봉 차트 응답 형식이 예상과 다릅니다.')
            rows.extend(page)
            dates = pd.to_datetime([row.get('dt') for row in page], format='%Y%m%d', errors='coerce')
            if len(dates) and dates.min() <= cutoff:
                break
            next_key = headers.get('next-key')
            if headers.get('cont-yn') != 'Y' or not next_key or not page:
                break
            if next_key in seen:
                raise KiwoomError('차트 연속조회가 반복되었습니다. 다시 조회해 주세요.')
            seen.add(next_key)
            continuation = next_key
        else:
            raise KiwoomError('차트 조회 한도에 도달했습니다. 잠시 후 다시 조회해 주세요.')
        if not rows:
            raise KiwoomError('일봉 차트 데이터가 없습니다. 모의투자에서 차트 조회가 가능한지 확인해 주세요.')
        frame = pd.DataFrame(rows)
        if not {'dt', 'cur_prc'}.issubset(frame.columns):
            raise KiwoomError('일봉 응답에 날짜 또는 종가가 없습니다.')
        frame['날짜'] = pd.to_datetime(frame['dt'], format='%Y%m%d', errors='coerce')
        frame['종가'] = frame['cur_prc'].map(lambda v: number(v, True))
        frame = frame.dropna(subset=['날짜', '종가'])
        frame = frame[frame['종가'] > 0].drop_duplicates('날짜').sort_values('날짜')
        frame = frame[frame['날짜'] >= cutoff]
        if frame.empty:
            raise KiwoomError('선택 기간에 유효한 차트 데이터가 없습니다.')
        return frame[['날짜', '종가']].reset_index(drop=True)
