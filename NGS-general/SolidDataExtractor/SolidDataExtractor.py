#     SolidDataExtractor.py: get data about SOLiD sequencer runs
#     Copyright (C) University of Manchester 2011 Peter Briggs
#
########################################################################
#
# SolidDataExtractor.py
#
#########################################################################

"""SolidDataExtractor

Provides classes for extracting data about SOLiD runs from directory
structure, data files and naming conventions."""

#######################################################################
# Import modules that this module depends on
#######################################################################

import sys,os
import string
import logging

#######################################################################
# Class definitions
#######################################################################

class SolidRun:
    """Describe a SOLiD run.

    The SolidRun class provides an interface to data about a SOLiD
    run. It analyses the SOLiD data directory to look for run
    definitions, statistics files and primary data files.

    It uses the same terminology as the SETS interface and the data
    files produced by the SOLiD instrument, so a run contains
    'samples' and each sample contains one or more 'libraries'.

    One initialised, access the data about the run via the SolidRun
    object's properties:

    run_dir: directory with the run data
    run_name: name of the run e.g. solid0123_20130426_FRAG_BC
    run_info: a SolidRunInfo object with data derived from the run name
    run_definition: a SolidRunDefinition object with data extracted from
      the run_definition.txt file
    samples: a list of SolidSample objects representing the samples in
      the run
    """

    def __init__(self,solid_run_dir):
        """Create and populate a new SolidRun instance.

        solid_run_dir is the top-level directory holding the files
        generated by the SOLiD run e.g.
        /path/to/SOLiD/data/solid0123_20130426_FRAG_BC
        """

        # Initialise
        self.run_dir = None
        self.run_name = None
        self.run_info = None
        self.run_definition = None
        self.samples = []

        # Basic data the supplied directory name
        if not os.path.isdir(os.path.abspath(solid_run_dir)):
            # Directory not found
            return

        self.run_dir = os.path.abspath(solid_run_dir)
        self.run_name = self.run_dir.strip(os.sep).split(os.sep)[-1]
        self.run_info = SolidRunInfo(self.run_name)

        # Locate and process the run definition file
        self.run_defn_filn = os.path.join(self.run_dir,
                                          self.run_name+"_run_definition.txt")
        if os.path.isfile(self.run_defn_filn):
            self.run_definition = SolidRunDefinition(self.run_defn_filn)
        else:
            # Unable to find run definition
            print "WARNING no run definition file"
            return

        # Determine samples and libraries
        for i in range(0,self.run_definition.nSamples()):
            sample_name = self.run_definition.getDataItem('sampleName',i)
            library_name = self.run_definition.getDataItem('library',i)

            # Barcoded samples
            #
            # Look for content in the "barcodes" column for the library
            # in the run definition file
            #
            # There may be several barcoded samples
            # Example barcode items:
            # --> "1"
            # --> "1,2,3,4,5,6,7,8"
            # (or could be empty)
            try:
                barcodes = self.run_definition.getDataItem('barcodes',i)
            except IndexError:
                barcodes = ''
            ##print "%s: barcodes: %s" % (library_name,barcodes)
            library_is_barcoded = (barcodes != '' and barcodes)
            if library_is_barcoded:
                barcodes = barcodes.strip('"').split(',')

            # Look for the directory with the results
            #
            # There should be a symlink "results" that will
            # point to the actual results directory
            results = os.path.join(self.run_dir,sample_name,'results')
            if os.path.islink(results):
                ##if library_is_barcoded:
                    # For barcoded samples, data will be a subdirectory
                    # of the "libraries" directory
                libraries_dir = os.path.join(self.run_dir,
                                             sample_name,
                                             os.readlink(results),
                                             'libraries')
                ##else:
                    # For non-barcoded samples, data is directly
                    # below the "results" directory
                    ##libraries_dir = os.path.join(self.run_dir,
                    ##                             sample_name,
                    ##                             os.readlink(results))
                    
                ##print "%s" % libraries_dir
            else:
                libraries_dir = None

            if not sample_name in [s.name for s in self.samples]:
                # New sample
                sample = SolidSample(sample_name,parent_run=self)
                self.samples.append(sample)
                # Locate and process barcode statistics
                if libraries_dir:
                    for f in os.listdir(libraries_dir):
                        if f.startswith("BarcodeStatistics"):
                            barcode_stats_filn = os.path.join(libraries_dir,f)
                            sample.barcode_stats = \
                                SolidBarcodeStatistics(barcode_stats_filn)
                            break
                else:
                    print "WARNING no libraries dir %s" % libraries_dir
                    
            # Store the library
            library = sample.addLibrary(library_name)
            library.is_barcoded = library_is_barcoded

            # Locate data files for this library
            #
            # This is a bit convoluted but essentially we're
            # looking for a "primary.XXXXXXX" subdirectory of the
            # <library> subdirectory, which contains a "reject"
            # subdirectory
            # The "reads" subdirectory parallel to the "reject"
            # dir has the data we want
            
            # Check for directory with result files
            if libraries_dir:
                this_library_dir = os.path.join(libraries_dir,library.name)
                if not os.path.isdir(this_library_dir):
                    this_library_dir = None
            else:
                this_library_dir = None

            # Locate the primary data
            got_primary_data = False
            ambiguity_error = False
            if this_library_dir:
                ##print "Library dir: %s..." % this_library_dir
                # Iterate over available directories
                for d in os.listdir(this_library_dir):
                    ##print "--> Library %s subdir: %s" % (library_name,d)
                    reject = os.path.join(this_library_dir,d,"reject")
                    reads = os.path.join(this_library_dir,d,"reads")
                    reports = os.path.join(this_library_dir,d,"reports")
                    # Check that we have 'reject', 'reads' and 'reports'
                    if os.path.isdir(reject) and \
                            os.path.isdir(reads) and \
                            os.path.isdir(reports):
                        ##print "---> has all of reads, reject and reports"
                        # Check for csfasta and qual files
                        csfasta = None
                        qual = None
                        for f in os.listdir(reads):
                            ext = os.path.splitext(f)[1]
                            if ext == ".csfasta":
                                csfasta = os.path.abspath( \
                                    os.path.join(reads,f))
                            elif ext == ".qual":
                                qual = os.path.abspath( \
                                    os.path.join(reads,f))
                        # Sanity check names for barcoded samples
                        # Look for "F3" in the file names
                        if library.is_barcoded:
                            if csfasta:
                                if csfasta.rfind('_F3_') < 0:
                                    csfasta = None
                            if qual:
                                if qual.rfind('_F3_') < 0:
                                    qual = None
                        # Store primary data
                        if csfasta and qual:
                            if got_primary_data:
                                ambiguity_error = True
                            else:
                                library.csfasta = csfasta
                                library.qual = qual
                                got_primary_data = True
                                ##print "-----> Located primary data"

            if not got_primary_data:
                print "WARNING unable to locate primary data for %s" % \
                    library
            elif ambiguity_error:
                print "WARNING ambigiuous location for primary data for %s" % \
                    library

    def fetchLibraries(self,sample_name='*',library_name='*'):
        """Retrieve libraries based on sample and library names

        Supplied names can be exact matches or simple patterns (using trailing
        '*'s as wildcards). '*' matches all names.

        Returns a list of matching SolidLibrary objects.
        """
        matching_libraries = []
        for sample in self.samples:
            if match(sample_name,sample.name):
                # Found a matching sample
                for library in sample.libraries:
                    if match(library_name,library.name):
                        # Found a matching library
                        logging.debug("Located sample and library: %s/%s" %
                                      (sample.name,library.name))
                        matching_libraries.append(library)
        if len(matching_libraries) == 0:
            logging.debug("No libraries matched to %s/%s in %s" % (sample_name,library_name,
                                                                   self.run_dir))
        # Finished
        return matching_libraries

    def slideLayout(self):
        """Return description of the slide layout

        Return a string describing the slide layout for the run based on
        the number of samples in the run, e.g. "Whole slide", "Quads",
        "Octets" etc.
        """
        nsamples = len(self.samples)
        if nsamples == 1:
            return "Whole slide"
        elif nsamples == 4:
            return "Quads"
        elif nsamples == 8:
            return "Octets"
        else:
            logging.warning("Undefined layout for %s samples" % len(self.samples))
            return "Undefined layout"

    def __nonzero__(self):
        """Implement nonzero built-in

        SolidRun object is False if the source directory doesn't
        exist, or if basic data couldn't be loaded."""
        if not self.run_name:
            return False
        elif not self.run_info:
            return False
        elif not self.run_definition:
            return False
        else:
            return True

