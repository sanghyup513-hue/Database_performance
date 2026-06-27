# Apache JMeter 부하 생성기 이미지 (PostgreSQL vs Altibase 벤치마크용)
#
# - 공식 Apache JMeter 릴리스 tarball을 sha512 검증 후 설치 (임의 포크 미사용)
# - PostgreSQL JDBC 드라이버를 Maven Central에서 lib/ 에 주입
# - Altibase JDBC 드라이버는 drivers/ 에 jar 를 넣으면 빌드 시 자동 포함
#   (Altibase 드라이버는 라이선스/배포 제약으로 repo 에 커밋하지 않음 — drivers/.gitignore 참고)
#
# 빌드 예:
#   docker build -t benchmark/jmeter:5.6.3 docker/jmeter
# 버전 오버라이드:
#   docker build --build-arg JMETER_VERSION=5.6.3 --build-arg PG_JDBC_VERSION=42.7.11 ...

FROM eclipse-temurin:17-jre

# ── 버전 고정 (재현성) ──────────────────────────────────────────────
ARG JMETER_VERSION=5.6.3
ARG PG_JDBC_VERSION=42.7.11

ENV JMETER_HOME=/opt/apache-jmeter-${JMETER_VERSION} \
    JMETER_VERSION=${JMETER_VERSION}
ENV PATH=${JMETER_HOME}/bin:${PATH}

# curl / ca-certificates (temurin 기본 미포함)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# ── 공식 JMeter 설치 (sha512 검증) ──────────────────────────────────
# archive.apache.org 는 과거 버전이 영구 보존되어 재현성에 유리
RUN set -eux; \
    base="https://archive.apache.org/dist/jmeter/binaries"; \
    tgz="apache-jmeter-${JMETER_VERSION}.tgz"; \
    curl -fSL "${base}/${tgz}" -o /tmp/${tgz}; \
    curl -fSL "${base}/${tgz}.sha512" -o /tmp/${tgz}.sha512; \
    expected="$(tr -dc '0-9a-fA-F' < /tmp/${tgz}.sha512 | tr 'A-F' 'a-f' | head -c 128)"; \
    actual="$(sha512sum /tmp/${tgz} | cut -d' ' -f1)"; \
    [ "${expected}" = "${actual}" ] || { echo "JMeter sha512 mismatch"; exit 1; }; \
    tar -xzf /tmp/${tgz} -C /opt; \
    rm -f /tmp/${tgz} /tmp/${tgz}.sha512

# ── PostgreSQL JDBC 드라이버 주입 ───────────────────────────────────
RUN set -eux; \
    curl -fSL "https://repo1.maven.org/maven2/org/postgresql/postgresql/${PG_JDBC_VERSION}/postgresql-${PG_JDBC_VERSION}.jar" \
      -o "${JMETER_HOME}/lib/postgresql-${PG_JDBC_VERSION}.jar"

# ── Altibase 등 추가 JDBC 드라이버 주입 (drivers/*.jar 있으면) ──────
COPY drivers/ /tmp/drivers/
RUN set -eux; \
    if ls /tmp/drivers/*.jar >/dev/null 2>&1; then \
      cp /tmp/drivers/*.jar "${JMETER_HOME}/lib/"; \
    fi; \
    rm -rf /tmp/drivers

# ── 비-root 실행 + 작업 디렉터리 ────────────────────────────────────
# /test : 테스트 계획(.jmx) 마운트 위치, /results : 결과 출력 위치
RUN set -eux; \
    useradd -r -u 1001 -m -d /home/jmeter jmeter; \
    mkdir -p /test /results; \
    chown -R jmeter:jmeter /test /results "${JMETER_HOME}"
USER 1001
WORKDIR /test

# 기본은 JMeter CLI. 매니페스트에서 args 로 -n -t plan.jmx -l results.jtl 등을 전달.
ENTRYPOINT ["jmeter"]
CMD ["--version"]
