"""Start the unified application with Waitress on Windows or Linux."""
import argparse
import os
from waitress import serve
from review_suite.app import create_app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default=os.environ.get('REVIEW_HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8080')))
    args = parser.parse_args()
    application = create_app()
    print(f'Review suite: http://{args.host}:{args.port}', flush=True)
    serve(application, host=args.host, port=args.port, threads=8,
          max_request_body_size=30 * 1024 * 1024, channel_timeout=240,
          clear_untrusted_proxy_headers=not application.config['TRUST_PROXY'])