class SolidSample:
    """Store information about a sample in a SOLiD run.

    A sample has a name and contains a set of libraries.
    The information about the sample can be accessed via the
    following properties:

    name: the sample name
    libraries: a list of SolidLibrary objects representing the libraries
      within the sample
    projects: a list of SolidProject objects representing groups of
      related libraries within the sample
    barcode_stats: a SolidBarcodeStats with data extracted from the
      BarcodeStatistics file (or None, if no file was available)
    parent_run: the parent SolidRun object, or None.
    """

    def __init__(self,name,parent_run=None):
        """Create a new SolidSample instance.

        Inputs:
          name: name of the sample (e.g. AS_XC_pool)
          parent_run: (optional) the parent SolidRun object
        """
        self.name = name
        self.libraries = []
        self.libraries_dir = None
        self.barcode_stats = None
        self.projects = []
        self.parent_run = parent_run

    def __repr__(self):
        """Implement __repr__ built-in

        Return string representation for the SolidSample -
        i.e. the sample name."""
        return str(self.name)

    def addLibrary(self,library_name):
        """Associate a library with the sample

        The supplied library is added to the list of libraries
        associated with the sample, if it's not already in the
        list.

        Input:
          library_name: name of the library to add

        Returns:
          New or existing SolidLibrary object representing the
          library.
        """
        # Check if the library is already in the list
        library = self.getLibrary(library_name)
        if not library:
            # Create new library object and add to list
            library = SolidLibrary(library_name,parent_sample=self)
            self.libraries.append(library)
            # Keep libraries in order
            self.libraries = sorted(self.libraries,
                                    key=lambda l: (l.prefix,l.index))
        # Deal with projects
        project_name = library.initials
        project = self.getProject(project_name)
        if not project:
            # Create new project
            project = SolidProject(project_name)
            self.projects.append(project)
        # Add the library to the project
        project.addLibrary(library)
        # Return library object
        return library

    def getLibrary(self,library_name):
        """Return library object matching a library name.

        If library_name matches a stored library name then return
        the matching library object, otherwise return None.
        """
        for library in self.libraries:
            if library.name == library_name:
                return library
        # Not found 
        return None

    def getProject(self,project_name):
        """Return project object matching a project name.

        If project_name matches a stored project name then return
        the matching project object, otherwise return None.
        """
        for project in self.projects:
            if project.name == project_name:
                return project
        # Not found
        return None

