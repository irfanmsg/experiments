#!/usr/bin/env python3
"""Write a persistent Studio user unit and environment; never start a service."""
import argparse
import ipaddress
from pathlib import Path


def quote(value):
    value = str(value)
    if '\n' in value or '\r' in value or '\0' in value:
        raise ValueError('Configuration values must be single-line strings')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1', type=ipaddress.ip_address,
                        help='Bind address; use the private interface address for network access')
    parser.add_argument('--port', default=8001, type=int)
    parser.add_argument('--asset-root', type=Path, default=Path.home() / 'Repos/OmniverseAssets')
    parser.add_argument('--config-dir', type=Path, default=Path.home() / '.config',
                        help='Override for a review-only staged installation')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('--port must be between 1024 and 65535')
    project = Path(__file__).resolve().parents[1]
    python = project / '.venv/bin/python'
    if not python.is_file():
        parser.error('Install dependencies with ./omni_setup/setup.sh first')
    config = args.config_dir.expanduser().resolve()
    environment = config / 'blueprint-studio/host.env'
    unit = config / 'systemd/user/blueprint-studio.service'
    environment.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    unit.parent.mkdir(parents=True, exist_ok=True)
    if environment.exists():
        print(f'Kept existing configuration: {environment}')
    else:
        content = '\n'.join(f'{key}={quote(value)}' for key, value in {
            'BLUEPRINT_STUDIO_HOST': str(args.host),
            'BLUEPRINT_STUDIO_PORT': args.port,
            'BLUEPRINT_STUDIO_ASSET_ROOT': args.asset_root.expanduser().resolve(),
            'PYTHONUNBUFFERED': '1',
        }.items()) + '\n'
        with environment.open('x') as output:
            environment.chmod(0o600)
            output.write(content)
        print(f'Wrote configuration: {environment}')
    # systemd expands percent specifiers in paths and dollars in ExecStart.
    executable = quote(str(python).replace('%', '%%').replace('$', '$$'))
    unit.write_text(f'''[Unit]
Description=Blueprint Studio editor and managed RTX stream

[Service]
Type=simple
WorkingDirectory={str(project).replace('%', '%%')}
EnvironmentFile={str(environment).replace('%', '%%')}
ExecStart={executable} -m uvicorn app.main:app --host ${{BLUEPRINT_STUDIO_HOST}} --port ${{BLUEPRINT_STUDIO_PORT}} --workers 1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillMode=control-group
UMask=0077

[Install]
WantedBy=default.target
''')
    print(f'Wrote unit: {unit}')
    print('No services were started or reloaded. Review docs/hosting.md before activation.')


if __name__ == '__main__':
    main()
