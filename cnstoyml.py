#!/usr/bin/env python

from __future__ import print_function
import sys
import argparse
import yaml

from cnsparser import CNSParser

parser = argparse.ArgumentParser(description='Convert a run.cns file to a YAML model description')

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
    '-c', '--compact',
    dest    = 'tidy',
    action  = 'store_false',
    default = True,
    help    = 'do NOT default to the more readable YAML block syntax'
)
parser.add_argument(
    'source', metavar='INPUT',
    type    = argparse.FileType('r'),
    default = sys.stdin,
    nargs   = '?',
    help    = 'the run.cns file to parse, defaults to \'-\' for stdin'
)
parser.add_argument(
    '-o', '--output', metavar='OUTPUT',
    dest    = 'destination',
    type    = argparse.FileType('w'),
    default = sys.stdout,
    help    = 'the output YAML file, defualts to \'-\' for stdout'
)

args = parser.parse_args()

# Pass arguments as an unpacked dictionary to the CNSParser constructor
parser = CNSParser(**dict(
    (key, value) for (key, value) in vars(args).iteritems()
        # Filter out arguments used only by this program
        if key not in set(['destination', 'tidy'])
))
accesslevels, components = parser.parse()

print(yaml.dump_all([accesslevels, components],
    explicit_start=True, default_flow_style=(not args.tidy)), file=args.destination)
