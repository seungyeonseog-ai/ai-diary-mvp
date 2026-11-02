"""로컬 실제/격리 서버의 사용자 화면 파일 동일성 확인. 인증/DB 조작 없음."""
import argparse
import hashlib
from urllib.request import urlopen

PATHS = ('/', '/login?next=%2Fspace', '/library',
         '/static/js/space/login.js', '/static/js/space/home.js',
         '/static/js/space/ui.js', '/static/js/space/library.js',
         '/static/js/space/library_model.js', '/static/css/library.css',
         '/static/css/space-ui.css', '/static/images/space/envelope-v2.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual-port', type=int, default=8000)
    parser.add_argument('--isolated-port', type=int, default=8016)
    args = parser.parse_args()
    failures = []
    for path in PATHS:
        hashes = []
        for port in (args.actual_port, args.isolated_port):
            with urlopen(f'http://127.0.0.1:{port}{path}', timeout=10) as response:
                hashes.append(hashlib.sha256(response.read()).digest())
        match = hashes[0] == hashes[1]
        print(('PASS' if match else 'FAIL'), path)
        if not match:
            failures.append(path)
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
