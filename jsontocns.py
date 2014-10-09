#!/usr/bin/env python

from __future__ import print_function
import sys
import argparse
import json

from cnsparser import CNSParser

parser = argparse.ArgumentParser(
    description='Save filled in model data back to a run.cns file',
    epilog=
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
    'job_dir', metavar='JOB_DIR',
    default = '.',
    nargs   = '?',
    help    = 'the job directory, defaults to \'.\', the current working directory'
)
parser.add_argument(
    '-t', '--template', metavar='TEMPLATE',
    dest    = 'source',
    type    = argparse.FileType('r'),
    default = None,
    help    = 'the CNS template file to parse, defaults to \'JOB_DIR/template.cns\''
)
parser.add_argument(
    '-i', '--form-data', metavar='FORM_DATA',
    dest    = 'form_data',
    type    = argparse.FileType('r'),
    default = None,
    help    = 'the formdata.json file to parse, defaults to \'JOB_DIR/formdata.json\''
)

args = parser.parse_args()

