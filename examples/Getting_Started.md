Getting Started
===============

*This guide assumes you're using [HADDOCK-WebUI](https://github.com/csmeele/HADDOCK-WebUI) as your form frontend*.

CNSParser consists of two scripts and one module.

The two scripts you will be using are cnstojson.py and jsontocns.py, of
which the latter does not yet exist at the time of writing.

First of all, help can be requested by calling either script with the
`-h` flag. Look into this usage output for all supported commandline
options.

Generating a model description
------------------------------

cnstojson.py is set up to be used in a pipeline, where it takes a CNS
file as its input and outputs model information and accesslevels to
standard output. Optionally, parameters can be given to specify output
filenames.

The JSON output is split into two parts, namely access level information
and the data model. By default, when no output files are specified, both
JSON datastructures are printed to standard output as two entries in an array.

HADDOCK-WebUI requires the model description and access levels to be
saved in separate files. You can achieve this by passing the `-l FILE`
and `-o FILE` options, where `FILE` is an output filename.

For example:

    ./cnstojson.py -w -l accesslevels.json -o model.json run.cns

It is recommended to always use the `-w` flag for cnstojson.py. This
enables all warnings, which can reveal unrecognized syntax, unlabeled
parameters, and section/parameter attributes that don't seem to make
sense.

HADDOCK-WebUI expects both JSON files to be stored in its `res/`
directory. If caching is enabled in `config.py`, the `mtime` of these
files are checked on each request to detect changes to the model.

Running the HADDOCK-WebUI server
--------------------------------

HADDOCK-WebUI can be run either locally, from the commandline, or under
apache, as a WSGI application.

Either way, the [Flask](http://flask.pocoo.org/) python module is
required for the application to run.

To run the server locally, execute the following command in the
application's root directory:

    ./run.py

By default, the applications listens for HTTP connections on port 5000.
Optionally, an address and port to listen on can be specified using the
`--host` and `--port` options.

For running the application under apache, make sure the WSGI module is
installed and loaded, and use the vhost template config under
`resources/` (in HADDOCK-WebUI's directory) to set up your vhost.


Filling in a new run.cns using the web form
-------------------------------------------

With the HADDOCK-WebUI application running, go to the webserver in your
web browser.

The web application will be running at
`http://<server-address>:<port>/form`.

You can add `?nocache` to the end of the URL to force a client-side
cache refresh.

The form page allows you to fill in parameter values, to add and remove
sections and values, and to upload files. Fill in the required
information and press `Submit` at the bottom of the page.

When the Submit button is pressed, the form will submit all filled in
information to the server in JSON format. The web-application will do
very basic validation and may reject the form, in which case an error
message will be sent back to the client.

If the form passes validation on the web-application level,
HADDOCK-WebUI creates a job directory in the directory specified in its
configuration. The uploaded JSON data as well as all uploaded files
(with temporary names) will be stored in this directory.

The script used for converting the form data back into a run.cns file is
currently not run automatically. To do this manually, run the following
command from the CNSParser directory:

    ./jsontocns.py -t template.cns job_directory

Where `template.cns` is the same file used for generating the JSON
model, and `job_directory` is the new job directory created by
HADDOCK-WebUI.

Debugging
---------

The model description can be dumped using the dumpmodel.py script. This
script recursively prints form components with some of their attributes.

dumpmodel.py can be called with a model.json file as its argument, or
used in a pipeline:

    ./dumpmodel.py model.json
    ./cnstojson.py -l /dev/null run.cns | ./dumpmodel.py

Add the `--verbose` flag to dumpmodel.py to get more information.

Additionally, the output of cnstojson.py (with warnings enabled) should
be checked for warnings.
