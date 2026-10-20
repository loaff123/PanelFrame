"""Offline CLI. Exit 0 complete, 1 incomplete, 2 invalid/I/O, 3 unsupported."""
import argparse
from pathlib import Path
import sys
from . import __version__
from .model import PanelFrameError, UnsupportedInput, MAX_CSV_BYTES, parse_csv, inventory
from .reports import read_file, json_bytes, recover, verify

def main(argv=None):
    parser=argparse.ArgumentParser(prog='panelframe',description='Recover exact repeated exported-row poses. No assembly or electrical certification.')
    parser.add_argument('--version',action='version',version='PanelFrame '+__version__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('inspect','recover','verify'):
        command=commands.add_parser(name)
        command.add_argument('source');command.add_argument('panel')
        if name=='inspect':command.add_argument('--json',required=True,dest='inventory_path')
        else:
            command.add_argument('--contract',required=True)
            command.add_argument('--out' if name=='recover' else '--report',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='inspect':
            source=parse_csv(read_file(args.source,MAX_CSV_BYTES),'source')
            panel=parse_csv(read_file(args.panel,MAX_CSV_BYTES),'panel')
            value={'schema_version':1,'scope':'Observed CSV facts only. inspect does not infer units, exporter profile, compatibility, or assembly intent.',
                   'source':inventory(source),'panel':inventory(panel)}
            with Path(args.inventory_path).open('xb') as stream:
                stream.write(json_bytes(value))
            print('Inventory written. Export profile and origins still require operator declarations.')
            return 0
        if args.command=='recover':
            complete=recover(args.source,args.panel,args.contract,args.out)
            print('Complete exported-row pose handoff written.' if complete else 'Incomplete: diagnostic report written; no offsets.csv emitted.')
            return 0 if complete else 1
        verify(args.source,args.panel,args.contract,args.report)
        print('Verified the complete exported-row pose handoff against original bytes.')
        return 0
    except UnsupportedInput as exc:
        print('Unsupported input: '+str(exc),file=sys.stderr)
        return 3
    except (PanelFrameError,OSError) as exc:
        print('Invalid input or output: '+str(exc),file=sys.stderr)
        return 2
