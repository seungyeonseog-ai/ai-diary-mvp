#!/bin/sh
# 검증용 Ubuntu 내부에서만 실행. Windows 시작 작업은 등록하지 않는다.
set -eu
test "$(id -u)" = 0
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
# 패키지 설치 중 자동 서비스 시작을 막고 설치 후에도 자동시작을 끈다.
if [ ! -e /usr/sbin/policy-rc.d ]; then
  printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
  chmod 755 /usr/sbin/policy-rc.d
  created_policy=1
else
  created_policy=0
fi
trap 'if [ "$created_policy" = 1 ]; then rm -f /usr/sbin/policy-rc.d; fi' EXIT
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
if command -v systemctl >/dev/null 2>&1; then
  systemctl disable docker.service docker.socket containerd.service
fi
docker --version
docker compose version
