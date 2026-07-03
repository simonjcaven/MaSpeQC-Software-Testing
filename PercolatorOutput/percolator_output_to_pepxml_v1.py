import re
import math
import sys
from pathlib import Path
from dataclasses import dataclass
import datetime
from typing import List, Dict, Tuple, Optional

# Reguläre Ausdrücke analog zur Java-Klasse
PATTERN = re.compile(r"(.+spectrum=\".+\.)([0-9]+)\.([0-9]+)(\.[0-9]+\".+)")
PATTERN_1 = re.compile(r'base_name="([^"]+)"')
PATTERN_2 = re.compile(r'raw_data_type="([^"]+)"')
PATTERN_3 = re.compile(r'raw_data="([^"]+)"')

@dataclass
class NttNmc:
    ntt: int
    nmc: int
    spectral_similarity: float
    rt_score: float
    im_score: float

@dataclass
class PepScore:
    pep: float
    score: float

# Ersatz für org.nesvilab.utils.StringUtils
def up_to_last_dot(s: str) -> str:
    return s.rsplit('.', 1)[0] if '.' in s else s

def after_last_dot(s: str) -> str:
    return s.rsplit('.', 1)[1] if '.' in s else ""

def get_spectrum(line: str) -> str:
    spectrum = None
    for e in line.split():
        if e.startswith("spectrum="):
            spectrum = e[len("spectrum=\""):-1]
            break
    if spectrum is None:
        raise ValueError(f"No spectrum found in line: {line}")
    return spectrum[:spectrum.rfind(".")]

def padding_zeros(line: str) -> str:
    match = PATTERN.match(line)
    if not match:
        raise RuntimeError(f"Cannot parse line {line}")
    if match.group(2) != match.group(3):
        raise RuntimeError(f"Cannot parse spectrum ID from {line}")
    
    scan_num = match.group(2)
    if len(scan_num) >= 5:
        return line
    
    padded_scan = scan_num.zfill(5)
    return f"{match.group(1)}{padded_scan}.{padded_scan}{match.group(4)}"

def get_spectrum_rank(s: str) -> Tuple[str]:
    charge_rank = s[s.rfind("."):]
    rank = int(charge_rank.split("_")[1])
    return (s[:s.rfind(".")], rank)


def handle_search_hit(search_hit: List[str], ntt_nmc: NttNmc, pep_score: PepScore, old_rank: int, new_rank: int) -> str:
    if not ntt_nmc or not pep_score:
        return ""

    lines = []
    calc_neutral_pep_mass = math.nan
    massdiff = math.nan
    isomassd = 0
    
    iterator = iter(search_hit)
    search_hit_line = next(iterator)

    for e in search_hit_line.split():
        if e.startswith("massdiff="):
            massdiff = float(e[len("massdiff=\""):-1])
        if e.startswith("calc_neutral_pep_mass="):
            calc_neutral_pep_mass = float(e[len("calc_neutral_pep_mass=\""):-1])

    gap = float('inf')
    C13C12_MASSDIFF_U = 1.0033548378
    for isotope in range(-6, 7):
        current_gap = abs(massdiff - isotope * C13C12_MASSDIFF_U)
        if current_gap < gap:
            gap = current_gap
            isomassd = isotope

    if gap > 0.1:
        isomassd = 0
    # is hit_rank always 1 for DDA?
    if old_rank == new_rank:
        lines.append(search_hit_line)
    else:
        lines.append(search_hit_line.replace(f'hit_rank="{old_rank}"', f'hit_rank="{new_rank}"'))

    for line in iterator:
        if line.strip() == "</search_hit>":
            break
        lines.append(line)

    if not math.isnan(ntt_nmc.spectral_similarity):
        lines.append(f'<search_score name="spectralsim" value="{ntt_nmc.spectral_similarity:f}"/>')
    
    if not math.isnan(ntt_nmc.rt_score):
        lines.append(f'<search_score name="rtscore" value="{ntt_nmc.rt_score:f}"/>')
        
    if not math.isnan(ntt_nmc.im_score):
        lines.append(f'<search_score name="imscore" value="{ntt_nmc.im_score:f}"/>')

    prob = 1.0 - pep_score.pep
    massd_val = (massdiff - isomassd * C13C12_MASSDIFF_U) * 1000000.0 / calc_neutral_pep_mass
    
    analysis_result = f"""<analysis_result analysis="peptideprophet">
                            <peptideprophet_result probability="{prob:f}" all_ntt_prob="({prob:f},{prob:f},{prob:f})">
                            <search_score_summary>
                            <parameter name="fval" value="{pep_score.score:f}"/>
                            <parameter name="ntt" value="{ntt_nmc.ntt:d}"/>
                            <parameter name="nmc" value="{ntt_nmc.nmc:d}"/>
                            <parameter name="massd" value="{massd_val:f}"/>
                            <parameter name="isomassd" value="{isomassd:d}"/>
                            </search_score_summary>
                            </peptideprophet_result>
                            </analysis_result>"""
    lines.append(analysis_result)
    lines.append("</search_hit>")
    
    return "\n".join(lines) + "\n"

