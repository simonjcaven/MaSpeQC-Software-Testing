import xml.etree.ElementTree as ET
import datetime

filename = 'QC_Proteomics_20260202203556_pos.pepXML'
tree = ET.parse(filename)
root = tree.getroot()
now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

# get namespace qualifier
ns = root.tag.split('}')[0] + '}'

### ANALYSIS SUMMARIES

# dataset_derivation element 
dd_element = ET.Element('dataset_derivation')
dd_element.set('generation_no', '0')

#### insert after root 
root.insert(0, dd_element)

# analysis_summary element (interact)
analysis_summary = ET.Element('analysis_summary')
analysis_summary.set('analysis', 'interact')
analysis_summary.set('time',now)

# interact summary element
interact_summary = ET.Element('interact_summary')
interact_summary.set('filename', 'test.pep.xml') # full pathname to output file (eg.converted)
interact_summary.set('directory','')

# input file element
input_file = ET.Element('inputfile')
input_file.set('name', filename) # full pathname

# append to parent
interact_summary.append(input_file)
analysis_summary.append(interact_summary)

#### insert after root 
root.insert(0, analysis_summary)

# analysis_summary element (database_refresh)
analysis_summary = ET.Element('analysis_summary')
analysis_summary.set('analysis', 'database_refresh')
analysis_summary.set('time',now)

#### insert after root 
root.insert(0, analysis_summary)

# analysis_summary element (percolator)
analysis_summary = ET.Element('analysis_summary')
analysis_summary.set('analysis', 'percolator')
analysis_summary.set('time',now)

# peptideprophet summary element
peptideprophet_summary = ET.Element('peptideprophet_summary')
peptideprophet_summary.set('min_prob', '0.5')

# input file element
input_file = ET.Element('inputfile')
input_file.set('name', filename) # full pathname

# append to parent
peptideprophet_summary.append(input_file)
analysis_summary.append(peptideprophet_summary)

#### insert after root 
root.insert(0, analysis_summary)

#### LOOP over all <spectrum_query> elements 
for sq in root.findall('.//{}spectrum_query'.format(ns)):
    print(sq.attrib['spectrum'])

# write to new file
ET.register_namespace('', 'http://regis-web.systemsbiology.net/pepXML')
ET.indent(root, space="  ")
tree.write('test.pep.xml', encoding='utf-8')