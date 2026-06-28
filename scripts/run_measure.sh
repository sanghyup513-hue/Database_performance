#!/usr/bin/env bash
# 본 측정 러너 (gb10에서 실행). 7개 유형 × RUNS회 반복, 워밍업 포함 측정.
# JTL: /data/bench-results/pg__<type>__r<N>.jtl  (집계 시 워밍업 구간 제외 + 중앙값)
# 접속 비밀번호는 /tmp/jmeter.props (db.password) 사용.
set -u
RES=/data/bench-results
IMG=benchmark/jmeter:5.6.3
PROPS=/tmp/jmeter.props
PLANS=/tmp/jplans/plans
DBURL='jdbc:postgresql://192.168.0.221:5521/sgicpoc_bench?sslmode=require'
DUR="${DUR:-55}"; RUNS="${RUNS:-3}"
ACC="${ACC:-10000000}"; TEL="${TEL:-1000}"; BR="${BR:-100}"

rm -f "$RES"/pg__*__r*.jtl 2>/dev/null
J(){ # plan tag run extra...
  docker run --rm -v "$PLANS":/test:ro -v "$PROPS":/jmeter.props:ro -v "$RES":/results "$IMG" \
    -n -t "/test/$1" -q /jmeter.props \
    -Jdb.driver=org.postgresql.Driver "-Jdb.url=$DBURL" -Jdb.user=bench \
    -Jaccounts="$ACC" -Jtellers="$TEL" -Jbranches="$BR" -Jrampup=5 -Jduration="$DUR" \
    "${@:4}" -l "/results/pg__$2__r$3.jtl" >/dev/null 2>&1; }

SPEC=(
 "01-read-only.jmx|01_read_only|-Jthreads=10 -Jdb.pool=40"
 "02-write-heavy.jmx|02_write_heavy|-Jthreads=10 -Jdb.pool=40"
 "03-mixed-oltp.jmx|03_mixed_oltp|-Jthreads=20 -Jdb.pool=40"
 "04-high-concurrency.jmx|04_high_concurrency|-Jthreads=40 -Jdb.pool=40"
 "05-large-workload.jmx|05_large_workload|-Jthreads=4 -Jdb.pool=16"
 "06-hot-row.jmx|06_hot_row|-Jthreads=30 -Jdb.pool=40 -Jhotrows=10"
 "07-rw-ratio.jmx|07_rw_ratio|-Jthreads=20 -Jdb.pool=40 -Jread_pct=50 -Jwrite_pct=50"
)
echo "START $(date +%F_%H:%M:%S)  SF: acc=$ACC dur=${DUR}s runs=$RUNS"
for s in "${SPEC[@]}"; do
  IFS='|' read -r plan tag extra <<< "$s"
  for r in $(seq 1 "$RUNS"); do
    J "$plan" "$tag" "$r" $extra
    echo "$(date +%H:%M:%S) $tag run$r done"
  done
done
echo "ALL MEASUREMENT DONE $(date +%F_%H:%M:%S)"