class SolidLibrary:
    """Store information about a SOLiD library.

    The following properties hold data about the library:

    name: the library name
    initials: the experimenter's initials
    prefix: the library name prefix (i.e. name without the trailing
      numbers)
    index_as_string: the trailing numbers from the name, as a string
      (preserves any leading zeroes)
    index: the trailing numbers from the name as an integer
    csfasta: full path to the csfasta file for the library
    qual: full path to qual file for the library
    parent_sample: parent SolidSample object, or None.
    """

    def __init__(self,name,parent_sample=None):
        """Create a new SolidLibrary instance.

        Inputs:
          name: name of the library (e.g. AS_07)
          parent_sample: (optional) parent SolidSample object
        """
        # Name
        self.name = str(name)
        # Name-based information
        self.initials = extract_initials(self.name)
        self.prefix = extract_prefix(self.name)
        self.index_as_string = extract_index(self.name)
        if self.index_as_string == '':
            self.index = None
        else:
            self.index = int(self.index_as_string.lstrip('0'))
        # Barcoding
        self.is_barcoded = False
        # Associated data files
        self.csfasta = None
        self.qual = None
        # Parent sample
        self.parent_sample = parent_sample

    def __repr__(self):
        """Implement __repr__ built-in

        Return string representation for the SolidLibrary -
        i.e. the library name."""
        return str(self.name)

