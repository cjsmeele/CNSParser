#!/usr/bin/env python

from __future__ import print_function
import sys
import argparse
import json
import os

from cnsparser import CNSParser

parser = argparse.ArgumentParser(
    description='Save filled in model data back to a run.cns file',
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
    '-k', '--keep-aux-filenames',
    dest    = 'keep_files',
    action  = 'store_true',
    default = False,
    help    = 'create links instead of renaming auxiliary files'
)
parser.add_argument(
    'job_dir', metavar='JOB_DIR',
    default = '.',
    nargs   = '?',
    help    = 'the job directory, defaults to \'.\', the current working directory'
)
parser.add_argument(
    '-t', '--template', metavar='TEMPLATE',
    dest    = 'template',
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
parser.add_argument(
    '-o', '--cns-output', metavar='CNS_OUTPUT',
    dest    = 'cns_output',
    type    = argparse.FileType('w'),
    default = None,
    help    = 'the run.cns output file, defaults to \'JOB_DIR/run.cns\''
)

args = parser.parse_args()

job_dir    = args.job_dir    if args.job_dir    is not None else '.'
template   = args.template   if args.template   is not None else open(os.path.join(job_dir, 'template.cns'))
form_data  = args.form_data  if args.form_data  is not None else open(os.path.join(job_dir, 'formdata.json'))
cns_output = args.cns_output if args.cns_output is not None else open(os.path.join(job_dir, 'run.cns'), 'w')

data = json.load(form_data)

parser = CNSParser(
    source         = template,
    verbose        = args.verbose,
    warnings       = args.warnings,
    fatal_warnings = args.fatal_warnings,
)

cns, file_map = parser.write(data, job_dir)

# Rename auxiliary files.
for component in data['files'].itervalues():
    for instance in component.itervalues():
        for file in instance.itervalues():
            # NOTE: We assume that the data['files'] list was filtered or
            #       generated securely by the form server.
            # TODO: It would be better to pass file information to CNSParser separate
            #       from other form data to avoid having to modify the form data as
            #       uploaded by the client.

            if args.keep_files:
                if file['name'] in file_map:
                    print('Linking ' + file_map[file['name']] + ' -> ' + os.path.join(job_dir, file['name']))
                    # Create a hard link.
                    os.link(os.path.join(job_dir, file['name']), os.path.join(job_dir, file_map[file['name']]))
            else:
                if file['name'] in file_map:
                    print('Moving ' + os.path.join(job_dir, file['name']) + ' -> ' + file_map[file['name']])
                    os.rename(os.path.join(job_dir, file['name']), os.path.join(job_dir, file_map[file['name']]))
                else:
                    print('Removing ' + os.path.join(job_dir, file['name']))
                    os.remove(file['name'])

cns_output.write('\n'.join(cns) + '\n')
