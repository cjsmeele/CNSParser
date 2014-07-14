#!/usr/bin/env python

from __future__ import print_function
import sys
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

    def __init__(self, source):
        """\
        source must be iteratable, contents are parsed line-by-line
        """
        self.source       = source
        self.accesslevels = []
        self.parameters   = []

        # Maps regular expressions to handler functions.
        # Capture groups are always named using the (?P<name>) syntax.
        # They can be retrieved by the handler using the match.group('name') function.
        # TODO: Extend the wrapper around these handlers to provide them with
        #       simple named arguments instead of passing a Match object.
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
                r'\{\+\s*(?P<key>[^:]+)\s*:\s*(?P<value>.+)\s*\+}',
                self.handle_metadata
            ),
            # TODO: Match blocks and handle repetitions
            # TODO: Blocks should take the top level in the parameters list
            #       instead of the parameters themselves
        ]

    def handle_accesslevel(self, match):
        """\
        Add an access level.
        Access levels must be specified in order from easiest to most complex.
        """
        self.accesslevels.append({
            'name':  match.group('name'),
            'label': match.group('label'),
        })

    def handle_parameter(self, match):
        """\
        Insert a new parameter into the parameter list, using all applicable
        metadata specified since the last parameter.
        """
        self.current_metadata.update({
            'name':    match.group('name'),
            'default': match.group('value'),
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
            print('Warning: Parameter "' + self.current_metadata['name'] + '" is not labeled', file=sys.stderr)

        self.parameters.append(self.current_metadata)
        self.current_metadata = {}

    def handle_metadata(self, match):
        if match.group('key') == 'choice':
            self.current_metadata.update({
                'type':    'choice',
                'options': match.group('value').split(),
            })
        else:
            print('Warning: Unknown metadata key "' + match.group('key') + '"', file=sys.stderr)

    def handle_paragraph(self, match):
        if len(self.current_paragraph):
            self.current_paragraph += '\n' + match.group('text')
        else:
            self.current_paragraph = match.group('text')

    def parse(self):
        self.current_metadata  = {}
        self.current_paragraph = {}

        for line in self.source:
            line = line.rstrip()
            if not len(line):
                # TODO: Store the current paragraph somewhere instead of discarding it
                self.current_paragraph = ""
                continue
            for pattern, function in self.pattern_handlers:
                match = re.search(pattern, line)
                if match:
                    #print('\n' + '-'*80, file=sys.stderr)
                    #print(line, file=sys.stderr)
                    #print(match.groupdict(), file=sys.stderr)
                    function(match)
                    break
            if not match:
                print('Warning: Could not parse line "' + line + '"', file=sys.stderr)

        # Clean up
        del self.current_metadata

        return self.accesslevels, self.parameters

if __name__ == '__main__':
    """\
    When run as a program, this module will try to use a run.cns in the current
    working directory and output the model description to stdout in yaml format.
    """
    # TODO: Use stdin instead and accept a filename parameter
    with open('run.cns', 'r') as cnsfile:
        model_generator = ModelGenerator(cnsfile)
        accesslevels, parameters = model_generator.parse()

        print(yaml.dump_all([accesslevels, parameters],
            explicit_start=True, default_flow_style=False))
