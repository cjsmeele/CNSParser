#!/usr/bin/env python

from __future__ import print_function
import sys
import re
import copy


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
    'parameter': r'\{===>}\s*' + re_string('name') + r'\s*=\s*' + re_string('value') + r'\s*;',

    # Match 'numhis=5;'
    # These parameters are not saved to the model
    'static_parameter': r'^\s*' + re_string('name') + r'\s*=\s*' + re_string('value') + r'\s*;',

    # Match '{* Molecular Type *}'
    'paragraph': r'\{\*\s*(?P<text>.*?)\s*\*}',

    # Match '! #multi-index=AA #type=integer'
    # Note: This format allows for actual comments before the first hash sign
    'hash_attributes': r'^\s*![^#]*(?P<attributes>(?:#[a-zA-Z0-9_-]+(?:\s*[=:]\s*' + re_string() + r')?\s*)+)\s*$',

    # Match '{+ choice: protein nucleic carbohydrate ligand +}'
    #'plus_attributes': r'\{\+\s*(?P<key>[^:]+?)\s*:\s*(?P<value>.+?)\s*\+}',
    'plus_attributes': r'\{\+\s*(?P<key>choice)\s*:\s*(?P<value>.+?)\s*\+}',

    # Match '{== Molecular Definition NN ==}'
    # Note: The amount of equals signs signify depth, allowing for nested sections.
    'section_start': r'\{(?P<indentation>={2,})\s*(?P<head>[^=].*?)\s*={2,}\}',

    # Match '! This is a comment'
    'linecomment': r'^\s*!\s*(?P<text>.*?)\s*$',

    # Match '{ This is a comment }'
    # Note: This parser does not support multiline block comments.
    #       Also, block comments may not contain closing braces.
    'blockcomment': r'\{\s*(?P<text>[^}]*?)\s*\}',
}

class ParserException(Exception):
    pass

