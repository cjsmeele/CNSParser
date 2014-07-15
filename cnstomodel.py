#!/usr/bin/env python

from __future__ import print_function
import sys
import argparse
import re
import yaml

class ModelGenerator(object):

    quote_id = 0
    @staticmethod
    def re_string(name):
        """\
        Generates a regular expression for matching an optionally quoted string
        that may contain whitespace when quoted.
        The name argument specifies the capture group name the matched string
        will be stored in.
        Unquoted strings may only contain alphanumeric characters, '_', '-' and
        '.'
        """
        ModelGenerator.quote_id += 1
        quote_name = 'quote' + str(ModelGenerator.quote_id);
        return (
              r'\s*(?P<' + quote_name + r'>["' '\'' r'])?'            # Opening quote
            + r'(?P<' + name + r'>'                                   # Start string capture
                + r'(?(' + quote_name + r').*?'                       #     Quoted string
                + r'|[a-zA-Z0-9_\-.]*)'                               #     Alternative, unquoted string
            + r')'                                                    # Stop string capture
            + r'(?(' + quote_name + r')(?P=' + quote_name + r')|)\s*' # Closing quote
        )

    def __init__(self, source=sys.stdin, verbose=False, warnings=False, fatal_warnings=False):
        """\
        source must be iteratable, contents are parsed line-by-line
        """
        self.verbose        = verbose
        self.warnings       = warnings or fatal_warnings
        self.fatal_warnings = fatal_warnings
        self.source         = source
        self.accesslevels   = []
        self.components     = []

        # Maps regular expressions to handler functions.
        # Capture groups are always named using the (?P<name>) syntax.
        # They can be retrieved by the handler in the args argument, which is
        # a dictionary.
        self.pattern_handlers = [
            (
                # Match '{!accesslevel easy "Easy" }'
                r'\{!accesslevel\s+' + self.re_string('name') + r'\s+' + self.re_string('label') + r'\s*\}',
                self.handle_accesslevel
            ), (
                # Match '{===>} prot_coor_A="/a/random/path/prot.pdb";'
                r'\{===>}\s*' + self.re_string('name') + r'\s*=\s*' + self.re_string('value') + r'\s*;',
                self.handle_parameter
            ), (
                # Match '{* Molecular Type *}'
                r'\{\*\s*(?P<text>.*?)\s*\*}',
                self.handle_paragraph
            ), (
                # Match '{+ choice: protein nucleic carbohydrate ligand +}'
                # Note: Values should not be quoted here
                r'\{\+\s*(?P<key>[^:]+?)\s*:\s*(?P<value>.+?)\s*\+}',
                self.handle_metadata
            ),
            # TODO: Match blocks and handle repetitions
            # TODO: Blocks should take the top level in the components list
            #       instead of the components themselves
        ]

    def warn(self, text):
        """\
        Print a warning if warnings are turned on.
        Exits with a non-zero value if fatal warnings are turned on.
        """
        if self.warnings:
            if self.fatal_warnings:
                print('Error:', text, file=sys.stderr)
                exit(1)
            else:
                print('Warning:', text, file=sys.stderr)

    def printv(self, text):
        """\
        Print a message if verbose mode is turned on.
        """
        if self.verbose:
            print(text, file=sys.stderr)

    def handle_accesslevel(self, args):
        """\
        Add an access level.
        Access levels must be specified in order from easiest to most complex.
        """
        self.printv('Added accesslevel \'' + args['name'] + '\', labeled \'' + args['label'] + '\'')
        self.accesslevels.append({
            'name':  args['name'],
            'label': args['label'],
        })

    def handle_parameter(self, args):
        """\
        Insert a new parameter into the parameter list, using all applicable
        metadata specified since the last parameter.
        """
        self.current_metadata.update({
            'name':    args['name'],
            'default': args['value'],
        })

        if not 'type' in self.current_metadata:
            # No type was specified, make a guess based on the default value
            if re.search('^\d+$', self.current_metadata['default']):
                self.current_metadata['type'] = 'int'
            elif re.search('^[0-9.]+$', self.current_metadata['default']):
                self.current_metadata['type'] = 'float'
            else:
                self.current_metadata['type'] = 'text'

        if not 'level' in self.current_metadata:
            # No access level was specified, default to the lowest level, which should be 'easy'
            self.current_metadata['level'] = self.accesslevels[0]['name']

        if len(self.current_paragraph):
            self.current_metadata['label'] = self.current_paragraph
            self.current_paragraph = ""
        else:
            self.warn('Parameter "' + self.current_metadata['name'] + '" is not labeled')

        self.printv(
            'Added parameter \'' + self.current_metadata['name'] + '\''
            + ' type = '      + self.current_metadata['type']
            + ' default = \'' + self.current_metadata['default'] + '\''
        )

        self.components.append(self.current_metadata)
        self.current_metadata = {}

    def handle_metadata(self, args):
        if args['key'] == 'choice':
            self.current_metadata.update({
                'type':    'choice',
                'options': args['value'].split(),
            })
            self.printv('Saving metadata for next parameter: type = choice, options = \'' + args['value'] + '\'')
        else:
            self.warn('Unknown metadata key "' + args['key'] + '"')

    def handle_paragraph(self, args):
        if len(self.current_paragraph):
            self.printv('Appending to current paragraph: \'' + args['text'] + '\'')
            self.current_paragraph += '\n' + args['text']
        else:
            self.printv('Creating paragraph or label: \'' + args['text'] + '\'')
            self.current_paragraph = args['text']

    def parse(self):
        self.current_metadata  = {}
        self.current_paragraph = {}

        for line in self.source:
            line = line.rstrip()
            if not len(line):
                # TODO: Store the current paragraph somewhere instead of discarding it
                if len(self.current_paragraph):
                    self.warn('Discarding current paragraph')
                    self.current_paragraph = ""
                continue
            for pattern, function in self.pattern_handlers:
                match = re.search(pattern, line)
                if match:
                    #print('\n' + '-'*80, file=sys.stderr)
                    #print(line, file=sys.stderr)

                    # Create an args dictionary based on named capture groups
                    # in the regex match. Filter out quote captures.
                    args = dict(
                        (key, value) for (key, value) in match.groupdict().iteritems()
                            if not re.match('^quote\d+$', key)
                    )
                    #print(args, file=sys.stderr)
                    function(args)
                    break
            if not match:
                self.warn('Could not parse line "' + line + '"')

        # Clean up
        del self.current_metadata
        del self.current_paragraph

        return self.accesslevels, self.components

if __name__ == '__main__':
    """\
    When run as a program, this module will try to use a run.cns in the current
    working directory and output the model description to stdout in yaml format.
    """

    parser = argparse.ArgumentParser(description='Convert a run.cns file to a generic YAML model description')

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

    # Pass arguments as an unpacked dictionary to the ModelGenerator constructor
    model_generator = ModelGenerator(**dict(
        (key, value) for (key, value) in vars(args).iteritems()
            if key not in set(['destination'])
    ))
    accesslevels, components = model_generator.parse()

    print(yaml.dump_all([accesslevels, components],
        explicit_start=True, default_flow_style=False), file=args.destination)
