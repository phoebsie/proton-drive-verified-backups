"""Command line entry; external output and exception details stay out of logs."""
import argparse
import json
import os
import sys
from .config import load
from .runner import run, verify, transport
from .monitor import check
from .state import Busy


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description='Standalone Proton Drive DR reference')
    parser.add_argument('--config', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('run')
    commands.add_parser('check')
    commands.add_parser('preflight')
    restore = commands.add_parser('verify')
    restore.add_argument('object_name')
    restore.add_argument('--sha256')
    args = parser.parse_args()
    try:
        config = load(args.config)
        if args.command == 'run':
            result = run(config)
        elif args.command == 'check':
            result = check(config)
        elif args.command == 'preflight':
            transport(config).list_remote()
            result = {'cli_checksum_and_list': True}
        else:
            result = verify(config, args.object_name, args.sha256)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Busy:
        print('{"skipped":"operation already running"}')
        return 75
    except Exception as exc:
        print(json.dumps({'ok': False, 'error_class': type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
