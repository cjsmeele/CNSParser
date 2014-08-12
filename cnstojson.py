#!/usr/bin/env python

from __future__ import print_function
import sys
import argparse
import json

from cnsparser import CNSParser

parser = argparse.ArgumentParser(
    description='Convert a run.cns file to a JSON model description',
    epilog=
        'If both output files have the same filename or both point to stdout, '
        'the access levels and model information will be printed as a nested '
        'array, access levels first.\n'

        'Any additional arguments not listed here will be passed to the '
        'CNSParser constructor.'
)

parser.add_argument(
    '-V', '--version',
    action  = 'version',
    version = '%(prog)s 0.1'
)
parser.add_argument(
    '-v', '--verbose',
    dest    = 'verbose',
    action  = 'store_true',
    default = False,
    help    = 'print parsing information to stderr'
)
parser.add_argument(
    '-w', '--warnings',
    dest    = 'warnings',
    action  = 'store_true',
    default = False,
    help    = 'show warnings for unrecognized input data'
)
parser.add_argument(
    '-W', '--fatal-warnings',
    dest    = 'fatal_warnings',
    action  = 'store_true',
    default = False,
    help    = 'make unrecognized input data throw a fatal error, implicitly sets -w'
)
parser.add_argument(
    '-t', '--tidy',
    dest    = 'tidy',
    action  = 'store_true',
    default = False,
    help    = 'use pretty-printed JSON output'
)
parser.add_argument(
    'source', metavar='INPUT',
    type    = argparse.FileType('r'),
    default = sys.stdin,
    nargs   = '?',
    help    = 'the run.cns file to parse, defaults to \'-\' for stdin'
)
parser.add_argument(
    '-o', '--model-output', metavar='OUTPUT',
    dest    = 'model_output',
    type    = argparse.FileType('w'),
    default = sys.stdout,
    help    = 'the model JSON file, defaults to \'-\' for stdout'
)
parser.add_argument(
    '-l', '--accesslevel-output', metavar='OUTPUT',
    dest    = 'accesslevel_output',
    type    = argparse.FileType('w'),
    default = sys.stdout,
    help    = 'the access level JSON file, defaults to \'-\' for stdout'
)

args = parser.parse_args()

# Pass arguments as an unpacked dictionary to the CNSParser constructor
parser = CNSParser(**dict(
    (key, value) for (key, value) in vars(args).iteritems()
        # Filter out arguments used only by this program
        if key not in set(['model_output', 'accesslevel_output', 'tidy'])
))

accesslevels, components = parser.parse()

if args.accesslevel_output.name == args.model_output.name:
    print(json.dumps(
        [accesslevels, components],
        sort_keys=args.tidy,
        indent=(4 if args.tidy else None),
    ), file=args.accesslevel_output)
else:
    print(json.dumps(
        accesslevels,
        sort_keys=args.tidy,
        indent=(4 if args.tidy else None),
    ), file=args.accesslevel_output)

    print(json.dumps(
        components,
        sort_keys=args.tidy,
        indent=(4 if args.tidy else None),
    ), file=args.model_output)
