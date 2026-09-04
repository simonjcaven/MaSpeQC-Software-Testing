#import xml.etree.ElementTree as ET
from lxml import etree as ET
import datetime
import math
now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def set_pin_dict(pin_file):

    # creates a dict from .pin file
    
    with open(pin_file, 'r') as f:
        lines = f.readlines()
    
    # header
    colnames = lines.pop(0).strip().split('\t')

    # indexes for desired pin columns
    idx_specid = colnames.index("SpecId")
    idx_ntt = colnames.index("ntt")
    idx_nmc = colnames.index("nmc")
    idx_rt_score = colnames.index("delta_RT_loess_real") if "delta_RT_loess_real" in colnames else -1
    idx_spectral_sim = colnames.index("unweighted_spectral_entropy") if "unweighted_spectral_entropy" in colnames else -1

    # create the pin dict
    pin_spectrum_dict = {}
    for line in lines:
        fields = line.strip().split('\t')
        spec_id = fields[idx_specid][:-2]  # remove rank suffix for spectrum id as seen in pepXML
        ntt = int(fields[idx_ntt])
        nmc = int(fields[idx_nmc])
        rt_score = float(fields[idx_rt_score]) if idx_rt_score != -1 else math.nan
        spectral_sim = float(fields[idx_spectral_sim]) if idx_spectral_sim != -1 else math.nan

        pin_spectrum_dict[spec_id] = {"ntt":ntt, "nmc":nmc, "rt_score":rt_score, "spectral_sim":spectral_sim}
    
    return pin_spectrum_dict
       
