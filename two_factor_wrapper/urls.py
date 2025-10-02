from two_factor.urls import urlpatterns as two_factor_raw_urls

# 1. two_factor.urls (패턴 리스트/튜플, '네임스페이스') 튜플인지 확인, 패턴만 추출.
if isinstance(two_factor_raw_urls, tuple):
    # 튜플의 첫 번째 요소([0])가 실제 URL 패턴들을 포함..
    # 두 번째 요소('two_factor')는 제거.
    raw_patterns = two_factor_raw_urls[0]
else:
    # 튜플이 아니라 이미 표준 리스트 형태라면 그대로 사용.
    raw_patterns = two_factor_raw_urls

# 2. 네임스페이스를 명시적으로 정의. (패키지 내부 로직과의 호환성)
app_name = "two_factor"

# 3. 추출된 패턴을 최종 urlpatterns로 설정합. (list()로 확실히 변환)
urlpatterns = list(raw_patterns)
