#!/usr/bin/env python

from __future__ import print_function
import argparse
import json
import sys

def dump(component, depth=0, verbose=False):
    def indent(depth, string=''):
        return ('|' + ' '*2)*depth + string

    if component['type'] == 'parameter':
        print(indent(depth), end='')
        if component['datatype'] == 'choice':
            print('(' + component['datatype'] + '<' + ','.join(component['options']) + '>) ', end='')
        else:
            print('(' + component['datatype'] + ') ', end='')
        print(component['name'] + ' = "' + component['default'] + '"', end='')
    elif component['type'] == 'section':
        print(indent(depth))
        print(indent(depth, component['label']))
        print(indent(depth, ('=' if depth == 0 else '-')*len(component['label'])), end='')
    elif component['type'] == 'paragraph':
        print(indent(depth))
        lines = component['text'].split('\n')
        for line in lines:
            print(indent(depth, line))
        print(indent(depth))
        return
    else:
        return

    if 'repeat' in component and component['repeat']:
        if component['repeat_min'] == component['repeat_max']:
            repeat_string = 'x' + str(component['repeat_min'])
        elif component['repeat_max'] < 0:
            repeat_string = 'x ' + str(component['repeat_min']) + '+'
        else:
            repeat_string = 'x ' + str(component['repeat_min']) + '-' + str(component['repeat_max'])
        print(' ' + repeat_string, end='')

    if verbose and 'accesslevels' in component and len(component['accesslevels']):
        print(' [' + ', '.join(sorted(component['accesslevels'])) + ']')
    else:
        print()

    if component['type'] == 'section':
        for child in component['children']:
            dump(child, depth=depth+1, verbose=verbose)

argparser = argparse.ArgumentParser(description='Dump a CNS model structure')
argparser.add_argument(
    'source', metavar='MODEL',
    type    = argparse.FileType('r'),
    default = sys.stdin,
    nargs   = '?',
    help    = 'A model JSON file'
)
argparser.add_argument(
    '-v', '--verbose',
    dest    = 'verbose',
    action  = 'store_true',
    default = False,
    help    = 'show access levels for each component'
)
args = argparser.parse_args()

model = json.load(args.source)

for component in model:
    dump(component, verbose=args.verbose)
