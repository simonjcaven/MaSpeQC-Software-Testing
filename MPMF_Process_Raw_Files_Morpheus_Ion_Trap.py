# MaSpeQC - Quality control software for LC-MS/MS instrumentation
#
# Copyright (C) 2018-2025  Simon Caven
# Copyright (C) 2020-2025  Monash University
# Copyright (C) 2022-2025  University of Applied Sciences Mittweida
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import datetime
from decimal import getcontext, Decimal
import glob
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
from MPMF_File_System import FileSystem
from MPMF_Database_SetUp import MPMFDBSetUp
from MPMF_Stats import Stat
from MPMF_Chromatogram import Chromatogram
from MPMF_Email import SendEmail
from MPMF_Thermo_Metrics import ThermoMetrics
getcontext().prec = 12

# LOGGING
# create module logger 
logger = logging.getLogger('processing')
logger.setLevel(logging.DEBUG)

# create file handler which logs even debug messages
fh = logging.FileHandler('processing.log')
fh.setLevel(logging.DEBUG)

# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(levelname)s - %(name)s - %(asctime)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)


class ProcessRawFile:
    """
        Processes a single raw file
        Inserts metric data into database
        Uses SendEmail and Stat
    """
    def __init__(self, file_name, file_path, machine, e_type, filesystem, db_info, email, machine_type, file_format):

        self.experiment = e_type.upper()
        self.machine = machine
        self.file_name = file_name
        self.fs = filesystem
        self.send_email = email
        self.machine_type = machine_type
        self.db = MPMFDBSetUp(db_info["user"], db_info["password"], db_info["database"], self.fs, db_info["port"])
        self.raw_file = file_path
        self.file_format = file_format
        self.metadata = {'filename': self.file_name, 'experiment': self.experiment, 'machine': self.machine}
        self.outfiles_dir = os.path.join(self.fs.out_dir, self.experiment, self.machine, self.file_name)
        self.morph_out_dir = os.path.join(self.outfiles_dir, "Morpheus")

        # make and set folder for outfiles
        os.chdir(self.fs.out_dir)
        if not os.path.isdir(self.outfiles_dir):
            os.makedirs(os.path.join(self.experiment, self.machine, self.file_name))

    # RUN
    def run(self):
        # check if a QC file and not inserted
        check_run = False
        if self.check_file_name():
            if not self.check_run():
                # convert raw file
                if self.run_msconvert():
                    # create xml
                    if self.experiment == "METABOLOMICS":
                        self.create_metab_xml()
                    elif self.experiment == "PROTEOMICS":
                        self.create_proteo_xml()
                    if self.run_mzmine():
                        if self.insert_qc_run_data():
                            if self.experiment == "METABOLOMICS":
                                self.insert_pos_csv()
                                self.insert_neg_csv()
                                self.fwhm_to_seconds()
                                email_data = self.check_email_thresholds_metab()
                                self.insert_summary(email_data)
                                if self.send_email:
                                    if len(email_data) > 0:
                                        email_data['metadata'] = self.metadata
                                        SendEmail(email_data, self.db, self.fs)
                                    else:
                                        logger.info("No Thresholds breached, No Email Sent")
                                logger.info("Inserted Data for " + self.machine + " " + self.file_name)
                                check_run = True
                            elif self.experiment == "PROTEOMICS":
                                self.insert_pos_csv()
                                self.fwhm_to_seconds()
                                if self.run_morpheus():
                                    self.insert_morpheus()
                                    email_data = self.check_email_thresholds_prot()
                                    self.insert_summary(email_data)
                                    if self.send_email:
                                        if len(email_data) > 0:
                                            email_data['metadata'] = self.metadata
                                            SendEmail(email_data, self.db, self.fs)
                                        else:
                                            logger.info("No Thresholds breached, No Email Sent")
                                    logger.info("Inserted Data for " + self.machine + " " + self.file_name)
                                    check_run = True
                                else:
                                    self.delete_run()
                                    logger.error("Morpheus error " + self.file_name)
                        else:
                            logger.error("Insert run details error " + self.file_name)
                    else:
                        logger.error("mzMine: processing error " + self.file_name)
                else:
                    logger.error("msconvert: file too small or still writing  " + self.file_name)
            else:
                logger.info("Already Inserted " + self.file_name)
        else:
            logger,error("Incorrect file format " + self.file_name)

        os.chdir(self.fs.main_dir)
        
        # close database conn. and cursor
        self.db.cursor.close()
        self.db.db.close()
        
        return check_run

    def run_mzmine(self):

        # check platform for loc and command
        platform_sys = platform.system()

        mzmine_loc = ''
        mzmine_command = ''
        if platform_sys == 'Windows':
            mzmine_loc = 'MZmine-2.53-Windows'
            mzmine_command = 'startMZmine-Windows.bat '
        elif platform_sys == 'Linux':
            mzmine_loc = 'MZmine-2.53-Linux'
            mzmine_command = 'startMZmine-Linux.bat '
        elif platform_sys == 'Darwin':
            mzmine_loc = 'MZmine-2.53-macOS'
            mzmine_command = 'startMZmine-macOS.bat '

        if mzmine_loc == '':
            logger.error("Unable to determine platform for mzMine")
            return False
        
        os.chdir(os.path.join(self.fs.sw_dir, mzmine_loc))
        command = mzmine_command + '"' + str(os.path.join(self.outfiles_dir, self.file_name + ".xml")) + '"'
        returnvalue = os.system(command)
        if returnvalue:
            return False
        else:
            return True

    def run_mzmine_sub(self):
        # using subprocess if needed
        os.chdir(os.path.join(self.fs.sw_dir, "MZmine-2.53-Windows"))
        p = subprocess.Popen(['startMZmine-Windows.bat',  str(os.path.join(self.outfiles_dir, self.file_name + ".xml"))], stdout=subprocess.PIPE)
        p.communicate()
        returnvalue = p.poll()
        # backward logic!
        if returnvalue:
            return False
        else:
            return True

    def run_morpheus(self):

        # runs morpheus for windows only
        # needs .NET 4.5 or higher and MSFileReader x86
        # NOTE: morpheus uses relative paths, current method for out folder
        #        removes C: (by splicing below) which means the path starts with /
        #           This is a path relative to the current drive root (WATCH for production env)

        # http://cwenger.github.io/Morpheus/faq.html

        # search database 
        morph_db = os.path.join(self.fs.sw_dir, "Morpheus (mzML)", "CUSTOM.fasta")
        if not os.path.exists(morph_db):
            logger.error("Please add a CUSTOM.fasta file to the Morpheus(mzML) folder and process again")
            return False

        # software location
        morph_dir = os.path.join(self.fs.sw_dir, "Morpheus (mzML)")
        os.chdir(morph_dir)

        if not os.path.isdir(self.morph_out_dir):
            os.makedirs(self.morph_out_dir)

        # cl options
        options = {
                '-d': self.pos_file,
                '-o': self.morph_out_dir,
                '-db': morph_db,
                '-p':'trypsin', # test (remove, but required?)
                #'-ad': 'true', # test(remove)
                #'-mmu': 'true',# test(remove)
                #'-precmtv': '20', # removed for test
                #'-precmtu': 'ppm', # removed for test
                '-prodmtv': '0.5', # test (set back to 20)
                #'-prodmtu': 'ppm', # removed for test
                #'-pmc': 'true', # removed for test
                '-minpmo': '-3',
                '-maxpmo': '+1',
                '-vm': 'oxidation of M', # test (remove, have to guess abbr. here)
                '-fm': 'carbamidomethylation of C', # test (remove, have to guess abbr. here)
                '-acs': 'true' # test(change back to false)
            }

        # executable
        command = 'morpheus_mzml_cl'

        # convert options to string for command line
        option_str = ''
        for key in options:
            option_str += ' %s="%s"' % (key, options[key])
        command = command + option_str


        # run morpheus
        returnvalue = os.system(command)
        if returnvalue:
            return False
        else:
            return True

    def run_msconvert(self):
        '''Creates .mzML files in OutFiles'''

        # copy mzML files for proteomics (don't convert)
        if self.file_format == ".mzML":
            if self.experiment == "PROTEOMICS":
                shutil.copy(self.raw_file, self.outfiles_dir)
                os.chdir(self.outfiles_dir)
                os.rename(self.file_name + ".mzML", self.file_name + "_pos" + ".mzML")
                return True


        # go to s/w location
        os.chdir(os.path.join(self.fs.sw_dir, "ProteoWizard"))

        # convert positive
        command = 'msconvert ' + '"' + self.raw_file + '"' \
                  + ' --filter ' + '"peakPicking true 1-"' + ' --filter ' + '"polarity positive"' \
                  + ' --mzML -o ' + '"' + self.outfiles_dir + '"' + ' --outfile ' + '"' + self.file_name \
                  + '"' + '_pos'
        returnvalue = os.system(command)
        if returnvalue:
            return False

        if self.experiment == "METABOLOMICS":
            # run negative
            command = 'msconvert ' + '"' + self.raw_file + '"' \
                      + ' --filter ' + '"peakPicking true 1-"' + ' --filter ' + '"polarity negative"' \
                      + ' --mzML -o ' + '"' + self.outfiles_dir + '"' + ' --outfile ' + '"' + self.file_name \
                      + '"' + '_neg'
            returnvalue = os.system(command)
            if returnvalue:
                return False

        return True

    # CHECK
    def check_run(self):
        # check hasn't already been inserted
        sql = "SELECT * FROM qc_run WHERE file_name = " + "'" + self.file_name + "'"
        try:
            self.db.cursor.execute(sql)
            data = self.db.cursor.fetchall()
        except Exception as e:
            logger.exception(e)

        return len(data)
        
    def delete_run(self):
        # delete run when error
        sql = "DELETE FROM qc_run WHERE file_name = " + "'" + self.file_name + "'"
        
        try:
            self.db.cursor.execute(sql)
            self.db.db.commit()
        except Exception as e:
            logger.exception(e)

    def check_file_name(self):
        # QC_Metabolomics_Timestamp
        # QC_Proteomics_Timestamp
        # Timestamp = YYYYMMDDHHMMSS or YYYYMMDDHHMM
        try:
            datetime.datetime.strptime(self.file_name[-14:], "%Y%m%d%H%M%S")
            return True
        except ValueError as e:
            try:
                datetime.datetime.strptime(self.file_name[-12:], "%Y%m%d%H%M")
                return True
            except ValueError as e:
                logger.error("Not a valid timestamp " + self.file_name)
                return False

    # CREATE
    def create_metab_xml(self):
        self.pos_file = os.path.join(self.outfiles_dir, self.file_name + "_pos.mzML")
        self.neg_file = os.path.join(self.outfiles_dir, self.file_name + "_neg.mzML")
        neg_db = self.fs.neg_db
        pos_db = self.fs.pos_db
        batch = os.path.join(self.outfiles_dir, self.file_name + ".mzmine")
        outfile_xml = os.path.join(self.outfiles_dir, self.file_name + ".xml")
        pos_output_file = os.path.join(self.outfiles_dir, "posoutput.csv")
        neg_output_file = os.path.join(self.outfiles_dir, "negoutput.csv")

        new_xml = []
        os.chdir(self.fs.main_dir)
        with open(self.fs.xml_template_metab, 'r') as infile:
            for line in infile:
                new_line = line.strip()
                new_line = new_line.replace('POSINPUTFILE', self.pos_file)
                new_line = new_line.replace('NEGINPUTFILE', self.neg_file)
                new_line = new_line.replace('POSDATABASEFILE', pos_db)
                new_line = new_line.replace('NEGDATABASEFILE', neg_db)
                new_line = new_line.replace('POSOUTPUTFILE', pos_output_file)
                new_line = new_line.replace('NEGOUTPUTFILE', neg_output_file)
                new_line = new_line.replace('SAMPLEBATCHNAME', batch)
                new_xml.append(new_line)

        with open(outfile_xml, 'w') as outfile:
            for line in new_xml:
                outfile.write(line + "\n")
        

    def create_proteo_xml(self):
        self.pos_file = os.path.join(self.outfiles_dir, self.file_name + "_pos.mzML")
        pos_db = self.fs.irt_db
        batch = os.path.join(self.outfiles_dir, self.file_name + ".mzmine")
        outfile_xml = os.path.join(self.outfiles_dir, self.file_name + ".xml")
        pos_output_file = os.path.join(self.outfiles_dir, "posoutput.csv")

        new_xml = []
        os.chdir(self.fs.main_dir)
        with open(self.fs.xml_template_proteo, 'r') as infile:
            for line in infile:
                new_line = line.strip()
                new_line = new_line.replace('POSINPUTFILE', self.pos_file)
                new_line = new_line.replace('POSDATABASEFILE', pos_db)
                new_line = new_line.replace('POSOUTPUTFILE', pos_output_file)
                new_line = new_line.replace('SAMPLEBATCHNAME', batch)
                new_xml.append(new_line)

        with open(outfile_xml, 'w') as outfile:
            for line in new_xml:
                outfile.write(line + "\n")

    # INSERT
    def insert_morpheus(self):

        # read and insert summary data from morpheus
        with open(os.path.join(self.morph_out_dir, "summary.tsv"), "r") as infile:
            lines = infile.readlines()
        # put summary data in a dict
        summary = {}

        keys = lines[0].split("\t")
        values = lines[1].split("\t")
        for i in range(len(keys)):
            summary[keys[i].strip()] = values[i].strip()

        # get run id
        run_id = self.db.get_run_id(self.file_name)

        # get hela component_id
        sql = "SELECT component_id FROM sample_component WHERE component_name = 'Hela Digest'"
        try:
            self.db.cursor.execute(sql)
            hela_id = self.db.cursor.fetchone()[0]
        except Exception as e:
            logger.exception(e)

        for key in summary:
            # get metric_id
            sql = "SELECT metric_id FROM metric WHERE metric_name = '" + key.strip() + "'"
            try:
                self.db.cursor.execute(sql)
                met_id = self.db.cursor.fetchone()
            except Exception as e:
                logger.exception(e)

            # insert measurement
            if met_id is not None:
                sql = "INSERT INTO measurement VALUES ( '" + str(met_id[0]) + "','" + str(hela_id) + \
                      "','" + str(run_id) + "','" + str(summary[key]) + "')"

                try:
                    self.db.cursor.execute(sql)
                except Exception as e:
                    logger.exception(e)

                self.db.db.commit()

        self.insert_morpheus_ppms(run_id, hela_id)

    def insert_morpheus_ppms(self, rid, hid):

        with open(os.path.join(self.morph_out_dir, self.file_name + "_pos.PSMs.tsv"), "r") as infile:
            lines = infile.readlines()

        # get and remove headers
        headers = lines[0].split('\t')
        lines.pop(0)

        # dict to find index of headers
        index = 0
        indexes = {}
        for header in headers:
            indexes[header.strip()] = index
            index +=1

        # compute average based on constraints
        count = 0
        total = 0
        for line in lines:
            ppm = float(line.split('\t')[indexes['Precursor Mass Error (ppm)']])
            target = line.split('\t')[indexes['Target?']].strip() # in file as capitals but converts to python 'string' bools
            score = float(line.split('\t')[indexes['Morpheus Score']])

            # TEST
            if target == "True":
                print(ppm, score)

            if ppm > -50 and ppm < 50 and target == 'True' and score > 13: # constraints -50 to 50, score = 13, for ion trap???
                total += ppm
                count +=1
            
        if count > 0:
            average = total/count
            print(count, "TOTAL")
        else:
            average = -1


        # get id for Precursor Mass Error
        sql = "SELECT metric_id FROM metric WHERE metric_name = 'Precursor Mass Error'"
        try:
            self.db.cursor.execute(sql)
            mid = self.db.cursor.fetchone()
        except Exception as e:
            logger.exception(e)

        # insert
        sql = "INSERT INTO measurement VALUES ( '" + str(mid[0]) + "','" + str(hid) + \
              "','" + str(rid) + "','" + str(average) + "')"

        try:
            self.db.cursor.execute(sql)
        except Exception as e:
            logger.exception(e)

        self.db.db.commit()

    def insert_pos_csv(self):
        # insert pos for v4
        # relies on INSERT ORDER (from DB) REFACTOR?
        # mz, rt, height, area, fwhm, tf, af, min, max, (ppm), (dalton), (areaN), (heightN)
        # change metric names in xml templates and rewrite all insert functions to use names

        run_id = self.db.get_run_id(self.file_name)

        with open(os.path.join(self.outfiles_dir, "posoutput.csv"), "r") as incsv:
            for line in incsv:
                in_data = line.strip().split("|")
                if in_data[0][0] != 'r': # skip first line
                    sql = "SELECT component_id FROM sample_component WHERE component_name = " + "'" + in_data[0] + "'"
                    try:
                        self.db.cursor.execute(sql)
                        comp_id = self.db.cursor.fetchone()
                    except Exception as e:
                        logger.exception(e)

                    for i in range(1, 10): # watch i as metric id here REFACTOR change metric names to mzmine and get ids
                        # handle nulls, put to 0, other values ??
                        ins_value = str(in_data[i])
                        if ins_value == 'null':
                            ins_value = '0'
                        ins_sql = "INSERT INTO measurement VALUES( " + "'" + str(i) + "', '" + str(comp_id[0]) \
                                  + "', '" + str(run_id) + "', '" + ins_value + "')"
                        try:
                            self.db.cursor.execute(ins_sql)
                            self.db.db.commit()
                        except Exception as e:
                            logger.exception(e)

                    self.insert_derived_errors(run_id, comp_id[0])

    def insert_neg_csv(self):
        # insert neg for v4
        # INSERT ORDER (from DB)
        # mz, rt, height, area, fwhm, tf, af, min, max, ppm, dalton, areaN, heightN

        # get run_id
        run_id = self.db.get_run_id(self.file_name)

        with open(os.path.join(self.outfiles_dir, "negoutput.csv"), "r") as incsv:
            for line in incsv:
                in_data = line.strip().split("|")
                if in_data[0][0] != 'r': # skip first line
                    sql = "SELECT component_id FROM sample_component WHERE component_name = " + "'" + in_data[0] + "'"
                    try:
                        self.db.cursor.execute(sql)
                        comp_id = self.db.cursor.fetchone()
                    except Exception as e:
                        logger.exception(e)

                    for i in range(1, 10):
                        # handle nulls, put to 0, other values ??
                        ins_value = str(in_data[i])
                        if ins_value == 'null':
                            ins_value = '0'
                        ins_sql = "INSERT INTO measurement VALUES( " + "'" + str(i) + "', '" + str(comp_id[0]) \
                                  + "', '" + str(run_id) + "', '" + ins_value + "')"
                        try:
                            self.db.cursor.execute(ins_sql)
                            self.db.db.commit()
                        except Exception as e:
                            logger.exception(e)

                    self.insert_derived_errors(run_id, comp_id[0])

    def insert_derived_errors(self, r_id, c_id):
        sql = "SELECT exp_mass_charge FROM sample_component WHERE component_id = " + str(c_id)
        try:
            self.db.cursor.execute(sql)
            emc = self.db.cursor.fetchone()
        except Exception as e:
            logger.exception(e)


        sql2 = "SELECT value FROM measurement WHERE component_id = " + str(c_id) + " AND run_id = " \
               + str(r_id) + " AND metric_id = 1"
        try:
            self.db.cursor.execute(sql2)
            m_value = self.db.cursor.fetchone()
        except Exception as e:
            logger.exception(e)

        # data type nightmare c/o mysql and python
        diff = Decimal(m_value[0]) - Decimal(emc[0])
        ppm = (diff/emc[0]) * Decimal(1e6)
        dalton = diff * Decimal(1e3)

        ins_sql1 = "INSERT INTO measurement VALUES( " + "'" + "10" + "', '" + str(c_id) \
                                    + "', '" + str(r_id) + "', '" + str(ppm) + "')"

        ins_sql2 = "INSERT INTO measurement VALUES( " + "'" + "11" + "', '" + str(c_id) \
                   + "', '" + str(r_id) + "', '" + str(dalton) + "')"

        try:
            self.db.cursor.execute(ins_sql1)
            self.db.cursor.execute(ins_sql2)
            self.db.db.commit()
        except Exception as e:
            logger.exception(e)

    def insert_qc_run_data(self):

        # get id for experiment
        e_sql = "SELECT experiment_id FROM experiment WHERE experiment_type = '" + self.experiment.lower() + "'"

        try:
            self.db.cursor.execute(e_sql)
            eid = self.db.cursor.fetchone()
            self.eid = eid[0] # store for stats
        except Exception as e:
            logger.exception(e)

        # get machine id
        m_sql = "SELECT machine_id FROM machine WHERE machine_name = " + "'" + self.machine + "'"

        try:
            self.db.cursor.execute(m_sql)
            self.mid = self.db.cursor.fetchone() # store machine id
        except Exception as e:
            logger.exception(e)


        run_date = self.get_run_date_time()

        sql = "INSERT INTO qc_run(run_id, file_name, date_time, machine_id, experiment_id, completed) VALUES(NULL,'" \
              + self.file_name + "', CONVERT('" + str(run_date) + "', DATETIME)" + ",'" + str(self.mid[0]) + \
               "','" + str(self.eid) + "','N'" + ")"
        try:
            self.db.cursor.execute(sql)
        except Exception as e:
            logger.exception(e)
            return False

        self.db.db.commit()
        return True

    def insert_summary(self, s_data):

        # get run id
        run_id = self.db.get_run_id(self.file_name)

        # convert to json and update table
        json_data = json.dumps(s_data, separators=(",", ":"))
        sql = "UPDATE qc_run SET summary = '" + json_data + "' WHERE run_id = '" + str(run_id) + "'"

        try:
            self.db.cursor.execute(sql)
            self.db.db.commit()
        except Exception as e:
            logger.exception(e)

    # EMAIL
    def check_email_thresholds_prot(self):
        # checks metric values against the thresholds in config files
        # and sends email if any outsdide limits
        
        # get db (exp. retention times)
        with open(self.fs.irt_db) as f:
            pos_db = f.readlines()
        
        # remove header
        pos_db.pop(0)
            
        # create dict for storing
        pos_samples = {}
        for sample in pos_db:
            new_sample = sample.split("|")
            pos_samples[new_sample[2].strip()] = float(new_sample[1])

        # get threshold limits
        with open(self.fs.thresh_email) as f:
            limits = f.readlines()

        # remove header
        limits.pop(0)

        # create dict for storing
        thresholds = {}
        for limit in limits:
            new_limit = limit.split("|")
            if new_limit[1] != '':
                thresholds[new_limit[0]] = [new_limit[1], new_limit[2], new_limit[3].strip()]

        # get run_id
        run_id = self.db.get_run_id(self.file_name)

        breaches = {}
        for metric in thresholds:

            # limits
            tot = int(thresholds[metric][0])
            lower = thresholds[metric][1]
            upper = thresholds[metric][2]

            # get metric_id
            sql = "SELECT metric_id FROM metric WHERE metric_name = " + "'" + metric + "'"
            self.db.cursor.execute(sql)
            metric_id = self.db.cursor.fetchone()[0]

            # get values for metric and run_id
            sql = "SELECT c.component_name, v.value FROM " + \
                  "measurement v, sample_component c, metric m " + \
                  "WHERE m.metric_id = v.metric_id AND " + \
                  "c.component_id = v.component_id AND " + \
                  "v.run_id = " + "'" + str(run_id) + "'" + \
                  " AND v.metric_id = " + "'" + str(metric_id) + "'"

            self.db.cursor.execute(sql)
            results = self.db.cursor.fetchall()

            # get components that exceed limits for each metric
            comps = {}
            if metric == "mass_error_ppm":
                # check limits
                for result in results:
                    # convert to negative as can come from config as pos
                    lower = float(lower)
                    if lower > 0:
                        lower = lower * -1
                    if result[1] > float(upper) or result[1] < lower:
                        comps[result[0]] = [str(round(result[1], 3)) + " ppm"]
                    # catch missed values
                    if result[1] == -1000000.0:
                        comps[result[0]] = ["NO VALUE"]
            elif metric == "area_normalised":
                # check limits
                for result in results:
                    if result[1] < float(lower):
                        comps[result[0]] = [str(round(result[1], 3))]
                    if result[1] == -100.0:
                        comps[result[0]] = ["NO VALUE"]
            elif metric == "fwhm":
                # check limits
                for result in results:
                    if result[1] > float(upper):
                        comps[result[0]] = [str(round(result[1], 3)) + " sec"]
                    if result[1] == 0:
                        comps[result[0]] = ["NO VALUE"]
            elif metric == "tf":
                # check limits
                for result in results:
                    if result[1] > float(upper):
                        comps[result[0]] = [str(round(result[1], 3))]
                    if result[1] == 0:
                        comps[result[0]] = ["NO VALUE"]
            elif metric == "af":
                # check limits
                for result in results:
                    if result[1] > float(upper):
                        comps[result[0]] = [str(round(result[1], 3))]
                    if result[1] == 0:
                        comps[result[0]] = ["NO VALUE"]
            elif metric == "MS/MS Spectra":
                # determine percentiles
                sql = "SELECT m.value FROM measurement m, qc_run q WHERE m.metric_id = " + "'" + str(metric_id) + "'" + \
                      " AND m.run_id = q.run_id AND " + \
                      " q.experiment_id = '" + str(self.eid) + "'" +\
                      " AND q.machine_id = " + str(self.mid[0]) + \
                      " ORDER by m.value"
                self.db.cursor.execute(sql)
                all_results = self.db.cursor.fetchall()
                all_values = [float(item[0]) for item in all_results]

                # get index in ordered list of values
                try:
                    pos = all_values.index(float(results[0][1]))
                    # check upper percentile (REMOVED)
                    #if (1 - pos / len(all_values)) < float(upper) / 100:
                        #comps[metric] = [str(int(results[0][1])),"Top " + str(round((1-pos / len(all_values))*100, 2)) + "%"]
                    # check lower percentile
                    if len(all_values) >= 20: # need 20 runs for threshold
                        if pos / len(all_values) < abs(float(lower)) / 100:
                            comps[metric] = [str(int(results[0][1])),"Bottom " + str(round((pos / len(all_values))*100, 2)) + "%"]
                except ValueError:
                    pass
            elif metric == "Target PSMs":
                # determine percentiles
                sql = "SELECT m.value FROM measurement m, qc_run q WHERE m.metric_id = " + "'" + str(metric_id) + "'" + \
                      " AND m.run_id = q.run_id AND " + \
                      " q.experiment_id = '" + str(self.eid) + "'" +\
                      " AND q.machine_id = " + str(self.mid[0]) + \
                      " ORDER by m.value"
                self.db.cursor.execute(sql)
                all_results = self.db.cursor.fetchall()
                all_values = [float(item[0]) for item in all_results]

                # get index in ordered list of values
                try:
                    pos = all_values.index(float(results[0][1]))
                    # check lower percentile
                    if len(all_values) >= 20: # need 20 runs for threshold
                        if pos / len(all_values) < abs(float(lower)) / 100:
                            comps[metric] = [str(int(results[0][1])),"Bottom " + str(round((pos / len(all_values))*100, 2)) + "%"]
                except ValueError:
                    pass
            elif metric == "Unique Target Peptides":
                # determine percentiles
                sql = "SELECT m.value FROM measurement m, qc_run q WHERE m.metric_id = " + "'" + str(metric_id) + "'" + \
                      " AND m.run_id = q.run_id AND " + \
                      " q.experiment_id = '" + str(self.eid) + "'" +\
                      " AND q.machine_id = " + str(self.mid[0]) + \
                      " ORDER by m.value"
                self.db.cursor.execute(sql)
                all_results = self.db.cursor.fetchall()
                all_values = [float(item[0]) for item in all_results]

                # get index in ordered list of values
                try:
                    pos = all_values.index(float(results[0][1]))
                    # check lower percentile
                    if len(all_values) >= 20: # need 20 runs for threshold
                        if pos / len(all_values) < abs(float(lower)) / 100:
                            comps[metric] = [str(int(results[0][1])),"Bottom " + str(round((pos / len(all_values))*100, 2)) + "%"]
                except ValueError:
                    pass
            elif metric == "Target Protein Groups":
                # determine percentiles
                sql = "SELECT m.value FROM measurement m, qc_run q WHERE m.metric_id = " + "'" + str(metric_id) + "'" + \
                      " AND m.run_id = q.run_id AND " + \
                      " q.experiment_id = '" + str(self.eid) + "'" +\
                      " AND q.machine_id = " + str(self.mid[0]) + \
                      " ORDER by m.value"
                self.db.cursor.execute(sql)
                all_results = self.db.cursor.fetchall()
                all_values = [float(item[0]) for item in all_results]

                # get index in ordered list of values
                try:
                    pos = all_values.index(float(results[0][1]))
                    # check lower percentile
                    if len(all_values) >= 20: # need 20 runs for threshold
                        if pos / len(all_values) < abs(float(lower)) / 100:
                            comps[metric] = [str(int(results[0][1])),"Bottom " + str(round((pos / len(all_values))*100, 2)) + "%"]
                except ValueError:
                    pass
            elif metric == "Precursor Mass Error":
                # check limits
                for result in results:
                    if result[1] > float(upper) or result[1] < float(lower):
                        comps[metric] = [str(round(result[1], 3)) + " ppm"]
            elif metric == 'rt':
            
                for result in results:
                    # catch missed values
                    if result[1] == 0:
                        comps[result[0]] = ["NO VALUE"]
                        continue
                        
                    # check pos db
                    if result[0] in pos_samples:
                        if result[1] < (pos_samples[result[0]] - float(lower)):
                            comps[result[0]] = [str(round(result[1], 3)) + " minutes (LOW)"]
                            continue
                        
                        if result[1] > (pos_samples[result[0]] + float(upper)):
                            comps[result[0]] = [str(round(result[1], 3)) + " minutes (HIGH)"]
                            continue

            # add to breaches if tot or more
            if len(comps) >= tot:
                breaches[metric] = comps

        return breaches

    def check_email_thresholds_metab(self):
    
        # get neg and pos databases (exp. retention times)
        with open(self.fs.pos_db) as f:
            pos_db = f.readlines()
            
        with open(self.fs.neg_db) as f:
            neg_db = f.readlines()
        
        # remove header
        neg_db.pop(0)
            
        # create dict for storing
        neg_samples = {}
        for sample in neg_db:
            new_sample = sample.split("|")
            neg_samples[new_sample[2].strip()] = float(new_sample[1])
            
         # remove header
        pos_db.pop(0)
            
        # create dict for storing
        pos_samples = {}
        for sample in pos_db:
            new_sample = sample.split("|")
            pos_samples[new_sample[2].strip()] = float(new_sample[1])

        # get threshold limits
        with open(self.fs.thresh_email) as f:
            limits = f.readlines()

        # remove header
        limits.pop(0)

        # create dict for storing
        thresholds = {}
        for limit in limits:
            new_limit = limit.split("|")
            if new_limit[1] != '':
                thresholds[new_limit[0]] = [new_limit[1], new_limit[2], new_limit[3].strip()]

        # get run_id
        run_id = self.db.get_run_id(self.file_name)

        breaches = {}
        for metric in thresholds:
            # limits
            tot = int(thresholds[metric][0])
            lower = thresholds[metric][1]
            upper = thresholds[metric][2]

            # get metric_id
            sql = "SELECT metric_id FROM metric WHERE metric_name = " + "'" + metric + "'"
            self.db.cursor.execute(sql)
            metric_id = self.db.cursor.fetchone()[0]

            # get values for metric and run_id (not limited by polarity)
            sql = "SELECT c.component_name, v.value FROM " + \
                  "measurement v, sample_component c, metric m " + \
                  "WHERE m.metric_id = v.metric_id AND " + \
                  "c.component_id = v.component_id AND " + \
                  "v.run_id = " + "'" + str(run_id) + "'" + \
                  " AND v.metric_id = " + "'" + str(metric_id) + "'"

            self.db.cursor.execute(sql)
            results = self.db.cursor.fetchall()

            # get components that exceed limits for each metric
            comps = {}
            if metric == "mass_error_ppm":
                # convert to negative as can come from config as pos
                lower = float(lower)
                if lower > 0:
                    lower = lower * -1

                modes = ['N', 'P']
                for mode in modes:
                    # get values by polarity
                    comps = {}
                    sql = "SELECT c.component_name, v.value FROM " + \
                          "measurement v, sample_component c, metric m " + \
                          "WHERE m.metric_id = v.metric_id AND " + \
                          "c.component_id = v.component_id AND " + \
                          "v.run_id = " + "'" + str(run_id) + "'" + \
                          " AND v.metric_id = " + "'" + str(metric_id) + "'" + \
                          " AND c.component_mode =" + "'" + mode + "'"

                    self.db.cursor.execute(sql)
                    results = self.db.cursor.fetchall()

                    # check limits
                    for result in results:
                        if result[1] > float(upper) or result[1] < lower:
                            comps[result[0]] = [str(round(result[1], 3)) + " ppm"]

                        # catch missed values
                        if result[1] == -1000000.0:
                            comps[result[0]] = ["NO VALUE"]

                    # add to breaches if tot or more
                    if len(comps) >= tot:
                        if mode == 'N':
                            breaches[metric + "_Neg"] = comps
                        else:
                            breaches[metric + "_Pos"] = comps
            elif metric == 'rt':
                for result in results:
                    # catch missed values
                    if result[1] == 0:
                        comps[result[0]] = ["NO VALUE"]
                        continue
                    
                    # check neg db
                    if result[0] in neg_samples:
                        if result[1] < (neg_samples[result[0]] - float(lower)):
                            comps[result[0]] = [str(round(result[1], 3)) + " minutes (LOW)"]
                            continue
                        
                        if result[1] > (neg_samples[result[0]] + float(upper)):
                            comps[result[0]] = [str(round(result[1], 3)) + " minutes (HIGH)"]
                            continue
                        
                    # check pos db
                    if result[0] in pos_samples:
                        if result[1] < (pos_samples[result[0]] - float(lower)):
                            comps[result[0]] = [str(round(result[1], 3)) + " minutes (LOW)"]
                            continue
                        
                        if result[1] > (pos_samples[result[0]] + float(upper)):
                            comps[result[0]] = [str(round(result[1], 3)) + " minutes (HIGH)"]
                            continue

                if len(comps) >= tot:
                    breaches[metric] = comps
            elif metric == 'area_normalised':
                for result in results:
                    sql = "SELECT component_id FROM sample_component WHERE component_name = " + "'" + str(
                        result[0]) + "'"
                    self.db.cursor.execute(sql)
                    comp_id = self.db.cursor.fetchone()[0]

                    # get all values per component per machine
                    sql = "SELECT m.value FROM measurement m, qc_run q WHERE m.metric_id = " + "'" + str(metric_id) + "'" + \
                          " AND m.run_id = q.run_id AND " + \
                          " q.experiment_id = '" + str(self.eid) + "'" +\
                          " AND q.machine_id = " + str(self.mid[0]) + \
                          " AND m.component_id = " + "'" + str(comp_id) + "'" + " AND m.value <> -100 " +\
                                                                              " ORDER BY m.value"
                    self.db.cursor.execute(sql)
                    all_results = self.db.cursor.fetchall()
                    all_values = [float(item[0]) for item in all_results]

                    # get index in ordered list of values
                    try:
                        pos = all_values.index(float(result[1]))
                        # check upper percentile
                        if len(all_values) >= 20: # need 20 runs for threshold
                            if (1 - pos / len(all_values)) < float(upper) / 100:
                                comps[result[0]] = [str(round(result[1], 2)) , "Top " + str(round((1-pos / len(all_values))*100, 2)) + "%"]
                            # check lower percentile
                            elif pos / len(all_values) < abs(float(lower)) / 100:
                                comps[result[0]] = [str(round(result[1], 2)) , "Bottom " + str(round((pos / len(all_values))*100, 2)) + "%"]
                    except ValueError:
                        pass

                    # catch missed values
                    if result[1] == -100:
                        comps[result[0]] = ["NO VALUE"]

                if len(comps) >= tot:
                    breaches[metric] = comps

        return breaches

    # OTHER
    def fwhm_to_seconds(self):
        sql = "SELECT metric_id FROM metric WHERE metric_name = 'fwhm'"

        try:
            self.db.cursor.execute(sql)
            fwhm_id = self.db.cursor.fetchone()[0]
        except Exception as e:
            logger.exception(e)

        sql = "SELECT run_id FROM qc_run WHERE file_name = " + "'" + self.file_name + "'"

        try:
            self.db.cursor.execute(sql)
            run_id = self.db.cursor.fetchone()[0]
        except Exception as e:
            logger.exception(e)

        update_sql = "UPDATE measurement SET value = value*60 WHERE run_id = " + "'" + str(run_id) + "'" + \
                    " AND metric_id = " + "'" + str(fwhm_id) + "'"


        try:
            self.db.cursor.execute(update_sql)
            self.db.db.commit()
        except Exception as e:
            logger.exception(e)

    def get_run_date_time(self):
    
        try:
            datetime.datetime.strptime(self.file_name[-14:], "%Y%m%d%H%M%S")
            return self.file_name[-14:]
        except ValueError as e:
            try:
                datetime.datetime.strptime(self.file_name[-12:], "%Y%m%d%H%M")
                return self.file_name[-12:] + "00" # add seconds for mysql DATETIME
            except ValueError as e:
                logger.exception("Not a valid timestamp " + self.file_name)
                return False
    

    def delete_files(self):

        # ADD: removal of .scans from chromatograms
        try:
            os.remove(os.path.join(self.outfiles_dir, self.file_name + ".xml"))
            os.remove(os.path.join(self.outfiles_dir, self.file_name + "_pos.mzXML"))
            if self.experiment == 'METABOLOMICS':
                os.remove(os.path.join(self.outfiles_dir, self.file_name + "_neg.mzXML"))
        except Exception as e:
            logger.exception(e)


