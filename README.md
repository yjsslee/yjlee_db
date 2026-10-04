# 이유진의 관심종목 대시보드

삼성전자·SK하이닉스·두산에너빌리티의 현재가와 1개월/3개월/6개월 일봉 차트를 보여주는 Streamlit 앱입니다.
키움 REST API **모의투자 서버** (`https://mockapi.kiwoom.com`)를 사용합니다.

## Streamlit Community Cloud 배포

1. https://share.streamlit.io 에 로그인합니다.
2. **Create app → Deploy a public app from GitHub**를 선택합니다.
3. Repository: `yjsslee/yjlee_db`, Branch: `main`, Main file path: `app.py`.
4. Advanced settings에서 Python 3.12를 선택하고 Secrets에 아래 형식으로 실제 값을 넣습니다.

```toml
KIWOOM_APP_KEY = "모의투자용 App Key를 입력"
KIWOOM_APP_SECRET = "모의투자용 App Secret을 입력"
```

5. Deploy를 누릅니다. 이미 배포했다면 앱 Settings → Secrets에서 설정합니다.

키나 Secret을 GitHub에 올리지 마세요. KRX API key는 이번 단계에서 사용하지 않습니다.
이 앱은 계좌번호가 필요 없는 시세 조회 앱이며 주문 기능이 없습니다.

## 연결 문제

- 실전투자 키와 모의투자 키를 혼용하지 마세요.
- 이 앱은 키움 **REST API** 키가 필요합니다. Windows OpenAPI+ 로그인 방식과 다릅니다.
- 키움은 허용 IP에서 인증하도록 안내합니다. PC IP와 Streamlit 서버 발신 IP는 다르므로
  IP 관련 오류 발생 시 키움의 계좌 App Key 관리 설정을 확인하세요.
  서버 발신 IP가 변경되는 환경에서는 고정 발신 IP를 갖는 별도 서버가 필요할 수 있습니다.
- 휴장일/점검 시간에는 최근 시세 또는 API 오류가 표시될 수 있습니다.
- API 오류를 예시 가격으로 대체하지 않습니다. 종목별 오류와 차트 오류를 따로 표시합니다.

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

로컬에서는 `.streamlit/secrets.toml`에 키를 설정합니다(커밋 금지).
시세는 세션 내 60초, 차트는 5분 동안 재사용합니다. 새로고침 버튼은 캐시를 초기화합니다.
모의투자 호출 제한을 고려해 요청 사이에 최소 1.1초 간격을 둡니다.

공식 문서: https://openapi.kiwoom.com/guide/apiguide


## 국내시장 요약 탭

Streamlit Settings → Secrets에서 기존 키움 설정을 유지하고 다음 한 줄을 추가하세요.

```toml
KRX_API_KEY = "발급받은 KRX 인증키"
```

KRX 유가증권 일별매매정보·코스닥 일별매매정보 이용승인이 필요합니다.
코스피/코스닥/전체를 선택하고 **시장 데이터 조회**를 누릅니다.
조회일에 자료가 없으면 이전 14일까지 최근 제공일을 찾습니다. 전체는 두 시장이 같은 날짜일 때만 합칩니다.
장중 실시간 자료가 아니며 실제 데이터 기준일을 표시합니다. 같은 조회는 세션 내 10분 동안 재사용합니다.
상승·하락 순위는 각각 양수·음수 등락률 종목만 대상으로 하며, 거래량·거래대금이 0인 종목은 제외합니다.
