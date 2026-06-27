# JDBC 드라이버 드롭 위치

이 디렉터리에 둔 `*.jar` 는 JMeter 이미지 빌드 시 `${JMETER_HOME}/lib/` 로 복사된다.

## Altibase JDBC 드라이버
- Altibase 설치본의 `lib/Altibase.jar` (또는 배포된 JDBC 드라이버 jar)를 이 디렉터리에 복사한 뒤 이미지를 빌드한다.
- **버전을 Altibase 서버 버전과 맞출 것.** (드라이버 클래스명·JDBC URL 형식·포트는 버전에 따라 다름 — 추정 금지, 실물 확인)
- 이 jar 는 라이선스/배포 제약 가능성이 있어 git 에 커밋하지 않는다 (`.gitignore` 처리됨).

## PostgreSQL JDBC 드라이버
- 별도로 둘 필요 없음. Dockerfile 이 Maven Central 에서 버전 고정(`PG_JDBC_VERSION`)으로 자동 다운로드한다.
