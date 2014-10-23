#!/usr/bin/env python

from __future__ import print_function
import argparse
import json
import sys


# component_index_static being an array is a hack to get function-static variables in python.
def dump(component, depth=0, verbose=False, component_index_static=[0]):
    """\
    Dump a component and its children if its a section.
    """
    def indent(depth, string=''):
        return ('|' + ' '*2)*depth + string

    if component['type'] == 'parameter':
        print(indent(depth) + '#' + str(component_index_static[0]) + ' ', end='')
        if component['datatype'] == 'choice':
            print('(' + component['datatype'] + '<' + ','.join(component['options']) + '>) ', end='')
        else:
            print('(' + component['datatype'] + ') ', end='')
        print(component['name'] + ' = "' + component['default'] + '"', end='')
    elif component['type'] == 'section':
        header_text = '#' + str(component_index_static[0]) + ' ' + component['label']
        print(indent(depth))
        print(indent(depth, header_text))
        print(indent(depth, ('=' if depth == 0 else '-')*len(header_text)), end='')
    elif component['type'] == 'paragraph':
        print(indent(depth))
        lines = component['text'].split('\n')
        for line in lines:
            print(indent(depth, line))
        print(indent(depth))
        component_index_static[0] += 1
        return
    else:
        return

    if 'repeat' in component and component['repeat']:
        if component['repeat_min'] == component['repeat_max']:
            repeat_string = 'x' + str(component['repeat_min'])
        elif component['repeat_max'] == None:
            repeat_string = 'x ' + str(component['repeat_min']) + '+'
        else:
            repeat_string = 'x ' + str(component['repeat_min']) + '-' + str(component['repeat_max'])
        print(' ' + repeat_string, end='')

    if verbose and 'accesslevels' in component and len(component['accesslevels']):
        print(' [' + ', '.join(sorted(component['accesslevels'])) + ']', end='')

    if component['hidden']:
        print(' (hidden)', end='')

    print()

    component_index_static[0] += 1

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
