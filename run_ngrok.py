import argparse
import os
import subprocess
import sys

from dotenv import load_dotenv
from pyngrok import ngrok
from pyngrok.conf import PyngrokConfig
from pyngrok.exception import PyngrokNgrokError


DEFAULT_NGROK_HOSTS = ['localhost', '127.0.0.1', '.ngrok-free.app', '.ngrok.app']
DEFAULT_NGROK_ORIGINS = ['https://*.ngrok-free.app', 'https://*.ngrok.app']


def merge_csv_env(name, values):
    current = [item.strip() for item in os.environ.get(name, '').split(',') if item.strip()]
    for value in values:
        if value not in current:
            current.append(value)
    os.environ[name] = ','.join(current)


def build_ngrok_config():
    token = os.environ.get('NGROK_AUTHTOKEN')
    region = os.environ.get('NGROK_REGION')
    if token or region:
        return PyngrokConfig(auth_token=token, region=region)
    return None


def main():
    load_dotenv(override=True)

    parser = argparse.ArgumentParser(description='Run Django through an ngrok tunnel.')
    parser.add_argument('--port', default=os.environ.get('NGROK_PORT', '8000'))
    parser.add_argument('--host', default=os.environ.get('DJANGO_RUNSERVER_HOST', '0.0.0.0'))
    parser.add_argument('--domain', default=os.environ.get('NGROK_DOMAIN'))
    args = parser.parse_args()

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')
    os.environ['ENABLE_NGROK'] = 'true'
    merge_csv_env('DJANGO_ALLOWED_HOSTS', DEFAULT_NGROK_HOSTS)
    merge_csv_env('DJANGO_CSRF_TRUSTED_ORIGINS', DEFAULT_NGROK_ORIGINS)

    options = {'bind_tls': True}
    if args.domain:
        options['domain'] = args.domain

    try:
        tunnel = ngrok.connect(
            addr=args.port,
            proto='http',
            pyngrok_config=build_ngrok_config(),
            **options,
        )
    except PyngrokNgrokError as exc:
        if 'ERR_NGROK_4018' in str(exc):
            print(
                'ngrok requires an authtoken before it can start a tunnel.\n'
                'Create a free ngrok account, copy your token from:\n'
                'https://dashboard.ngrok.com/get-started/your-authtoken\n\n'
                'Then add this line to your local .env file:\n'
                'NGROK_AUTHTOKEN=your_token_here\n\n'
                'Or run this once in a new terminal:\n'
                'ngrok config add-authtoken your_token_here',
                file=sys.stderr,
            )
            return 1
        raise

    print(f'ngrok tunnel: {tunnel.public_url}', flush=True)
    print(f'PhonePe webhook URL: {tunnel.public_url}/payments/phonepe/webhook/', flush=True)

    try:
        return subprocess.call([
            sys.executable,
            'manage.py',
            'runserver',
            f'{args.host}:{args.port}',
        ])
    finally:
        ngrok.disconnect(tunnel.public_url)


if __name__ == '__main__':
    raise SystemExit(main())
