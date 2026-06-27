# JMeter 부하 생성기 이미지

PostgreSQL·Altibase 공통 부하 하니스로 사용할 Apache JMeter 컨테이너 이미지.

## 구성
- 베이스: `eclipse-temurin:17-jre` (JMeter 5.6.3 는 Java 8+ 요구, 17 LTS 사용)
- JMeter: 공식 Apache 릴리스 `5.6.3` (tarball sha512 검증)
- PostgreSQL JDBC: `42.7.11` (Maven Central, 빌드 시 자동 주입) — PostgreSQL 17 호환
- Altibase JDBC: `drivers/` 에 jar 를 두면 자동 포함 (드라이버 확보 후)

## 빌드
```sh
docker build -t benchmark/jmeter:5.6.3 docker/jmeter
```
버전 변경:
```sh
docker build \
  --build-arg JMETER_VERSION=5.6.3 \
  --build-arg PG_JDBC_VERSION=42.7.11 \
  -t benchmark/jmeter:5.6.3 docker/jmeter
```

## 동작 확인
```sh
docker run --rm benchmark/jmeter:5.6.3 --version
```

## 실행 방식
- ENTRYPOINT 는 `jmeter`. 테스트 계획(.jmx)을 `/test` 에, 결과를 `/results` 에 둔다.
- CLI 실행 예 (K8s Job 에서 args 로 전달):
  ```
  -n -t /test/plan.jmx -l /results/result.jtl -e -o /results/report
  ```
- DB 접속 정보(호스트·계정·비밀번호·포트)는 이미지에 넣지 않고, K8s Secret → 환경변수/JMeter property 로 주입한다 (자격증명 평문 금지).
