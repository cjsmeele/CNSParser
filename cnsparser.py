#!/usr/bin/env python

from __future__ import print_function
import sys
import re

def re_string(name="", quote_id=[0]):
    """\
    Generates a regular expression for matching an optionally quoted string
    that may contain whitespace when quoted.
    The name argument specifies the capture group name the matched string
    will be stored in. If no name is given, no capture group will be filled.
    Unquoted strings may only contain alphanumeric characters, '_', '-' and '.'

    quote_id is a static variable.
    """
    quote_id[0] += 1
    quote_name = 'quote' + str(quote_id[0]);
    return (
          r'\s*(?P<' + quote_name + r'>["' '\'' r'])?'            # Opening quote
        + ((r'(?P<' + name + r'>') if name else r'(?:')           # Start string capture
            + r'(?(' + quote_name + r').*?'                       #     Quoted string
            + r'|[a-zA-Z0-9_\-.]*)'                               #     Alternative, unquoted string
        + r')'                                                    # Stop string capture
        + r'(?(' + quote_name + r')(?P=' + quote_name + r')|)\s*' # Closing quote
    )

# These patterns are used to dissect lines and map them to handler functions.
# Capture groups must be named using the (?P<name>) syntax.
parser_patterns = {
    # Match '{!accesslevel easy "Easy" }'
    # Note: Values may be quoted.
    'accesslevel': r'\{!accesslevel\s+' + re_string('name') + r'\s+' + re_string('label') + r'\s*\}',

    # Match '{===>} prot_coor_A="/a/random/path/prot.pdb";'
    # Note: Values may be quoted.
    'parameter': r'\{===>}\s*' + re_string('name') + r'\s*=\s*' + re_string('value') + r'\s*;'
                 r'\s*(!#level\s*=\s*' + re_string('accesslevel') + r')?',

    # Match 'numhis=5;'
    # These parameters are not saved to the model
    'static_parameter': r'^\s*' + re_string('name') + r'\s*=\s*' + re_string('value') + r'\s*;',

    # Match '{* Molecular Type *}'
    'paragraph': r'\{\*\s*(?P<text>.*?)\s*\*}',

    # Match '! #multi-index=AA #type=integer'
    # Note: This format allows for actual comments before the first hash sign
    'hash_metadata': r'^\s*![^#]*(?P<metadata>(?:#[a-zA-Z0-9_-]+(?:\s*[=:]\s*' + re_string() + r')?)+)\s*$',

    # Match '{+ choice: protein nucleic carbohydrate ligand +}'
    'plus_metadata': r'\{\+\s*(?P<key>[^:]+?)\s*:\s*(?P<value>.+?)\s*\+}',

    # Match '{== Molecular Definition ($segid) ==}'
    # Note: The amount of equals signs signify depth, allowing for nested blocks.
    'blockstart': r'\{(?P<indentation>={2,})\s*(?P<head>.*?)\s*={2,}\}',

    # Match '! This is a comment'
    'linecomment': r'^\s*!\s*(?P<text>.*?)\s*$',

    # Match '{ This is a comment }'
    # Note: This parser does not support multiline block comments.
    #       Also, block comments may not contain closing braces.
    'blockcomment': r'\{\s*(?P<text>[^}]*?)\s*\}',
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
        #
        # Note that the order of these patterns matters:
        # Patterns are checked in the order they are specified, and when lines
        # match multiple patterns, only the first match counts.
        #
        # To extend the parser without changing the original, subclass CNSParser
        # and add or replace pattern handlers in your __init__ function.
        self.pattern_handlers = [
            (
                parser_patterns['accesslevel'],
                self.handle_accesslevel
            ), (
                parser_patterns['parameter'],
                self.handle_parameter
            ), (
                parser_patterns['static_parameter'],
                None
            ), (
                parser_patterns['paragraph'],
                self.handle_paragraph
            ), (
                parser_patterns['hash_metadata'],
                self.handle_hash_metadata
            ), (
                parser_patterns['plus_metadata'],
                self.handle_plus_metadata
            ), (
                parser_patterns['blockstart'],
                self.handle_head
            ), (
                # Regular comments must be recognized to avoid warnings.
                parser_patterns['linecomment'],
                None
            ), (
                parser_patterns['blockcomment'],
                None
            ),
        ]

    # FIXME: A library shouldn't call exit(), raise an exception instead
    def warn(self, text):
        """\
        Print a warning if warnings are turned on.
        Exits with a non-zero value if fatal warnings are turned on.

        This method should only be called in parse() context.
        """
        if self.warnings:
            if self.fatal_warnings:
                print('Error on line ' + str(self.line_no) + ':', text, file=sys.stderr)
                exit(1)
            else:
                print('Warning on line ' + str(self.line_no) + ':', text, file=sys.stderr)

    def error(self, text):
        """\
        Print an error and exit with a non-zero value.

        This method should only be called in parse() context.
        """
        print('Error on line ' + str(self.line_no) + ':', text, file=sys.stderr)
        exit(1)

    def printv(self, text):
        """\
        Print a message if verbose mode is turned on.
        """
        if self.verbose:
            print('Line ' + str(self.line_no) + ':', text, file=sys.stderr)

    def squash_accesslevels(self, inherited, minimum_index, maximum_index, includes, excludes):
        """\
        Squash the different type of access level definitions into a single set with allowed access levels.
        The definition sets are evaluated in the following order:
        inherited levels, specified minimum, specified maximum, includes, excludes

        Note that minimums, maximums, includes and excludes are never inherited from parent blocks;
        We only inherit a squashed set of allowed access levels.

        Also important is that a parameter or block is NOT allowed to have an access level that is
        lower than that of its parent. As a result, #level-include is only useful
        when in the same metadata a level-min or level-max was specified.

        This function saves the access levels in a list instead of a set as the JSON module cannot dump sets.
        """
        if inherited is None:
            inherited = set(self.accesslevel_names)
        else:
            # Inherited levels will most likely be passed as a list instead of a set
            inherited = set(inherited)

        levels = set(inherited)

        if minimum_index is not None:
            # Filter out levels with a lower index than the specified minimum
            levels = set([value for value in levels if self.accesslevel_names.index(value) >= minimum_index])

        if maximum_index is not None:
            # Filter out levels with a higher index than the specified maximum
            levels = set([value for value in levels if self.accesslevel_names.index(value) <= maximum_index])

        # Add explicitly included levels
        levels |= includes

        # Remove explicitly excluded levels
        levels -= excludes

        # We are strict in access level inheritance. If you need a lower-level
        # parameter in an otherwise restricted block, lower the level requirement for that block
        # and use excludes to deny access to other parameters.
        if not inherited.issuperset(levels):
            self.error('Cannot allow levels that are not allowed in a parent block')

        if minimum_index is not None:
            actual_minimum = min([self.accesslevel_names.index(name) for name in levels])
            if minimum_index < actual_minimum:
                self.warn(
                    'Specified minimum level \'' + self.accesslevel_names[minimum_index] + '\' '
                    + 'is lower than the lowest actual access level for this component ('
                    + self.accesslevel_names[actual_minimum] + ')'
                )

        if maximum_index is not None:
            actual_maximum = max([self.accesslevel_names.index(name) for name in levels])
            if maximum_index > actual_maximum:
                self.warn(
                    'Specified minimum level \'' + self.accesslevel_names[minimum_index] + '\' '
                    + 'is lower than the lowest actual access level for this component ('
                    + self.accesslevel_names[actual_maximum] + ')'
                )

        return list(levels)

    def install_common_metadata(self, component):
        """\
        Installs metadata that's valid for both blocks and parameters.
        Clears the metadata dict afterwards.
        """
        if len(self.current_blocks):
            inherited_accesslevels = self.current_blocks[-1]['component']['accesslevels']
        else:
            # Notify squash_accesslevels that we have no parent.
            # Note that this is different from passing an empty set.
            inherited_accesslevels = None

        # Calculate allowed access levels
        # Use provided metadata if available
        component['accesslevels'] = self.squash_accesslevels(
            inherited     = inherited_accesslevels,
            minimum_index = None if 'accesslevel-index-min' not in self.current_metadata
                                 else self.current_metadata['accesslevel-index-min'],

            maximum_index = None if 'accesslevel-index-max' not in self.current_metadata
                                 else self.current_metadata['accesslevel-index-max'],

            includes      = set() if 'accesslevel-includes' not in self.current_metadata
                                  else self.current_metadata['accesslevel-includes'],

            excludes      = set() if 'accesslevel-excludes' not in self.current_metadata
                                  else self.current_metadata['accesslevel-excludes'],
        )

        # Install repeat data and do some checks
        for key, value in self.current_metadata.items():
            # Save repeat metadata
            if key in set(['repeat', 'repeat-index', 'repeat-min', 'repeat-max']):
                component[key] = value

        if 'repeat' in component and component['repeat']:
            if 'repeat-index' not in component:
                self.error('Component set to repeat but no repeat-index defined')
            if len(self.current_blocks):
                for block in self.current_blocks:
                    # We can't do this check during metadata definition because
                    # at that time we don't know if the metadata is for a block
                    # on a higher nesting level.
                    if block['repeat'] and block['repeat-index'] == component['repeat-index']:
                        self.error('Cannot reuse repeat-index of parent block: "' + component['repeat-index'] + '"')
        else:
            component['repeat'] = False

        self.current_metadata = {}

    def open_block(self, label, level):
        """\
        NOTE: 'level' here means the depth of the block as the amount of equals
              signs used in its definition.
              The access level is specified in the same way as it is done for
              parameters, using !#level metadata.
        """
        # Close open blocks until we are on the right level
        while len(self.current_blocks) and level <= self.current_blocks[-1]['level']:
            self.current_blocks.pop()

        component = {
            'label':     label,
            'type':     'block',
            'children': []
        }
        self.install_common_metadata(component)

        if len(self.current_blocks):
            # Add a block component to the current block component's children
            self.current_blocks[-1]['component']['children'].append(component)

            # Add a pointer to the block component to the block list
            self.current_blocks.append({
                'level': level,
                'component': self.current_blocks[-1]['component']['children'][-1]
            })
        else:
            # This is a top-level block
            self.components.append(component)
            self.current_blocks.append({
                'level': level,
                'component': self.components[-1]
            })

    def append_component(self, component):
        if not len(self.current_blocks) or not len(self.components):
            self.components.append(component)
        else:
            self.current_blocks[-1]['component']['children'].append(component)

    def handle_accesslevel(self, args):
        """\
        Add an access level.
        Access levels must be specified in order from easiest to most complex,
        before any blocks or parameters are defined.
        """
        if len(self.components) or len(self.current_blocks):
            self.error('Access levels need to be specified before any parameters or blocks are defined')

        self.accesslevels.append({
            'name':  args['name'],
            'label': args['label'],
        })
        self.accesslevel_names.append(args['name'])

        self.printv('Added accesslevel \'' + args['name'] + '\', labeled \'' + args['label'] + '\'')

    def handle_parameter(self, args):
        """\
        Insert a new parameter into the component list, using all applicable
        metadata specified since the last parameter or block.
        """
        component = {
            'name':    args['name'],
            'default': args['value'],
            'type':    'parameter',
        }

        self.install_common_metadata(component)

        #if 'repeat' not in self.current_metadata:
        #    self.current_metadata['repeat'] = False

        if 'datatype' not in component:
            # No datatype was specified, make a guess based on the default value
            if re.search('^\d+$', component['default']):
                component['datatype'] = 'int'
            elif re.search('^[0-9.]+$', component['default']):
                component['datatype'] = 'float'
            else:
                component['datatype'] = 'text'

        if len(self.current_paragraph):
            component['label'] = self.current_paragraph
            self.current_paragraph = ""
        else:
            self.warn('Parameter "' + component['name'] + '" is not labeled')

        self.printv(
            'Added parameter \'' + component['name']    + '\''
            + ' datatype = '     + component['datatype']
            + ' default  = \''   + component['default'] + '\''
        )

        self.append_component(component)

    def handle_hash_metadata(self, args):
        # args.metadata is a string starting with a hash sign that may contain multiple pieces of metadata
        # Extract all settings from this string
        for setting in re.finditer(r'(#(?P<key>[a-zA-Z0-9_-]+)\s*[=:]\s*)' + re_string('value'), args['metadata']):
            key, value = setting.group('key'), setting.group('value')

            if key in set(['level-min', 'level-max', 'level-include', 'level-exclude']):
                if value not in self.accesslevel_names:
                    self.error('Unknown access level specified: "' + value + '"');

                if 'accesslevel-includes' not in self.current_metadata:
                    self.current_metadata['accesslevel-includes'] = set()
                if 'accesslevel-excludes' not in self.current_metadata:
                    self.current_metadata['accesslevel-excludes'] = set()

            if key == 'level-min':
                if (
                        'accesslevel-index-max' in self.current_metadata
                        and self.accesslevel_names.index(value) > self.current_metadata['accesslevel-index-max']
                    ):
                    self.error(
                        'Specified minimum level is higher than the current maximum level ('
                        + self.accesslevel_names[self.current_metadata['accesslevel-index-max']] + ')'
                    )
                self.current_metadata['accesslevel-index-min'] = self.accesslevel_names.index(value)

            elif key == 'level-max':
                if (
                        'accesslevel-index-min' in self.current_metadata
                        and self.accesslevel_names.index(value) < self.current_metadata['accesslevel-index-min']
                    ):
                    self.error('Specified maximum level is lower than the current minimum level')
                self.current_metadata['accesslevel-index-max'] = self.accesslevel_names.index(value)

            elif key == 'level-include':
                self.current_metadata['accesslevel-excludes'].discard(value)
                self.current_metadata['accesslevel-includes'].add(value)

            elif key == 'level-exclude':
                self.current_metadata['accesslevel-includes'].discard(value)
                self.current_metadata['accesslevel-excludes'].add(value)
                pass

            elif key == 'multi-index':
                self.current_metadata.update({
                    'repeat': True,
                    'repeat-index': value,
                })
            elif key == 'multi-min':
                self.current_metadata.update({ 'repeat_min': value })
            elif key == 'multi-max':
                self.current_metadata.update({ 'repeat_max': value })
            elif key == 'type':
                self.current_metadata.update({ 'datatype': value })
            else:
                self.warn('Unknown hash_metadata key "' + key + '"')

        # TODO: Loop through value-less settings

    def handle_plus_metadata(self, args):
        # The only known uses for this metadata format are choice and table definitions
        if args['key'] == 'choice':
            # Filter out enclosing quotation marks
            values = [ re.sub(r'^(["|'+'\''+r'])(.*)\1$', r'\2', value) for value in args['value'].split() ]

            self.current_metadata.update({
                'datatype': 'choice',
                'options':  values,
            })
            self.printv('Saving metadata for next parameter: datatype = choice, options = \'' + args['value'] + '\'')
        elif args['key'] == 'table':
            # Rendering and formatting is not our responsibility
            pass
        else:
            self.warn('Unknown plus_metadata key "' + args['key'] + '"')

    def handle_paragraph(self, args):
        if len(self.current_paragraph):
            self.printv('Appending to current paragraph: \'' + args['text'] + '\'')
            self.current_paragraph += '\n' + args['text']
        else:
            self.printv('Creating paragraph or label: \'' + args['text'] + '\'')
            self.current_paragraph = args['text']

    def handle_head(self, args):
        label = re.sub('=', '', args['head'])
        self.open_block(label, len(args['indentation']))
        # Blocks are closed automatically

    def write(parameters):
        # TODO
        pass

    def parse(self):
        self.current_metadata  = {} # Data type, etc.
        self.current_paragraph = {} # Documentation or parameter labels
        self.current_blocks    = [] # Contains pointers to actual block components, used for switching between levels
        self.accesslevel_names = [] # Used for inexpensive parameter access level validation
        self.line_no           = 0

        for line in self.source:
            self.line_no += 1
            line = line.rstrip()
            if not len(line):
                if len(self.current_paragraph):
                    self.append_component({
                        'type': 'paragraph',
                        'text': self.current_paragraph
                    })
                    self.current_paragraph = ""
                continue
            for pattern, function in self.pattern_handlers:
                match = re.search(pattern, line)
                if match:
                    if function is not None:
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
                # one) describes this unparsable line, drop it.
                self.current_paragraph = ""

        # Clean up
        del self.line_no
        del self.accesslevel_names
        del self.current_blocks
        del self.current_paragraph
        del self.current_metadata

        return self.accesslevels, self.components