class SolidProject:
    """Hold information about a SOLiD 'project'

    A SolidProject object holds a collection of libraries which
    together constitute a 'project'.

    The definition of a 'project' is quite loose in this context:
    essentially it's a grouping of libraries within a sample.
    Typically the grouping is by the initial letters of the library
    name e.g. DR for DR1, EP for EP_NCYC2669 - but this determination
    is made at the application level.

    Libraries are added to the project via the addLibrary method.
    Data about the project can be accessed via the following
    properties:

    name: the project name (supplied on object creation)
    libraries: a list of libraries in the project

    Also has the following methods:

    getSample(): returns the parent SolidSample
    getRun(): returns the parent SolidRun
    isBarcoded(): returns boolean indicating whether the libraries
      in the sample are barcoded
    """

    def __init__(self,name,run=None,sample=None):
        """Create a new SolidProject object.

        name: the name of the project.
        run: (optional) the parent SolidRun for the project
        sample: (optional) the parent SolidSample for the project
        """
        self.name = name
        self.libraries = []

    def addLibrary(self,library):
        """Add a library to the project.

        library: the name of the library to add.
        """
        self.libraries.append(library)

    def getSample(self):
        """Return the parent sample for the project.
        """
        if len(self.libraries):
            return self.libraries[0].parent_sample
        else:
            return None

    def getRun(self):
        """Return the parent run for the project.
        """
        parent_sample = self.getSample()
        if parent_sample:
            return parent_sample.parent_run

    def isBarcoded(self):
        """Return boolean indicating if the libraries are barcoded.

        If all libraries in the project are barcoded then return
        True, otherwise return False if at least one isn't barcoded
        (or if there are no libraries associated with the project).
        """
        # If any library is not barcoded, return False
        for library in self.libraries:
            if not library.is_barcoded:
                return False
        # Will be True as long as there's at least one library
        return len(self.libraries) > 0

    def getLibraryNamePattern(self):
        """Return wildcard pattern matching all library names in the project.

        Find the longest pattern which matches all the library names in
        the project. For example if the project contains four libraries
        PB1, PB2, PB3 and PB4 then return 'PB*'.

        If the project only contains one library then the pattern will be
        the single name without wildcard characters.
        """
        pattern = None
        for library in self.libraries:
            if pattern is None:
                pattern = library.name
            else:
                new_pattern = []
                for i in range(min(len(pattern),len(library.name))):
                    if pattern[i] != library.name[i]:
                        if len(new_pattern) < len(library.name):
                            new_pattern.append('*')
                        pattern = ''.join(new_pattern)
                        break
                    else:
                        new_pattern.append(pattern[i])
        return pattern

    def getProjectName(self):
        """Return a name for the project.

        Typically this is the same as the project name assigned when
        the project was created, unless the project essentially maps
        to an entire sample (i.e. all the libraries in the parent
        sample are also in the project) - then the project name is
        the sample name.
        """
        if len(self.getSample().libraries) == len(self.libraries):
            return self.getSample().name
        else:
            return self.name