def handle_spectrum_query(sq: List[str], pin_spectrum_rank_ntt_nmc: Dict[str, List[Optional[NttNmc]]], 
                          pin_spectrum_rank_pep_score: Dict[str, List[Optional[PepScore]]], dia_rank: int) -> str:
    search_hits = []
    lines = []
    iterator = iter(sq)
    
    for line in iterator:
        line = line.strip()
        spectrum = get_spectrum(line)
        pep_score_array = pin_spectrum_rank_pep_score.get(spectrum)
        if not pep_score_array: # this is the filtering of spectrum query
            return ""
        
        
        ntt_nmc_array = pin_spectrum_rank_ntt_nmc.get(spectrum)
        if not ntt_nmc_array: return ""

        lines.append(padding_zeros(line))

        for line in iterator:
            line_stripped = line.strip()
            if line_stripped.startswith("<search_result>"):
                lines.append(line_stripped)
            elif line_stripped.startswith("<search_hit "):
                search_hit = [line]
                for next_line in iterator:
                    search_hit.append(next_line)
                    if next_line.strip() == "</search_hit>":
                        break
                search_hits.append(search_hit)
            elif not line_stripped.startswith("</search_result>"):
                if not line_stripped.startswith("</spectrum_query>"):
                    raise RuntimeError(f"Unexpected line: {line}")
                lines.append(line_stripped)
            else:
                # Python's dict (insertion order) or sorting handles the TreeMap reverse order
                score_old_rank_minus_one = {}
                for old_rank_minus_one, pep_score in enumerate(pep_score_array):
                    if pep_score:
                        score_old_rank_minus_one[pep_score.score] = old_rank_minus_one
                
                # Sort descending by score
                sorted_scores = sorted(score_old_rank_minus_one.items(), key=lambda item: item[0], reverse=True)
                
                new_rank = 0
                for _, old_rank_minus_one in sorted_scores:
                    new_rank += 1
                    lines.append(handle_search_hit(search_hits[old_rank_minus_one], 
                                                    ntt_nmc_array[old_rank_minus_one], 
                                                    pep_score_array[old_rank_minus_one], 
                                                    old_rank_minus_one + 1, 
                                                    new_rank).strip())
                
                lines.append(line_stripped)

    return "\n".join(lines) + "\n"

