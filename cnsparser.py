#!/usr/bin/env python

from __future__ import print_function
import sys
import re

def re_string(name, quote_id=[0]):
    """\
    Generates a regular expression for matching an optionally quoted string
    that may contain whitespace when quoted.
    The name argument specifies the capture group name the matched string
    will be stored in.
    Unquoted strings may only contain alphanumeric characters, '_', '-' and
    '.'

    quote_id is a static variable.
    """
    quote_id[0] += 1
    quote_name = 'quote' + str(quote_id[0]);
    return (
          r'\s*(?P<' + quote_name + r'>["' '\'' r'])?'            # Opening quote
        + r'(?P<' + name + r'>'                                   # Start string capture
            + r'(?(' + quote_name + r').*?'                       #     Quoted string
            + r'|[a-zA-Z0-9_\-.]*)'                               #     Alternative, unquoted string
        + r')'                                                    # Stop string capture
        + r'(?(' + quote_name + r')(?P=' + quote_name + r')|)\s*' # Closing quote
    )

# These patterns are used to dissect lines and map them to handler functions.
# Capture groups are always named using the (?P<name>) syntax.
parser_patterns = {
    # Match '{!accesslevel easy "Easy" }'
    # Note: Values may be quoted
    'accesslevel': r'\{!accesslevel\s+' + re_string('name') + r'\s+' + re_string('label') + r'\s*\}',

    # Match '{===>} prot_coor_A="/a/random/path/prot.pdb";'
    # Note: Values may be quoted
    'parameter': r'\{===>}\s*' + re_string('name') + r'\s*=\s*' + re_string('value') + r'\s*;',

    # Match '{* Molecular Type *}'
    'paragraph': r'\{\*\s*(?P<text>.*?)\s*\*}',

    # Match '{+ choice: protein nucleic carbohydrate ligand +}'
    'metadata': r'\{\+\s*(?P<key>[^:]+?)\s*:\s*(?P<value>.+?)\s*\+}',

    # Match '{======================= Molecular Definition ($segid) =========================}'
    'blockstart': r'\{={3,}\s*(?P<head>.*?)\s*={3,}\}',
}

class CNSParser(object):

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
        # The contents of named capture groups can be retrieved by the handler
        # in the args argument, which is a dictionary.
        self.pattern_handlers = [
            (
                parser_patterns['accesslevel'],
                self.handle_accesslevel
            ), (
                parser_patterns['parameter'],
                self.handle_parameter
            ), (
                parser_patterns['paragraph'],
                self.handle_paragraph
            ), (
                parser_patterns['metadata'],
                self.handle_metadata
            ), (
                parser_patterns['blockstart'],
                self.handle_head
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
        Insert a new parameter into the component list, using all applicable
        metadata specified since the last parameter.
        """
        self.current_metadata.update({
            'name':    args['name'],
            'default': args['value'],
        })

        self.current_metadata['type'] = 'parameter'

        if 'datatype' not in self.current_metadata:
            # No datatype was specified, make a guess based on the default value
            if re.search('^\d+$', self.current_metadata['default']):
                self.current_metadata['datatype'] = 'int'
            elif re.search('^[0-9.]+$', self.current_metadata['default']):
                self.current_metadata['datatype'] = 'float'
            else:
                self.current_metadata['datatype'] = 'text'

        if 'level' not in self.current_metadata:
            # No access level was specified, default to the lowest level, which should be 'easy'
            self.current_metadata['level'] = self.accesslevels[0]['name']

        if len(self.current_paragraph):
            self.current_metadata['label'] = self.current_paragraph
            self.current_paragraph = ""
        else:
            self.warn('Parameter "' + self.current_metadata['name'] + '" is not labeled')

        self.printv(
            'Added parameter \'' + self.current_metadata['name']    + '\''
            + ' datatype = '     + self.current_metadata['datatype']
            + ' default  = \''   + self.current_metadata['default'] + '\''
        )

        self.components.append(self.current_metadata)
        #self.current_block.append(self.current_metadata)
        self.current_metadata = {}

    def handle_metadata(self, args):
        if args['key'] == 'choice':
            self.current_metadata.update({
                'datatype': 'choice',
                'options':  args['value'].split(),
            })
            self.printv('Saving metadata for next parameter: datatype = choice, options = \'' + args['value'] + '\'')
        else:
            self.warn('Unknown metadata key "' + args['key'] + '"')

    def handle_paragraph(self, args):
        if len(self.current_paragraph):
            self.printv('Appending to current paragraph: \'' + args['text'] + '\'')
            self.current_paragraph += '\n' + args['text']
        else:
            self.printv('Creating paragraph or label: \'' + args['text'] + '\'')
            self.current_paragraph = args['text']

    def handle_head(self, args):
        head = re.sub('=', '', args['head'])
        # TODO
        pass

    def write(parameters):
        # TODO
        pass

    def parse(self):
        self.current_metadata  = {}
        self.current_paragraph = {}
        self.blocks = []
        self.current_block = []

        for line in self.source:
            line = line.rstrip()
            if not len(line):
                if len(self.current_paragraph):
                    self.components.append({
                        'type': 'paragraph',
                        'text': self.current_paragraph
                    })
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
                    function(args)
                    break
            if not match:
                self.warn('Could not parse line "' + line + '"')
                # Assume that the current paragraph (on the line before this
                # one) has something to do with this unparsable line, drop it.
                self.current_paragraph = ""

        # Clean up
        del self.current_metadata
        del self.current_paragraph

        return self.accesslevels, self.components