if __name__ == "__main__":
   
    # Arguments: experiment (proteomics, metabolomics)
    #            depth (number of files to process, -1 equals all)
    #            email (Y N)
    #
    
    # Machine data needs to be in_dir\experiment_type\machine_name

    # read in db details
    with open(os.path.join(os.getcwd(), "Config", "database-login.json"), "r") as f:
        db_details = json.load(f)

    db_info = {}
    db_info["user"] = db_details["User"]
    db_info["port"] = db_details["Database Port"]
    db_info["database"] = db_details["Database Name"]

    with open(os.path.join(os.getcwd(), "Config", ".maspeqc_gen"), "r") as f:
        db_info["password"] = f.read()

    # set database details
    db = MPMFDBSetUp(db_info["user"], db_info["password"], db_info["database"], "", db_info["port"])

    # get arguments
    experiment_type = sys.argv[1].upper()
    depth = int(sys.argv[2])
    email = sys.argv[3].upper()
    if email == "Y":
        email = True
    else:
        email = False

    # check if running
    if os.path.exists(experiment_type + ".txt"):
        logger.info("Script already running for {}".format(experiment_type))
        sys.exit(1)
    else:
        with open(experiment_type + ".txt", "w") as f:
            f.write("")
        logger.info("Starting processing for {}. Number of runs = {}. Sending email = {}.".format(experiment_type, depth, email))

    # read in directories
    if experiment_type == "METABOLOMICS":
        with open(os.path.join(os.getcwd(), "Config", "dir-metabolomics.csv"), "r") as incsv:
            for line in incsv:
                in_data = line.strip().split("|")
                in_dir = in_data[0]
                out_dir = in_data[1]
                break
    else:
        with open(os.path.join(os.getcwd(), "Config", "dir-proteomics.csv"), "r") as incsv:
            for line in incsv:
                in_data = line.strip().split("|")
                in_dir = in_data[0]
                out_dir = in_data[1]
                break

    # get machine names for experiment type
    run_check = True
    sql = ''
    machine_names = ()

    if experiment_type.strip() == "METABOLOMICS":
        sql = "SELECT machine_name, machine_type FROM machine WHERE use_metab = 'Y'"
    elif experiment_type.strip() == "PROTEOMICS":
        sql = "SELECT machine_name, machine_type FROM machine WHERE use_prot = 'Y'"
    else:
        logger.error("Enter metabolomics or proteomics")
        run_check = False

    if run_check:
        try:
            db.cursor.execute(sql)
            machine_names = db.cursor.fetchall()
        except Exception as e:
            logger.info("Could not get machines")
            logger.exception(e)
            run_check = False

    # get raw files for each machine
    file_formats = ['.mzXML', '.mzML', '.raw', '.wiff', 'wiff2', '.d', '.yep', '.baf', '.fid', '.tdf', '.lcd',
                    '.RAW', '.WIFF', '.WIFF2', '.D', '.YEP', '.BAF', '.FID', '.TDF', '.LCD']
    raw_files = []
    machines = {}

    if run_check:
        if experiment_type == "METABOLOMICS":
            for machine in machine_names:
                for _format in file_formats:
                    raw_files = glob.glob(os.path.join(in_dir, machine[0], 'QC_Metabolomics_*' + _format))
                    if len(raw_files) > 0:
                        raw_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                        machines[machine[0]] = [raw_files, machine[1]]
                        ext_length = len(_format)
                        file_format = _format
                        break
        elif experiment_type == "PROTEOMICS":
            for machine in machine_names:
                for _format in file_formats:
                    raw_files = glob.glob(os.path.join(in_dir, machine[0], 'QC_Proteomics_*' + _format))
                    if len(raw_files) > 0:
                        raw_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                        machines[machine[0]] = [raw_files, machine[1]]
                        ext_length = len(_format)
                        file_format = _format
                        break


    # loop through machines and process raw files
    if run_check:
        for machine in machines:
            logger.info("Machine: " + machine)
            logger.info("Found " + str(len(machines[machine][0])) + " files")
            fs = FileSystem(in_dir, out_dir, machine, experiment_type)  # used in processing and chrom and stats

            # set loop variable
            if depth == -1:
                loop = len(machines[machine][0])
            elif depth > len(machines[machine][0]):
                loop = len(machines[machine][0])
            else:
                loop = depth

            # loop backwards
            for k in range(loop-1, -1, -1):

                # get file name
                _, tail = os.path.split(machines[machine][0][k])
                file_id = tail[:-ext_length]

                # process raw file for mzmine and morpheus metrics
                qc_run = ProcessRawFile(file_id, machines[machine][0][k], machine, experiment_type, fs, db_info, email, machines[machine][1], file_format)

                # only do thermo metrics, pressure and chroms if successful metric (mzmine/morpheus) insert
                if qc_run.run():
                    # process instrument metrics for thermo machines
                    if machines[machine][1] == "thermo":
                        ThermoMetrics(machines[machine][0][k], file_id, experiment_type, db, fs, machine)

                    # extract and add chromatogram data
                    Chromatogram(file_id, fs, experiment_type, machine, db)
            
            # update stats and normalised metrics
            new_stat = Stat(experiment_type, db, machine.strip(),  machines[machine][1], fs)
            new_stat.run()
            
            

        logger.info("FINISHED PROCESSING")
        
    # close database connection and cursor
    db.cursor.close()
    db.db.close()
    
    # remove runtime file
    os.remove(experiment_type + ".txt")