def percolator_to_pep_xml(base_dir: str, basename: str, min_prob: float):

    # set file paths
    fragger_pin = Path(base_dir) / f"{basename}.pin"
    booster_pin = Path(base_dir) / f"{basename}_edited.pin"
    pin = booster_pin if booster_pin.exists() else fragger_pin    
    percolator_target_psms = Path(base_dir) / "targets.tsv"
    percolator_decoy_psms = Path(base_dir) / "decoys.tsv"
    lcms_path = basename + ".mzML" 
    out_basename = Path(base_dir) / "converted"

    pin_spectrum_rank_ntt_nmc: Dict[str, List[Optional[NttNmc]]] = {}
    pin_spectrum_rank_pep_score: Dict[str, List[Optional[PepScore]]] = {}

    # Lese PIN Datei
    with open(pin, 'r', encoding='utf-8') as brtsv:
        pin_header = brtsv.readline()
        if not pin_header:
            raise ValueError(f"Could not read the first line of {pin.absolute()}.")
        
        colnames = pin_header.strip().split("\t")
        idx_specid = colnames.index("SpecId")
        idx_ntt = colnames.index("ntt")
        idx_nmc = colnames.index("nmc")
        
        idx_spectral_sim = colnames.index("bray_curtis") if "bray_curtis" in colnames else colnames.index("unweighted_spectral_entropy") if "unweighted_spectral_entropy" in colnames else -1
        idx_rt_score = colnames.index("delta_RT_loess_real") if "delta_RT_loess_real" in colnames else -1
        idx_im_score = colnames.index("delta_IM_loess") if "delta_IM_loess" in colnames else -1

        for line in brtsv:
            if not line.strip(): continue
            split = line.split("\t")
            raw_specid = split[idx_specid]
            spec_rank = get_spectrum_rank(raw_specid)
            spec_id, rank = spec_rank[0], spec_rank[1] 
            
            ntt = int(split[idx_ntt])
            nmc = int(split[idx_nmc])
            spectral_sim = float(split[idx_spectral_sim]) if idx_spectral_sim != -1 else math.nan
            rt_score = float(split[idx_rt_score]) if idx_rt_score != -1 else math.nan
            im_score = float(split[idx_im_score]) if idx_im_score != -1 else math.nan

            if spec_id not in pin_spectrum_rank_ntt_nmc:
                pin_spectrum_rank_ntt_nmc[spec_id] = [None]
            
            pin_spectrum_rank_ntt_nmc[spec_id][rank - 1] = NttNmc(ntt, nmc, spectral_sim, rt_score, im_score)

    print(len(pin_spectrum_rank_ntt_nmc))

    # Lese Target und Decoy TSVs
    for tsv_path in [percolator_target_psms, percolator_decoy_psms]:
        with open(tsv_path, 'r', encoding='utf-8') as brtsv:
            header = brtsv.readline()
            if not header: continue
            colnames = header.strip().split("\t")
            idx_psmid = colnames.index("PSMId")
            idx_pep = colnames.index("posterior_error_prob")
            idx_score = colnames.index("score")

            for line in brtsv:
                if not line.strip(): continue
                split = line.split("\t")
                spec_rank = get_spectrum_rank(split[idx_psmid])
                spec_id, rank = spec_rank[0], spec_rank[1]

                try:
                    pep = float(split[idx_pep])
                except ValueError:
                    pep = 1.0

                if (1.0 - pep) >= min_prob:
                    try:
                        score = float(split[idx_score])
                    except ValueError:
                        score = 0.0

                    if spec_id not in pin_spectrum_rank_pep_score:
                        pin_spectrum_rank_pep_score[spec_id] = [None]
                    pin_spectrum_rank_pep_score[spec_id][rank - 1] = PepScore(pep, score)

    print(len(pin_spectrum_rank_pep_score))

    # Generiere Output XMLs
    output_rank = Path(base_dir) / f"{out_basename}.pep.xml"
    pepxml_rank = Path(base_dir) / f"{basename}.pepXML"

    with open(pepxml_rank, 'r', encoding='utf-8') as brpepxml, open(output_rank, 'w', encoding='utf-8') as out:
        for line in brpepxml:
            line_stripped = line.strip()
            if line_stripped.startswith("<msms_run_summary"):
                if PATTERN_1.search(line):
                    line = PATTERN_1.sub(f'base_name="{up_to_last_dot(lcms_path)}"', line, count=1)
                    if PATTERN_2.search(line):
                        line = PATTERN_2.sub(f'raw_data_type="{after_last_dot(lcms_path)}"', line, count=1)
                    if PATTERN_3.search(line):
                        line = PATTERN_3.sub(f'raw_data="{after_last_dot(lcms_path)}"', line, count=1)
                else:
                    print(f"Could not find the base_name from {pepxml_rank}", file=sys.stderr)
                    return False

            out.write(line)

            if line_stripped.startswith("<msms_pipeline_analysis "):
                now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                tmp = (f'<analysis_summary analysis="Percolator" time="{now}">\n'
                        f'<peptideprophet_summary min_prob="{min_prob:.2f}">\n'
                        f'<inputfile name="{pepxml_rank.absolute()}"/>\n'
                        f'</peptideprophet_summary>\n'
                        f'</analysis_summary>\n'
                        f'<analysis_summary analysis="database_refresh" time="{now}"/>\n'
                        f'<analysis_summary analysis="interact" time="{now}">\n'
                        f'<interact_summary filename="{output_rank.absolute()}" directory="">\n'
                        f'<inputfile name="{pepxml_rank.absolute()}"/>\n'
                        f'</interact_summary>\n'
                        f'</analysis_summary>\n'
                        f'<dataset_derivation generation_no="0"/>\n')
                out.write(tmp)

            if line_stripped == "</search_summary>":
                break

        # Verarbeite spectrum_queries
        sq = []
        for line in brpepxml:
            if line.strip().startswith("<spectrum_query"):
                sq = [line]
            elif sq:
                sq.append(line)
                if line.strip() == "</spectrum_query>":
                    out.write(handle_spectrum_query(sq, pin_spectrum_rank_ntt_nmc, pin_spectrum_rank_pep_score,rank))
                    sq = []

        out.write("</msms_run_summary>\n</msms_pipeline_analysis>\n")
    return True

if __name__ == "__main__":
    import sys
    percolator_to_pep_xml(
        sys.argv[1],
        sys.argv[2],
        float(sys.argv[3])
    )