def set_percolator_dict(min_prob, target_psms_file, decoy_psms_file):

    # creates a dict from .tsv files
    
    tsv_spectrum_dict = {}
    for tsv_path in [target_psms_file, decoy_psms_file]:
        with open(tsv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # header
        colnames = lines.pop(0).strip().split('\t')

        # indexes for desired tsv columns
        idx_psmid = colnames.index("PSMId")
        idx_pep = colnames.index("posterior_error_prob")
        idx_score = colnames.index("score")

        # create the tsv dict
        for line in lines:
            fields = line.strip().split('\t')
            spec_id = fields[idx_psmid][:-2]  # remove rank suffix for spectrum id as seen in pepXML

            # get pep prob
            try:
                pep = float(fields[idx_pep])
            except ValueError:
                pep = 1.0

            # filter on pep prob (FILTERS <spectrum_query>)
            if (1.0 - pep) >= min_prob:

                # get score
                try:
                    score = float(fields[idx_score])
                except ValueError:
                    score = 0.0

                tsv_spectrum_dict[spec_id] = {"pep":pep, "score":score}

    return tsv_spectrum_dict

def set_metadata_in_stream(xf, indent, filename):

    # analysis_summary element (percolator)
    analysis_summary = ET.Element('analysis_summary', attrib={"analysis": "percolator", "time": now})
    peptideprophet_summary = ET.Element('peptideprophet_summary', attrib={"min_prob": "0.5"})
    input_file = ET.Element('inputfile', attrib={"name": filename}) 
    peptideprophet_summary.append(input_file)
    analysis_summary.append(peptideprophet_summary)
    xf.write(indent)
    xf.write(analysis_summary)

    # analysis_summary element (database_refresh)
    analysis_summary = ET.Element('analysis_summary', attrib={"analysis": "database_refresh", "time": now})
    xf.write(indent)
    xf.write(analysis_summary)

    # analysis_summary element (interact)
    analysis_summary = ET.Element('analysis_summary', attrib={"analysis": "interact", "time": now})
    interact_summary = ET.Element('interact_summary', attrib={"filename": "lxml.pep.xml", "directory": ""})
    input_file = ET.Element('inputfile', attrib={"name": filename}) # create again , not needed?
    interact_summary.append(input_file)
    analysis_summary.append(interact_summary)
    xf.write(indent) 
    xf.write(analysis_summary)

    # dataset_derivation element 
    new_el = ET.Element('dataset_derivation', attrib={"generation_no": "0"})
    xf.write(indent) 
    xf.write(new_el)
    xf.write(indent)


def update_spectrum_query(tsv, pin, ns, sq, spectrum, prob):

        # search tags
        search_result = sq.find('.//{}search_result'.format(ns))
        search_hit = search_result.find('.//{}search_hit'.format(ns))
         
        # search hit variables
        massdiff = float(search_hit.attrib['massdiff'])
        calc_neutral_pep_mass = float(search_hit.attrib['calc_neutral_pep_mass'])

        # calculate isoptope mass difference (isotopic mass shift)
        gap = float('inf')
        isomassd = 0
        C13C12_MASSDIFF_U = 1.0033548378
        for isotope in range(-6, 7):
            current_gap = abs(massdiff - isotope * C13C12_MASSDIFF_U)
            if current_gap < gap:
                gap = current_gap
                isomassd = isotope

        if gap > 0.1:
            isomassd = 0

        # calculated variables
        prob = 1.0 - tsv[spectrum]["pep"]
        massd_val = (massdiff - isomassd * C13C12_MASSDIFF_U) * 1000000.0 / calc_neutral_pep_mass

        #### update the XML
        if not math.isnan(pin[spectrum]["spectral_sim"]):
            # update search hit with search scores (spectral sim)
            search_score = ET.Element('search_score')
            search_score.set('name', 'spectralsim')
            search_score.set('value', str(pin[spectrum]["spectral_sim"]))
            search_hit.append(search_score)

        if not math.isnan(pin[spectrum]["rt_score"]):
            # update search hit with search scores (rt score)
            search_score = ET.Element('search_score')
            search_score.set('name', 'rtscore')
            search_score.set('value', str(pin[spectrum]["rt_score"]))
            search_hit.append(search_score)

        # peptideprophet analysis result
        analysis_result = ET.Element('analysis_result')
        analysis_result.set('analysis', 'peptideprophet')

        # peptideprophet result summary
        result_summary = ET.Element('peptideprophet_result')
        result_summary.set('probability', str(prob))
        result_summary.set('all_ntt_prob', "({prob:f},{prob:f},{prob:f})".format(prob=prob))

        # search score summary
        search_score_summary = ET.Element('search_score_summary')

        # parameters for search score summary
        parameters = [
            ('fval', str(tsv[spectrum]["score"])),
            ('ntt', str(pin[spectrum]["ntt"])),
            ('nmc', str(pin[spectrum]["nmc"])),
            ('massd', str(massd_val)),
            ('isomassd', str(isomassd))
        ]

        # append to search score summary
        for name, value in parameters:
            parameter = ET.Element('parameter')
            parameter.set('name', name)
            parameter.set('value', value)
            search_score_summary.append(parameter)

        # append to document
        result_summary.append(search_score_summary)
        analysis_result.append(result_summary)
        search_hit.append(analysis_result)
        

def stream_and_write_xml(input_path, output_path, tsv, pin, prob):

    context = ET.iterparse(input_path, events=('start', 'end'))
    _, root = next(context) 
    indent_level_1 = "\n"
    ns = root.tag.split('}')[0] + '}'
    msms_summary = None

    with open(output_path, 'wb') as f:
        with ET.xmlfile(f, encoding='utf-8', buffered=False) as xf:

            xf.write_declaration()
            
            with xf.element(root.tag, attrib=root.attrib, nsmap=root.nsmap):

                # --- Insert Metadata ---
                set_metadata_in_stream(xf, indent_level_1, input_path)
                
                # Find the msms_run_summary element (main container)
                for event, elem in context:
                    if event == 'start' and elem.tag == f'{ns}msms_run_summary':
                        msms_summary = elem
                        break
                    else: # only reached if not well formed XML
                        xf.write(elem)
                        elem.clear()

                # Start again from msms_summary and process its children
                if msms_summary is not None:
                    with xf.element(msms_summary.tag, attrib=msms_summary.attrib):      

                        for event, elem in context:
                            # Process only direct children of msms_summary
                            if event == 'end' and elem.getparent() == msms_summary:

                                # Handle spectrum query elements based on tsv dict
                                if elem.tag == f'{ns}spectrum_query':
                                    spectrum = elem.attrib['spectrum']
                                    if spectrum in tsv:

                                        # --- Update spectrum query with new data and write to file ---
                                        update_spectrum_query(tsv, pin, ns, elem, spectrum, prob)
                                        xf.write(elem)
                                        elem.clear()
                                    else:
                                        # Skip writing this element and clear it from memory
                                        elem.clear()
                                else:
                                    # Serialize and stream other elements directly to the target file
                                    xf.write(elem)
                                    elem.clear()
                            # Stop when we hit the end tag of the msms_summary
                            elif event == 'end' and elem == msms_summary:
                                break
                                
                # Clear root 
                root.clear() 

                                     
if __name__ == "__main__":

    # files
    filename = 'QC_Proteomics_20260202203556_pos.pepXML'
    outfile = 'lxml.pep.xml'
    pin_file = 'QC_Proteomics_20260202203556_pos_edited.pin'
    target_psms_file = "targets.tsv"
    decoy_psms_file = "decoys.tsv"

    prob = 0.5

    pin_spectrum_dict = set_pin_dict(pin_file)
    tsv_spectrum_dict = set_percolator_dict(prob, target_psms_file, decoy_psms_file)
    stream_and_write_xml(filename, outfile, tsv_spectrum_dict, pin_spectrum_dict, prob)
    
   