class SolidRunInfo:
    """Extract data about a run from the run name
        
    Run names are of the form 'solid0123_20130426_FRAG_BC_2'
    
    This class analyses the name and breaks it down into components
    that can be accessed as object properties, specifically:
    
    name: the supplied run name
    instrument: the instrument name e.g. solid0123
    datestamp: e.g. 20130426
    is_fragment_library: True or False
    is_barcoded_sample: True or False
    flow_cell: 1 or 2
    date: datestamp reformatted as DD/MM/YY
    id: the run name without any flow cell identifier
    """

    def __init__(self,run_name):
        """Create and initialise a new SolidRunInfo instance

        Input
          run_name: the name of the run, e.g. solid0123_20130426_FRAG_BC_2
                    (not a path to a directory)
        """
        # Initialise
        self.name = run_name
        self.id = None
        self.instrument = None
        self.datestamp = None
        self.is_fragment_library = False
        self.is_barcoded_sample = False
        self.flow_cell = 1
        self.date = None
        #
        data = str(run_name).split('_')
        #
        # Basic info
        self.instrument = data[0]
        self.datestamp = data[1]
        #
        # Fragment library
        if 'FRAG' in data:
            self.is_fragment_library = True
        #
        # Barcoded sample
        if 'BC' in data:
            self.is_barcoded_sample = True
        #
        # Flow cell
        if data[-1] == '2':
            self.flow_cell = 2
        #
        # I.D.
        self.id = "%s_%s" % (self.instrument,
                             self.datestamp)
        if self.is_fragment_library:
            self.id += "_FRAG"
        if self.is_barcoded_sample:
            self.id += "_BC"
        #
        # Date
        if len(self.datestamp) == 8:
            self.date = "%s/%s/%s" % (self.datestamp[6:8],
                                      self.datestamp[4:6],
                                      self.datestamp[2:4])

    def __repr__(self):
        """Implement __repr__ built in for str etc
        """
        return str(self.dict())

    def dict(self):
        """Return extracted data as a dictionary
        """
        return { 'name': self.name,
                 'instrument': self.instrument,
                 'datestamp': self.datestamp,
                 'flow_cell': self.flow_cell,
                 'is_fragment_library': self.is_fragment_library,
                 'is_barcoded_sample': self.is_barcoded_sample}

    def summary(self):
        """Print summary of the data extracted from the name
        """
        for item in self.dict():
            print "%s: %s" % (' '.join(item.split('_')).title(),
                              str(self.dict()[item]))

class SolidRunDefinition:
    """Store data from a SOLiD run definition file.

    The data file name must be provided as run_definition_file;
    the instance is automatically populated from this file."""

    def __init__(self,run_definition_file):
        """Create a new SolidRunDefinition object."""
        self.file = run_definition_file
        self.header_fields = []
        self.data = []
        try:
            self.populate()
        except IOError, ex:
            print "SolidRunDefinition: IOError exception: "+str(ex)

    def __nonzero__(self):
        """Implement the built-in __nonzero__ method"""
        return len(self.data) != 0

    def fields(self):
        """Return list of fields"""
        return self.header_fields

    def nSamples(self):
        """Return the number of samples"""
        return len(self.data)

    def getData(self,i):
        """Return row of data"""
        return self.data[i]

    def getDataItem(self,field,i):
        """Return data item from specified row

        field must be one of the fields read in from the file,
        and i must be a valid row index."""
        try:
            pos = self.header_fields.index(field)
        except ValueError:
            print "%s not found" % field
            return None
        return self.data[i][pos]

    def populate(self):
        """Populate the SolidRunDefiniton object."""
        # Initialise
        got_header = False
        # Open the file
        f = open(self.file,'r')
        for line in f:
            # Look for header line
            # This looks like:
            # sampleName	sampleDesc	spotAssignments	primarySetting	library	application	secondaryAnalysis	multiplexingSeries	barcodes
            if line.startswith("sampleName"):
                for field in line.strip().split('\t'):
                    self.header_fields.append(field)
                got_header = True
            elif got_header:
                # Deal with information under the header
                data = line.strip().split('\t')
                self.data.append(data)
        # Finished
        f.close()

class SolidBarcodeStatistics:
    """Store data from a SOLiD BarcodeStatistics file"""

    def __init__(self,barcode_statistics_file):
        """Create a new SolidBarcodeStatistics object"""
        self.file = barcode_statistics_file
        self.header = None
        self.data = []
        try:
            self.populate()
        except IOError, ex:
            print "SolidBarcodeStatistics: IOError exception: "+str(ex)

    def __nonzero__(self):
        """Implement the __nonzero__ built-in"""
        return len(self.data) != 0

    def populate(self):
        """Populate the SolidBarcodeStatistics object.
        """
        got_header = False
        f = open(self.file,'r')
        for line in f:
            if got_header:
                data = line.strip().split('\t')
                self.data.append(data)
            elif line.startswith('##'):
                self.header = line.strip().strip('#').split('\t')
                got_header = True
        f.close()

    def header(self):
        """Return list of header fields"""
        return self.header

    def nRows(self):
        """Return the number of rows"""
        return len(self.data)

    def getData(self,i):
        """Return row of data"""
        return self.data[i]

    def getDataItem(self,field,i):
        """Return data item from specified row

        field must be one of the fields read in from the file,
        and i must be a valid row index."""
        try:
            pos = self.header.index(field)
        except ValueError:
            print "%s not found" % field
            return None
        return self.data[i][pos]

    def getDataByName(self,name):
        """Return a row of data matching 'name'
        """
        for data in self.data:
            if data[0] == name:
                return data
        return None

