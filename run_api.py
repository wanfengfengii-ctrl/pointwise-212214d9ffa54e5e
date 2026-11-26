"""Launch the museum HTTP service with a readiness response."""

import argparse
from pathlib import Path

from routing.http_api import serve_loopback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=('127.0.0.1', 'localhost'), required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args()

    with serve_loopback(args.data_dir, args.port) as server:
        class ReadyHandler(server.RequestHandlerClass):
            def do_GET(self):
                if self.path == '/health':
                    self._reply(200, {'ready': True})
                else:
                    super().do_GET()

        server.RequestHandlerClass = ReadyHandler
        print(f'Listening on 127.0.0.1:{server.server_port}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
