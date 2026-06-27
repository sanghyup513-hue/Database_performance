#!/usr/bin/env bash
# 벤치마크 데이터 적재 (스케일 팩터 SF). 데이터 규모 스케일링 테스트용.
#   SF=10  -> account 100만 / teller 100 / branch 10
#   SF=100 -> account 1천만 ...
# 접속은 PG* 환경변수(PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD/PGSSLMODE) 사용.
#
# 실행 예 (psql 포함 컨테이너):
#   docker run --rm --env-file /tmp/bench.env -e SF=100 -v $PWD/scripts:/s \
#     postgres:17-alpine sh /s/load_data.sh
set -euo pipefail
SF="${SF:-10}"
ACC=$((SF * 100000)); TEL=$((SF * 10)); BR=$SF
echo "[load] SF=$SF  account=$ACC teller=$TEL branch=$BR"
psql -v ON_ERROR_STOP=1 \
  -c "TRUNCATE bench_history, bench_account, bench_teller, bench_branch;" \
  -c "INSERT INTO bench_branch (bid,bbalance,filler)        SELECT g,0,'' FROM generate_series(1,$BR)  g;" \
  -c "INSERT INTO bench_teller (tid,bid,tbalance,filler)    SELECT g,((g-1)/10)+1,0,'' FROM generate_series(1,$TEL) g;" \
  -c "INSERT INTO bench_account (aid,bid,abalance,filler)   SELECT g,((g-1)/($ACC/$BR))+1,0,'' FROM generate_series(1,$ACC) g;" \
  -c "SELECT 'loaded account='||count(*) FROM bench_account;"
echo "[load] done. JMeter 실행 시 -Jaccounts=$ACC -Jtellers=$TEL -Jbranches=$BR 로 맞출 것."
