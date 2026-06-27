-- 포터블(ANSI) 벤치마크 스키마 — PostgreSQL / Altibase 공통 (pgbench / TPC-B 류)
-- 방언 의존 회피: SERIAL/IDENTITY 미사용(적재 시 id 명시), 날짜함수 대신 epoch(BIGINT).
--
-- 스케일 정의 (SF = scale factor):
--   bench_branch  : SF        rows
--   bench_teller  : SF * 10   rows
--   bench_account : SF * 100000 rows   <- 데이터 규모의 주 동인
--   bench_history : 적재 0, 부하 중 INSERT 로 증가
-- 예) SF=100 -> account 1천만행 (대략 수 GB). 메모리-이내/초과 시나리오는 SF 로 조절.
--
-- 주의(확인 필요): Altibase 타입/구문 호환은 실제 서버에서 검증할 것.
--   - CHAR/VARCHAR/INTEGER/BIGINT/PRIMARY KEY/INDEX 는 양쪽 공통으로 간주.
--   - 대상은 전용 벤치마크 DB/스키마에 생성(운영 sgicpoc 직접 사용 금지 권장).

CREATE TABLE bench_branch (
  bid      INTEGER  NOT NULL PRIMARY KEY,
  bbalance INTEGER,
  filler   CHAR(88)
);

CREATE TABLE bench_teller (
  tid      INTEGER  NOT NULL PRIMARY KEY,
  bid      INTEGER,
  tbalance INTEGER,
  filler   CHAR(84)
);

CREATE TABLE bench_account (
  aid      INTEGER  NOT NULL PRIMARY KEY,
  bid      INTEGER,
  abalance INTEGER,
  filler   CHAR(84)
);

CREATE TABLE bench_history (
  hid    BIGINT,
  tid    INTEGER,
  bid    INTEGER,
  aid    INTEGER,
  delta  INTEGER,
  mtime  BIGINT,       -- epoch millis (JMeter __time()), 날짜함수 방언 회피
  filler CHAR(22)
);

-- 범위 스캔 / 조인 테스트용 보조 인덱스
CREATE INDEX idx_bench_account_bid ON bench_account (bid);
