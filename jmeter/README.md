# JMeter 부하 테스트 계획 (PostgreSQL vs Altibase 공통)

5개 테스트 유형별 JMeter 테스트 계획. **동일한 plan을 프로퍼티만 바꿔 양쪽 DB에 구동**한다.

## 파일
| 파일 | 유형 | 내용 |
|---|---|---|
| `plans/01-read-only.jmx` | Read-only | 포인트 조회 / 범위 스캔 / 조인 |
| `plans/02-write-heavy.jmx` | Write-heavy | UPDATE(account) + INSERT(history) |
| `plans/03-mixed-oltp.jmx` | Mixed OLTP | TPC-B 류 믹스(account/teller/branch UPDATE + history INSERT + SELECT) |
| `plans/04-high-concurrency.jmx` | 고동시성 확장성 | select+update 단위를 thread 단계 증가로 측정 |
| `plans/05-large-workload.jmx` | 대용량 | 풀스캔/집계/조인(OLAP) + 대량 배치 UPDATE |
| `sql/schema.sql` | 스키마 | 포터블 DDL (pgbench/TPC-B 류) |

## 스키마 / 데이터셋
- 테이블: `bench_branch`, `bench_teller`, `bench_account`, `bench_history` (ANSI 포터블, `sql/schema.sql`).
- 스케일: `bench_account = SF * 100000` 행 (SF=scale factor). teller=SF*10, branch=SF.
- **양쪽 DB에 동일 데이터로 적재**한다. Altibase는 인메모리 성격이 강하므로 **메모리-이내/초과** 두 SF로 측정([README 비교 공정성](../README.md)).
- 적재는 별도 단계(로더). 운영 `sgicpoc`가 아닌 **전용 벤치마크 DB/스키마** 사용 권장.

## 실행 (CLI, 자격증명은 프로퍼티로 주입 — 파일에 미포함)
```sh
jmeter -n -t plans/01-read-only.jmx \
  -Jdb.driver=org.postgresql.Driver \
  -Jdb.url='jdbc:postgresql://<host>:5521/<db>?sslmode=disable' \
  -Jdb.user='<user>' -Jdb.password='<pw>' \
  -Jthreads=20 -Jrampup=10 -Jduration=120 -Jaccounts=10000000 \
  -l results/01-pg.jtl -e -o results/01-pg-report
```
Altibase는 `db.driver`/`db.url`/`db.checkQuery`만 교체(아래). 그 외 옵션 동일.

### 프로퍼티
| 프로퍼티 | 기본값 | 설명 |
|---|---|---|
| `db.driver` | (필수) | JDBC 드라이버 클래스 |
| `db.url` | (필수) | JDBC URL |
| `db.user` / `db.password` | (필수) | 접속 계정/비밀번호 (K8s Secret/env 로 주입) |
| `db.pool` | 50(04=256,05=16) | 커넥션 풀 최대 (>= threads 권장) |
| `db.checkQuery` | `SELECT 1` | keepAlive 검증 쿼리 (Altibase는 `SELECT 1 FROM DUAL` 일 수 있음 — 확인) |
| `threads` | 유형별 | 동시 스레드 수 |
| `rampup` | 유형별 | 램프업(초) |
| `duration` | 60~120 | 측정 시간(초) |
| `accounts`/`tellers`/`branches` | 100000/10/1 | 스케일(아이디 상한). 적재 SF와 일치시킬 것 |

## DB별 접속값 (참고 — 실제 값/검증 필요)
- **PostgreSQL(XcruzDB)**: `db.driver=org.postgresql.Driver`, `db.url=jdbc:postgresql://<host>:5521/<db>`. coordinator(5521) 대상.
- **Altibase**: 드라이버 클래스/URL/포트는 **버전별로 다르므로 실물 확인**(미보유). 일반적으로 드라이버 jar를 이미지 `drivers/`에 추가해야 함([docker/jmeter/drivers](../docker/jmeter/drivers/README.md)).

## 설계 결정 / 검증 필요 항목
- **Mixed OLTP는 TPC-B 류**(account/teller/branch/history)로 단순·이식성 우선. 완전한 TPC-C(9테이블·5트랜잭션)는 방언 의존이 커 제외. 단일 트랜잭션 원자성이 필요하면 스토어드 프로시저로 확장(DB별 작성).
- `autocommit=true`(문장 단위 커밋). 진짜 멀티문장 트랜잭션은 위 프로시저 방식으로.
- 값은 JMeter `__Random` 인라인(프리페어드 아님) — 양쪽 동일 조건이라 비교 공정성 유지. 프리페어드(서버 플랜 캐시) 효과를 보려면 별도 변형 추가 가능.
- 고동시성(04)의 단계 증가는 **스톡 JMeter**로 `-Jthreads` 반복 실행(Job/스크립트 주도). jpgc Concurrency/Stepping ThreadGroup을 쓰려면 이미지에 플러그인 추가 필요.
- **커넥션 한계(중요)**: 대상 DB `max_connections=100`, `superuser_reserved_connections=3`, 그리고 XcruzDB coordinator↔worker 내부연결 + exporter 등으로 **베이스라인 ~45 연결 상시 점유** → `bench` 가용 ≈ **50**. JMeter는 풀을 init 시 `poolMax`만큼 미리 열기 때문에 `db.pool`이 가용을 넘으면 전부 실패("Error preloading the connection pool"). 04 기본 풀=40(검증 OK). **~50 이상 동시성 측정은 양쪽 DB의 `max_connections`를 동일하게 상향**해야 하며(공정성), 이는 튜닝 결정으로 리포트에 명시한다. `-Jthreads`는 `-Jdb.pool` 이하로 유지.
- 측정 지표(TPS/QPS, p50/95/99, 에러율)는 JTL/HTML 리포트 및 (추후) Prometheus Backend Listener 로 수집.