#######################################################################
# Module Functions
#######################################################################

def extract_initials(library):
    """Given a library or library name, extract the experimenter's initials.

    The initials are normally the first letters at the start of the
    library name e.g. 'DR' for 'DR1', 'EP' for 'EP_NCYC2669', 'CW' for
    'CW_TI' etc
    """
    initials = []
    for c in str(library):
        if c.isalpha():
            initials.append(c)
        else:
            break
    return ''.join(initials)
        
def extract_prefix(library):
    """Given a library name, extract the prefix.

    The prefix is the library name with any trailing numbers
    removed, e.g. 'LD_C' for 'LD_C1'"""
    return str(library).rstrip(string.digits)

def extract_index(library):
    """Given a library name, extract the index.

    The index consists of the trailing numbers from the library
    name. It is returned as a string, to preserve any leading
    zeroes, e.g. '1' for 'LD_C1', '07' for 'DR07' etc"""
    index = []
    chars = [c for c in str(library)]
    chars.reverse()
    for c in chars:
        if c.isdigit():
            index.append(c)
        else:
            break
    index.reverse()
    return ''.join(index)

def match(pattern,word):
    """Check if word matches pattern

    patterns can be simple glob-like strings (i.e. using trailing '*' to
    indicate wildcard) or exact words."""
    if not pattern or pattern == '*':
        # No pattern/wildcard, matches everything
        return True
    # Only simple patterns considered for now
    if pattern.endswith('*'):
        # Match the start
        return word.startswith(pattern[:-1])
    else:
        # Match the whole word exactly
        return (word == pattern)

#######################################################################
# Main program
#######################################################################

if __name__ == "__main__":

    if len(sys.argv) != 2:
        # Example input /home/pjb/SOLiD_meta_data/solid0123_20130426_FRAG_BC
        print "Usage: python %s <solid_run_dir>" % sys.argv[0]
        sys.exit()

    # First argument is a directory name
    run_dir = sys.argv[1]
    print "Run dir: %s" % run_dir

    # Set up a SolidRun class
    run = SolidRun(run_dir)
    if not run:
        print "Error loading run data"
        sys.exit(1)

    # Print summary of run information
    run.run_info.summary()

    # Report run data
    if not run.run_definition:
        print "Failed to get run definition data"
        sys.exit()
    print str(run.run_definition.fields())

    # Report info for each sample
    for sample in run.samples:

        print "=========================================="
        print "Sample: %s" % sample
        print "=========================================="

        # Libraries and data files
        print "%i Libraries:" % len(sample.libraries)
        for library in sample.libraries:
            print "%s" % library
            # Files for this library
            csfasta = library.csfasta
            if csfasta:
                print "\t...%s%s" % (os.sep,os.path.basename(csfasta))
            qual = library.qual
            if qual:
                print "\t...%s%s" % (os.sep,os.path.basename(qual))
            # Associated barcode stats data
            # FIXME not very pretty at the moment
            if sample.barcode_stats:
                barcode_stats = sample.barcode_stats
                for i in range(0,barcode_stats.nRows()):
                    if barcode_stats.getDataItem('Library',i) == library:
                        print "\t%s\n\t%s" % \
                            (str(barcode_stats.header),
                             str(barcode_stats.getData(i)))
                        break
        # Total reads for all beads
        if sample.barcode_stats:
            print "\t"+str(sample.barcode_stats.getDataByName("All Beads"))
        else:
            print "\tBarcode statistics not available for %s" % sample