class CNSParser(object):

    def __init__(self, source=sys.stdin, verbose=False, warnings=False, fatal_warnings=False):
        """\
        Source must be iteratable, contents are parsed line-by-line.
        """
        self.verbose        = verbose
        self.warnings       = warnings or fatal_warnings
        self.fatal_warnings = fatal_warnings
        self.source         = source

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
                'accesslevel',
                parser_patterns['accesslevel'],
                self.handle_accesslevel
            ), (
                'parameter',
                parser_patterns['parameter'],
                self.handle_parameter
            ), (
                'static_parameter',
                parser_patterns['static_parameter'],
                None
            ), (
                'paragraph',
                parser_patterns['paragraph'],
                self.handle_paragraph
            ), (
                'hash_attributes',
                parser_patterns['hash_attributes'],
                self.handle_hash_attributes
            ), (
                'plus_attributes',
                parser_patterns['plus_attributes'],
                self.handle_plus_attributes
            ), (
                'section_start',
                parser_patterns['section_start'],
                self.handle_head
            ), (
                # Regular comments must be recognized to avoid warnings.
                'linecomment',
                parser_patterns['linecomment'],
                None
            ), (
                'blockcomment',
                parser_patterns['blockcomment'],
                None
            ),
        ]

    def warn(self, text):
        """\
        Print a warning if warnings are turned on.
        Throws a ParserException if fatal warnings are turned on.

        This method should only be called in parse() or write() context.
        """
        if self.warnings:
            if self.fatal_warnings:
                raise ParserException('Error on line ' + str(self.line_no) + ': ' + text)

            else:
                print('Warning on line ' + str(self.line_no) + ':', text, file=sys.stderr)

    def error(self, text):
        """\
        Throws a ParserException.

        This method should only be called in parse() or write() context.
        """
        raise ParserException('Error on line ' + str(self.line_no) + ': ' + text)

    def printv(self, text):
        """\
        Print a message if verbose mode is turned on.
        """
        if self.verbose:
            print('Line ' + str(self.line_no) + ':', text, file=sys.stderr)

    def squash_accesslevels(self, inherited, minimum_index, maximum_index, includes, excludes):
        """\
        Squash the different type of access level attributes into a single set with allowed access levels.
        The definition sets are evaluated in the following order:
        inherited levels, specified minimum, specified maximum, includes, excludes

        Note that minimums, maximums, includes and excludes are never inherited from parent sections;
        We only inherit a squashed set of allowed access levels.

        Also important is that a parameter or section is NOT allowed to have an access level that is
        lower than that of its parent. As a result, #level-include is only useful
        when for the same parameter or section a level-min or level-max attribute was specified.

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
        # parameter in an otherwise restricted section, lower the level requirement for that section
        # and use excludes to deny access to other parameters.
        if not inherited.issuperset(levels):
            self.error('Cannot allow levels that are not allowed in a parent section')

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
                    'Specified maximum level \'' + self.accesslevel_names[maximum_index] + '\' '
                    + 'is higher than the highest actual access level for this component ('
                    + self.accesslevel_names[actual_maximum] + ')'
                )

        return list(levels)

    def install_common_attributes(self, component):
        """\
        Installs attributes that are valid for both sections and parameters.
        Clears the attributes dict afterwards.
        """
        if len(self.current_sections):
            inherited_accesslevels = self.current_sections[-1]['component']['accesslevels']
        else:
            # Notify squash_accesslevels that we have no parent.
            # Note that this is different from passing an empty set.
            inherited_accesslevels = None

        # Calculate allowed access levels
        # Use provided attributes if available
        component['accesslevels'] = self.squash_accesslevels(
            inherited     = inherited_accesslevels,
            minimum_index = None if 'accesslevel_index_min' not in self.current_attributes
                                 else self.current_attributes['accesslevel_index_min'],

            maximum_index = None if 'accesslevel_index_max' not in self.current_attributes
                                 else self.current_attributes['accesslevel_index_max'],

            includes      = set() if 'accesslevel_includes' not in self.current_attributes
                                  else self.current_attributes['accesslevel_includes'],

            excludes      = set() if 'accesslevel_excludes' not in self.current_attributes
                                  else self.current_attributes['accesslevel_excludes'],
        )

        # Install repeat data and do some checks
        for key, value in self.current_attributes.items():
            if key in set(['repeat', 'repeat_index', 'repeat_min', 'repeat_max']):
                component[key] = value
            if key == 'custom_attributes':
                for key, value in value.items():
                    assert key not in component # This would indicate that a reserved word is used as an attr name.
                    component[key] = value

        if 'repeat' in component and component['repeat']:
            if 'repeat_index' not in component:
                self.error('Component set to repeat but no repeat-index defined')
            if component['type'] == 'parameter' and component['name'].find(component['repeat_index']) == -1:
                self.error('Name of repeatable parameter does not contain the specified repeat-index placeholder "'
                    + component['repeat_index'] + '"')
            if 'repeat_min' not in component:
                component['repeat_min'] = 1;
            if 'repeat_max' not in component:
                component['repeat_max'] = None;
        else:
            component['repeat'] = False

        if len(self.current_sections):
            for section in self.current_sections:
                # We can't do this check during attribute definition because
                # at that time we don't know if the attribute is for a section
                # on a higher nesting level.
                if component['repeat']:
                    if section['component']['repeat'] and section['component']['repeat_index'] == component['repeat_index']:
                        self.error('Cannot reuse repeat-index of parent section: "' + component['repeat_index'] + '"')

                if (
                        component['type'] == 'parameter'
                        and section['component']['repeat'] and component['name'].find(section['component']['repeat_index']) == -1
                    ):
                    self.error('Parameter name does not contain parent repeat-index placeholder "'
                        + section['component']['repeat_index'] + '"')

        if 'hidden' in self.current_attributes and self.current_attributes['hidden']:
            component['hidden'] = True
        elif len(self.current_sections):
            # Inherit the 'hidden' attribute
            component['hidden'] = self.current_sections[-1]['component']['hidden']
        else:
            component['hidden'] = False


        self.current_attributes = {}

    def open_section(self, label, level):
        """\
        NOTE: 'level' here means the depth of the section as the amount of equals
              signs used in its definition.
              The access level is specified in the same way as it is done for
              parameters, using !#level attributes.
        """
        # Close open sections until we are on the right level
        while len(self.current_sections) and level <= self.current_sections[-1]['level']:
            self.current_sections.pop()

        component = {
            'label':     label,
            'type':     'section',
            'children':  [],
        }
        self.install_common_attributes(component)

        if len(self.current_sections):
            # Add a section component to the current section component's children
            self.current_sections[-1]['component']['children'].append(component)

            # Add a pointer to the section component to the section list
            self.current_sections.append({
                'level': level,
                'component': self.current_sections[-1]['component']['children'][-1]
            })
        else:
            # This is a top-level section
            self.components.append(component)
            self.current_sections.append({
                'level': level,
                'component': self.components[-1]
            })

    def append_component(self, component):
        """\
        Add a component to the component tree.
        """
        if not len(self.current_sections) or not len(self.components):
            self.components.append(component)
        else:
            # Add the component to the last / deepest section if it exists.
            self.current_sections[-1]['component']['children'].append(component)

    # Pattern handlers {{{

    def handle_accesslevel(self, args):
        """\
        Add an access level.
        Access levels must be specified in order from easiest to most complex,
        before any sections or parameters are defined.
        """
        if len(self.components) or len(self.current_sections):
            self.error('Access levels need to be specified before any parameters or sections are defined')

        self.accesslevels.append({
            'name':  args['name'],
            'label': args['label'],
        })
        self.accesslevel_names.append(args['name'])

        self.printv('Added accesslevel \'' + args['name'] + '\', labeled \'' + args['label'] + '\'')

    def handle_parameter(self, args):
        """\
        Insert a new parameter into the component list, using all applicable
        attributes specified since the last parameter or section.
        """
        component = {
            'name':    args['name'],
            'default': args['value'],
            'type':    'parameter',
        }

        if 'datatype' in self.current_attributes:
            component['datatype'] = self.current_attributes['datatype']
            if component['datatype'] == 'choice':
                component['options'] = self.current_attributes['options']
        else:
            # No datatype was specified, make a guess based on the default value
            if re.search('^\d+$', component['default']):
                component['datatype'] = 'integer'
            elif re.search('^[0-9.]+$', component['default']):
                component['datatype'] = 'float'
            else:
                component['datatype'] = 'string'


        self.install_common_attributes(component)

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

    def handle_hash_attributes(self, args):
        # args.attributes is a string starting with a hash sign that may contain multiple attributes
        # Extract all settings from this string
        for setting in re.finditer(r'#(?P<key>[a-zA-Z0-9_-]+)(?:\s*[=:]\s*' + re_string('value') + ')?', args['attributes']):
            key, value = setting.group('key'), setting.group('value')

            if key in set(['level-min', 'level-max', 'level-include', 'level-exclude']):
                if value not in self.accesslevel_names:
                    self.error('Unknown access level specified: "' + value + '"');

                if 'accesslevel_includes' not in self.current_attributes:
                    self.current_attributes['accesslevel_includes'] = set()
                if 'accesslevel_excludes' not in self.current_attributes:
                    self.current_attributes['accesslevel_excludes'] = set()

            if key == 'level-min':
                if (
                        'accesslevel_index_max' in self.current_attributes
                        and self.accesslevel_names.index(value) > self.current_attributes['accesslevel_index_max']
                    ):
                    self.error(
                        'Specified minimum level is higher than the current maximum level ('
                        + self.accesslevel_names[self.current_attributes['accesslevel_index_max']] + ')'
                    )
                self.current_attributes['accesslevel_index_min'] = self.accesslevel_names.index(value)

            elif key == 'level-max':
                if (
                        'accesslevel_index_min' in self.current_attributes
                        and self.accesslevel_names.index(value) < self.current_attributes['accesslevel_index_min']
                    ):
                    self.error('Specified maximum level is lower than the current minimum level')
                self.current_attributes['accesslevel_index_max'] = self.accesslevel_names.index(value)

            elif key == 'level-include':
                self.current_attributes['accesslevel_excludes'].discard(value)
                self.current_attributes['accesslevel_includes'].add(value)

            elif key == 'level-exclude':
                self.current_attributes['accesslevel_includes'].discard(value)
                self.current_attributes['accesslevel_excludes'].add(value)

            elif key == 'hidden':
                self.current_attributes['hidden'] = True

            elif key == 'multi-index':
                if 'repeat_index' in self.current_attributes:
                    self.error('Repeat-index specified twice for the same component')
                self.current_attributes.update({
                    'repeat': True,
                    'repeat_index': value,
                })
            elif key == 'multi-min':
                self.current_attributes.update({ 'repeat': True, 'repeat_min': int(value) })
            elif key == 'multi-max':
                self.current_attributes.update({ 'repeat': True, 'repeat_max': int(value) })
            elif key == 'type':
                self.current_attributes.update({ 'datatype': value })
            else:
                self.warn('Unknown hash_attributes key "' + key + '" saved as custom attribute')
                # Add it to current_attributes anyway.
                if 'custom_attributes' not in self.current_attributes:
                    self.current_attributes['custom_attributes'] = dict()
                self.current_attributes['custom_attributes'].update({ key: value })

    def handle_plus_attributes(self, args):
        # The only known uses for this attribute format are choice and table definitions.
        if args['key'] == 'choice':
            # Filter out enclosing quotation marks.
            values = [ re.sub(r'^(["|'+'\''+r'])(.*)\1$', r'\2', value) for value in args['value'].split() ]

            self.current_attributes.update({
                'datatype': 'choice',
                'options':  values,
            })
            self.printv('Saving attributes for next parameter: datatype = choice, options = \'' + args['value'] + '\'')
        elif args['key'] == 'table':
            # Rendering and formatting is not our responsibility.
            pass
        else:
            self.warn('Unknown plus_attributes key "' + args['key'] + '"')

    def handle_paragraph(self, args):
        if len(self.current_paragraph):
            self.printv('Appending to current paragraph: \'' + args['text'] + '\'')
            self.current_paragraph += '\n' + args['text']
        else:
            self.printv('Creating paragraph or label: \'' + args['text'] + '\'')
            self.current_paragraph = args['text']

    def handle_head(self, args):
        label = re.sub('=', '', args['head'])
        self.open_section(label, len(args['indentation']))
        # Blocks are closed automatically

    # }}}

    def save_paragraph(self, paragraph):
        if len(self.current_sections):
            inherited_accesslevels = self.current_sections[-1]['component']['accesslevels']
        else:
            inherited_accesslevels = None

        component = {
            'type': 'paragraph',
            'text': self.current_paragraph
        }

        # Paragraphs always inherit their parent access levels.
        # If you need a paragraph with different access levels, consider
        # adding a section for it.
        component['accesslevels'] = self.squash_accesslevels(
            inherited     = inherited_accesslevels,
            minimum_index = None,
            maximum_index = None,
            includes      = set(),
            excludes      = set(),
        )

        self.append_component(component)

    def postprocess_section(self, section):
        """\
        Hides sections with no visible children in the model description.
        To be called at the end of the parse() function.
        """
        children_hidden = True

        for component in section['children']:
            if component['type'] == 'section':
                self.postprocess_section(component)
            if (
                    component['type'] in set(['section', 'parameter'])
                    and ('hidden' not in component or not component['hidden'])
                ):
                children_hidden = False
                break

        section['hidden'] = children_hidden

    def call_handlers(self, line):
        """\
        Tries to call the pattern handler function for the given line.
        If the function was found and called, returns the name of the matched pattern
        (see the self.pattern_handlers definition).
        Returns None otherwise.
        """
        for name, pattern, function in self.pattern_handlers:
            match = re.search(pattern, line)
            if match:
                if function is not None:
                    # Create an args dictionary based on named capture groups
                    # in the regex match. Filter out quote captures added with re_string().
                    args = dict(
                        (key, value) for (key, value) in match.groupdict().iteritems()
                            if not re.match('^quote\d+$', key)
                    )
                    args['_line'] = line # Pattern handlers may access the exact line through this argument.

                    function(args)
                return name
        return None

    def parse_start(self):
        # These properties are used by pattern handler functions.
        # They are set on the parser object. This avoids having to pass
        # parser state around as a parameter to every function.

        self.current_attributes = {} # Data type, etc.
        self.current_paragraph  = {} # Documentation paragraphs or parameter labels
        self.current_sections   = [] # Contains pointers to actual section components, used for switching between levels
        self.accesslevel_names  = [] # Used in parameter access level validation
        self.line_no            = 0  # Current line number in a CNS source file

        self.accesslevels = [] # A list of access levels
        self.components   = [] # A tree of components found by the parser

    def parse_end(self):
        # Clean up. Not necessary, but it's good to leave the parser in its initial state after its done.
        del self.components
        del self.accesslevels
        del self.line_no
        del self.accesslevel_names
        del self.current_sections
        del self.current_paragraph
        del self.current_attributes

    def parse(self):
        """\
        Loops through the CNS source file and fills in a model description.
        Returns the accesslevels and components structures.
        """

        # Initialize temporary parser state variables.
        self.parse_start()

        # Skip until the start of the block parameter definition.
        found_parameter_block = False

        for line in self.source:
            self.line_no += 1
            if re.search('- begin block parameter definition -', line) is not None:
                found_parameter_block = True
                break

        if not found_parameter_block:
            self.error('Could not find the start of the block parameter definition')

        for line in self.source:
            self.line_no += 1
            line = line.rstrip()
            if len(line):
                if self.call_handlers(line) is None:
                    self.warn('Could not parse line "' + line + '"')
                    # Assume that the current paragraph (on the line before this
                    # one) describes this unparsable line, drop it.
                    self.current_paragraph = ''
            else:
                if len(self.current_paragraph):
                    # A single empty line can mark the end of a paragraph component.
                    self.save_paragraph(self.current_paragraph)
                    self.current_paragraph = ''
                continue

        accesslevels = self.accesslevels
        components   = self.components

        # Clean up parser state.
        self.parse_end()

        for component in components:
            if component['type'] == 'section':
                self.postprocess_section(component)

        return accesslevels, components

    def write(self, form_data, aux_file_root):
        """\
        Generate a new CNS file based on the supplied CNS source file (used as
        a template) and a form_data structure which describes all instantiated parameters and sections.
        Returns a new CNS file as a list of lines, and a map for renaming auxiliary files.
        """

        cns          = [] # The CNS output
        aux_file_map = dict()

        # First, get the CNS source (file) as an array.
        # This allows us to seek within the file to deal with repetitions.
        source_array = [line for line in self.source]

        # Replace the source property since we just exhausted it by looping through it.
        self.source  = source_array

        # Obtain components and accesslevels by parsing the CNS file.
        # This seems redundant since we loop through the CNS file a second time
        # later on, but it simplifies the code.
        accesslevels, component_tree = self.parse()

        def squash_component_tree(roots):
            """\
            Returns a flat list of components.
            """
            flat = list()
            for component in roots:
                flat.append(component)
                if component['type'] == 'section':
                    flat.extend(squash_component_tree(component['children']))
            return flat


        # Component order in this list will match the component_index numbers
        # supplied in form_data.
        components = squash_component_tree(component_tree)
        # Note that this list is different from self.components, which is used
        # solely by the parser and in pattern handler functions.

        # Initialize parser state variables again.
        self.parse_start()

        # Skip until the start of the block parameter definition.
        found_parameter_block = False

        for line in source_array:
            self.line_no += 1
            line = line.rstrip()
            cns.append(line)
            if re.search('- begin block parameter definition -', line) is not None:
                found_parameter_block = True
                break

        # This error should have been catched by the parse() call above.
        assert found_parameter_block

        # Order between attributes and labels in front of parameter lines is not preserved.
        # Attributes always come before the label in our output. This shouldn't have any consequences.
        current_paragraph_lines = []
        current_attr_lines      = []

        # The reason we add some properties to the parser object instead of using it as a function-local variable
        # is that python's scoping issues do not allow for (non-global) variables from an outer scope to be
        # assigned to in a nested function. We want that flexibility.
        self.component_index = 0

        section_its = [
            {
                # This describes a component container (either a section or the virtual root block).
                # The first entry, inserted here, describes the root block.
                'component_index': None, # The root block is not a component.
                'level':           0,    # Section depth, measured in the amount of equals signs. The root block is at the highest level, 0.
                'has_access':      True, # All access levels have access to the root block.
                'repetitions':     [ form_data['instances'] ], # The root block can be seen as having 1 repetition.
                'repetition':      0,    # Current section repetition index. Always 0 for the root block.
                'child_index':     0,    # Index within the current repetition of this section to the current instance.
                # Note that the above value may not be used to access a child in the
                # components tree, as the index is not incremented for hidden
                # child components.

                'parser_state':    None, # Parser state saving is only needed for repeatable sections, the root block is not repeated.
            }
        ]

        # Instances of file parameters are added to this dictionary for mapping them with formdata['files'].
        file_parameter_instances = dict()


        def replace_repetition_placeholders(string, parameter_component_index=None, parameter_repetition=None, zero_based=False):
            """\
            Replace occurrences of repetition index number placeholders with repeat indices.

            If parameter_repetition is not None, the current parameter component
            will be selected from section_its[] and its placeholder will be replaced as well.
            """

            # Apply substitutions from outermost to innermost section.
            if len(section_its) > 1:
                for it in section_its[1:]:
                    section_component = components[it['component_index']]
                    if section_component['repeat']:
                        string = re.sub(section_component['repeat_index'], str(it['repetition'] if zero_based else it['repetition'] + 1), string)

            # Apply substitutions for the current parameter.
            if parameter_component_index is not None:
                parameter_component = components[parameter_component_index]
                string = re.sub(parameter_component['repeat_index'], str(parameter_repetition if zero_based else parameter_repetition + 1), string)

            return string

        def on_section_boundary(at_eof=False):
            """\
            Called when a new section is opened and at end-of-file.
            Handles section repetition and section depth traversal.

            The return value indicates whether the encountered section header
            should be printed at this time.
            """

            # Actual sections of level 1 can not exist due to the minimum amount
            # of equals signs for a section enforced by the parser being 2.
            # A value of 1 basically tells the writer to close or repeat all
            # component containers except for the virtual root block.
            new_level = 1 if at_eof else self.current_sections[-1]['level']

            # The current (deepest) section iterator.
            it = section_its[-1]

            # Are we leaving one or more sections?
            if new_level <= section_its[-1]['level']:

                # This can only happen at EOF or when we are within a section already.
                # TODO: Re-check with models that do not use sections.
                assert at_eof or len(section_its) > 1

                if self.line_no == it['parser_state']['line_no']:
                    # This indicates that we just jumped back for a repetition.
                    # Continue without handling the section boundary.
                    return True

                # Have we entered a new repetition?
                jumped_for_repetition = False

                # As long as there are sections left to close and we haven't
                # entered a new repetition...
                while new_level <= section_its[-1]['level'] and not jumped_for_repetition:

                    if section_its[-1]['repetition'] < len(section_its[-1]['repetitions']) - 1:

                        # Enter a new repetition for this section.
                        section_its[-1]['repetition'] += 1
                        section_its[-1]['child_index'] = 0

                        self.printv(
                            'Jumping from line ' + str(self.line_no)
                            + ' to '             + str(section_its[-1]['parser_state']['line_no'] - 1)
                        )

                        # Restore parser state.
                        self.component_index  = section_its[-1]['component_index']-1
                        self.line_no          = section_its[-1]['parser_state']['line_no'] - 1
                        self.current_sections = section_its[-1]['parser_state']['current_sections']
                        self.components       = section_its[-1]['parser_state']['components']

                        jumped_for_repetition = True

                    else:
                        # No repetitions left, close the section and move on.
                        section_its.pop()
                        section_its[-1]['child_index'] += 1

                if jumped_for_repetition:
                    # Tell the caller not to print the section header that ends this section yet.
                    return False

                # Note that parameters can not exist directly after a section end.
                # After a section end either a section start or an EOF MUST follow.

            if at_eof:
                # Nothing to do here.
                return False

            if components[self.component_index]['hidden']:
                # We shouldn't have to create an iterator for hidden sections. -- TODO: double-check
                return True

            # The iterator for the parent of the section we are entering.
            it = section_its[-1]

            assert new_level > section_its[-1]['level']

            if len(it['repetitions']):
                instance = it['repetitions'][it['repetition']][it['child_index']]

                # Check whether the current component index number matches with the next component number in form_data.
                if instance['component_index'] != self.component_index:
                    self.error(
                        'Missing or incorrect section instance in form data.'
                        + ' Expected component index ' + str(self.component_index)
                        + ' but found index ' + str(instance['component_index']) + ' instead'
                    )

                # This would indicate a bug in the parser.
                assert components[self.component_index]['type'] == 'section'

            else:
                # This is a (child of a) section that has zero repetitions.
                instance = None

            #print(self.line_no, it['child_index'], instance['component_index'], self.component_index)

            component = components[self.component_index]

            if instance is not None:
                # Check if the repetition count is within the allowed bounds.
                if component['repeat']:
                    if (component['repeat_min'] is not None
                            and len(instance['repetitions']) < component['repeat_min']):
                        self.error(
                            'Not enough repetitions for section "'
                            + component['label'] + '" found, require at least '
                            + str(component['repeat_min'])
                        )
                    elif (component['repeat_max'] is not None
                            and len(instance['repetitions']) > component['repeat_max']):
                        self.error(
                            'Too many repetitions for section "'
                            + component['label'] + '" found, only '
                            + str(component['repeat_max']) + ' allowed'
                        )
                elif len(instance['repetitions']) != 1:
                    # Repetition is not allowed, require exactly one value.
                    self.error(
                        'Incorrect amount of repetitions for section "'
                        + component['label'] + '", only one allowed'
                    )

            # If False, the submitted form level does not have access to this section.
            # Use the default amount of repetitions and use default values for everything.
            has_access_to_this_section = (
                it['has_access']
                and form_data['level'] in component['accesslevels']
            )

            # Add a new section iterator.
            section_its.append({
                'component_index': self.component_index,
                'level':           new_level,
                'has_access':      has_access_to_this_section,
                'repetitions':     instance['repetitions'] if instance is not None else [],
                'repetition':      0,
                'child_index':     0,
                'parser_state': {
                    # Save the parser's state so we can easily jump back if we need to repeat this section.
                    'line_no':          self.line_no,
                    'current_sections': self.current_sections,
                    'components':       self.components,
                }
            })

            # If this section instantiation doesn't have a single repetition, don't print it at all.
            return (len(section_its[-1]['repetitions']) > 0)

        while True:
            # If at EOF, close or repeat any open sections.
            if self.line_no >= len(source_array):
                on_section_boundary(at_eof=True)
                # on_section_boundary() may jump to another line number, check again.
                if self.line_no >= len(source_array):
                    break

            line          = source_array[self.line_no]
            self.line_no += 1

            # TODO: This kills trailing spaces in our output, check if this is a problem.
            line = line.rstrip()

            if len(line):
                # Call pattern handler functions like parse() does.
                line_type = self.call_handlers(line)

                # Did the parser parse the line succesfully?
                if line_type is None:
                    # No need to warn about this, we already warned the user in the parse() call above.
                    self.current_paragraph = ''
                    # Output saved paragraph lines even though they're not saved as a component.
                    cns.extend(current_paragraph_lines)
                    current_paragraph_lines = []
                    #cns.append('')
                    # Add the possibly erroneous input line to the CNS output anyway.
                    cns.append(line)

                elif line_type in set(['section_start', 'parameter']):
                    # This line defines a component.

                    # Attributes describing the current component.
                    component = components[self.component_index]

                    # The deepest section we're currently in.
                    it = section_its[-1]

                    if line_type == 'section_start':
                        if on_section_boundary():
                            # Never output section attributes.
                            #cns.extend(current_attr_lines)
                            new_line = replace_repetition_placeholders(line)
                            cns.append(new_line)

                        current_attr_lines = []

                        if component['hidden']:
                            current_paragraph_lines = []
                            current_attr_lines = []

                            self.component_index += 1

                            # Hidden components are never instantiated or added to form_data; Don't increment that index.
                            #it['child_index'] += 1
                            continue

                    elif line_type == 'parameter':
                        if component['hidden']:
                            cns.extend(current_attr_lines)
                            cns.extend(current_paragraph_lines)

                            # Fill in repetition placeholders in the parameter name.
                            new_line = re.sub(
                                r'(?<=\{===>\})\s*([a-zA-Z0-9_]+)(?==[^;]*?;)',
                                lambda match: ' ' + replace_repetition_placeholders(match.group(1)),
                                line
                            )

                            cns.append(new_line)

                            current_paragraph_lines = []
                            current_attr_lines = []

                            self.component_index += 1
                            #it['child_index'] += 1
                            continue

                        else:
                            # Does our parent section exist at least once?
                            if len(it['repetitions']):
                                # Yes. Get this parameter's instance from the current section repetition.
                                instance = it['repetitions'][it['repetition']][it['child_index']]

                                # Check whether the current component index number matches with the next component number in form_data.
                                if instance['component_index'] != self.component_index:
                                    self.error(
                                        'Missing or incorrect parameter instance in form data.'
                                        + ' Expected component index ' + str(self.component_index)
                                        + ' but found index ' + str(instance['component_index']) + ' instead'
                                    )

                                # This would indicate a bug in the parser.
                                assert component['type'] == 'parameter'

                                # Check if the repetition count is within the allowed bounds.
                                if component['repeat']:
                                    if (component['repeat_min'] is not None
                                            and len(instance['repetitions']) < component['repeat_min']):
                                        self.error(
                                            'Not enough values for parameter "'
                                            + component['name'] + '" found, require at least '
                                            + str(component['repeat_min'])
                                        )
                                    elif (component['repeat_max'] is not None
                                            and len(instance['repetitions']) > component['repeat_max']):
                                        self.error(
                                            'Too many values for parameter "'
                                            + component['name'] + '" found, only '
                                            + str(component['repeat_max']) + ' allowed'
                                        )
                                elif len(instance['repetitions']) != 1:
                                    # Repetition is not allowed, require exactly one value.
                                    self.error(
                                        'Incorrect amount of values for parameter "'
                                        + component['name'] + '", only one allowed'
                                    )


                                # If False, the submitted form level does not have access to this parameter.
                                # Use the default amount of repetitions and use default values for everything.
                                has_access_to_this_parameter = (
                                    it['has_access']
                                    and form_data['level'] in component['accesslevels']
                                )


                                if str(self.component_index) not in file_parameter_instances:
                                    file_parameter_instances[str(self.component_index)] = []

                                if component['datatype'] == 'file':
                                    this_file_parameter_repetitions = []
                                    file_parameter_instances[str(self.component_index)].append(this_file_parameter_repetitions)
                                    local_instance_index = len(file_parameter_instances[str(self.component_index)]) - 1

                                # Use minimum repetition count if the submitted form has no access to this parameter.
                                repetitions = (
                                    instance['repetitions']
                                        if has_access_to_this_parameter
                                        else
                                            [None] * component['repeat_min']
                                                if component['repeat']
                                                else [None] * 1
                                )

                                for repetition_index, repetition in enumerate(repetitions):
                                    cns.extend(current_attr_lines)
                                    cns.extend(current_paragraph_lines)

                                    # Parameter is a file, add it to the file_map if a file exists.
                                    if component['datatype'] == 'file' and has_access_to_this_parameter:
                                        if (str(self.component_index) in form_data['files']
                                                and str(local_instance_index) in form_data['files'][str(self.component_index)]
                                                and str(repetition_index) in form_data['files'][str(self.component_index)][str(local_instance_index)]):

                                            # An uploaded file exists for this file parameter component.

                                            filename_original = form_data['files'][str(self.component_index)][str(local_instance_index)][str(repetition_index)]['name']

                                            filename_new = (
                                                replace_repetition_placeholders(component['name'], self.component_index, repetition_index)
                                                    if   component['repeat']
                                                    else replace_repetition_placeholders(component['name'])
                                            )

                                            # Grab the desired extension from the component's default value.
                                            match = re.search(r'\.(.*)$', component['default'])
                                            if match is not None:
                                                filename_new += '.' + match.group(1)

                                            aux_file_map[filename_original] = filename_new

                                            # This repetition field must contain the filename as provided by the user
                                            # (and may be prefixed with C:\fakepath\ by a web browser).
                                            # We do not use it however.
                                            assert len(repetition)

                                            # Instead we replace the value with the actual name the file will have after the rename.
                                            repetition = filename_new

                                    new_line = line

                                    if repetition is None:
                                        # No access, minimum amount of repetitions.
                                        repetition = (
                                            replace_repetition_placeholders(component['default'], self.component_index, repetition_index)
                                                if   component['repeat']
                                                else replace_repetition_placeholders(component['default'])
                                        )

                                    # Escape special characters.

                                    # Python has some issues with backslashes in regular expressions.
                                    # The following converts single backslashes (\) into escaped backslashes (\\).
                                    repetition = re.sub(r'\\', r'\\\\\\\\', repetition)

                                    # Escape double quotes
                                    repetition = re.sub(r'"',  r'\"',  repetition)

                                    # Is the parameter value in the template enclosed by quotes?
                                    if re.search(r'(?<=(?<!\{|=)=)(["' + '\'' + r'])[^;]*?\1(?=;)', new_line) is not None:
                                        # Always output double quotes.
                                        new_line = re.sub(r'(?<=(?<!\{|=)=)[^;]*?(?=;)', '"' + repetition + '"', new_line)
                                    else:
                                        new_line = re.sub(r'(?<=(?<!\{|=)=)[^;]*?(?=;)', repetition, new_line)

                                    new_line = re.sub(
                                        r'(?<=\{===>\})\s*([a-zA-Z0-9_]+)(?==[^;]*?;)',
                                        lambda match: ' ' + (
                                            replace_repetition_placeholders(match.group(1), self.component_index, repetition_index)
                                                if component['repeat']
                                                else replace_repetition_placeholders(match.group(1))
                                        ),
                                        new_line
                                    )

                                    cns.append(new_line)

                        current_paragraph_lines = []
                        current_attr_lines = []

                        it['child_index'] += 1

                    self.component_index += 1

                elif line_type == 'paragraph':
                    # A paragraph can be a component as well, but we don't yet know if this is actually a label.
                    current_paragraph_lines.append(replace_repetition_placeholders(line))

                elif line_type == 'hash_attributes' or line_type == 'plus_attributes':
                    current_attr_lines.append(line)

                else:
                    # Comments and other lines that don't need special handling.
                    cns.append(line)
            else:
                if len(self.current_paragraph):
                    # A single empty line can mark the end of a paragraph component.
                    cns.extend(current_paragraph_lines)
                    current_paragraph_lines = []
                    self.save_paragraph(self.current_paragraph)
                    self.current_paragraph = ''
                    self.component_index += 1

                cns.append('')
                continue

        del self.component_index

        self.parse_end()

        return cns, aux_file_map
