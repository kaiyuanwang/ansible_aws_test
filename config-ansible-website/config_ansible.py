#!/usr/bin/python
# coding=utf-8

"""
Name: configure_ansible.py

Dependencies:
pip install numpy
pip install pandas
pip install xlrd
pip install xlsxwriter

Description:
1.  Read truecall server details from truecall_server_info.xlsx. Check if varliable has value in var template files to determine if variable is mandatory. truecall_server_info.xlsx is exported from vzw example.
2.  By default, read in template files TrueCall_template.yml, host_template.yml, production_template, and truecall_server_info.xlsx file from config_ansible_input diretory. These files and directories can also be customized with script arguments.
3.  Generate group_vars files (TrueCall.yml, <market>.yml), host_vars files and ansible hosts (production) file. By default, files will be generated under config_ansible_output directory, but can opt to overwrite current configuration under <ansible_dir>/host_vars etc with script arguments.
4.  Old output will be moved to config_ansible_archive directory.
4.  fields of "basic_info" category in truecall_server_info.xlsx are for ansible hosts (production) provisioning. Will not be exported to host/group vars files.
5.  Tested on Windows and Linux with Python 2.7 and Python 3.5.
6.  Processing logs: config_ansible.log

TODO:
1. sanity check on current host and group vars files
1.1. provision gsrsvcs_rpm, truecall_rpm in /opt/ansible/roles/tc_install/vars/main.yml and tc_upgrade_vars/main.yml
    or just put it in truecall_server_info.xlsx
    search, run checksum, and provide available packages for selection
1.2 sanity check if all required files are available
2. age off archive files older than a month
3. enhance regular expression check on input

4. [root@ip-172-31-1-40 ansible]#  ansible-playbook -i production_mumbai tc_install.yml -K --tags="stage,install"
SUDO password: ????



Parameters:
python configure_ansible.py --help

Execute Methods:
1. Mode: configure ansible
    Generate hosts file, host_vars and group_vars files based on templates and truecall_server_info.xlsx file
    1). Put input files and templates under config_ansible_input directory 
    2). Execute "python configure_ansible.py"
    3). production hosts file, host_vars and group_vars files will be generated under config_ansible_output diretory
    Usage:
        python config_ansible.py --server-info-file server_info_output\truecall_server_info_updated_20181126_130442.xlsx’

2. Mode: update-server-info-file
    1). specify --update-server-info-file
    2). Execute "python configure_ansible.py"
    3). truecall_server_info.xlsx will be updated based on vars template files
    Usage:
        python configure_ansible.py --update-server-info-file

3. Mode: provision-si-from-backup
    work with truecall_config_backup.sh to provision server info spreasheet from production backups
    Usage:
        python config_ansible.py --backup-data-dir "c:\Tektronix Work\TrueCall\Truecall_backup_20181119" --provision-si-from-backup

History:
---------
11/01/2018 Kaiyuan Wang 0.1
11/09/2018 Kaiyuan Wang 1.0
11/22/2018 Kaiyuan Wang 1.1
    Add function of updating server_info_file with truecall server backup data.
    Add "server type" column that only reads from related server type when writing yml files.
11/26/2018 Kaiyuan Wang 1.2
    Bug fixing.
    Test with Python 2.7 and Python 3.5.
12/12/2018 Kaiyuan Wang 1.3
    Change var writing to include empty lines in TrueCall.yml.
    Test with truecall_server_info_test.xlsx on Real TrueCall clusters.
12/14/2018 Kaiyuan Wang 1.4
    Update truecall_server_info.xlsx with truecall_rpm and gsrsvcs_rpm fileds, used to generate roles\\tc_install\\vars\\main.yml and roles\\tc_upgrade\\vars\\main.yml files
01/03/2019 Kaiyuan Wang 1.5
    Add logging levels
01/10/2019 Kaiyuan Wang 1.6
    Add copy function for default.yml and config.ini templates
03/22/2019 Kaiyuan Wang 1.7
    refactor each class to be modulized, for stand-alone import

"""   

__author__ = "Kaiyuan Wang"

import os, sys, csv, json, re

#python 2 specific
if sys.version < '3':
    reload(sys)
    sys.setdefaultencoding('utf-8')

import abc
import yaml
import logging
import logging.handlers
import datetime
from argparse import ArgumentParser
from warnings import filterwarnings
import io
try:
    import ConfigParser
except:
    import configparser as ConfigParser
from functools import reduce
from copy import deepcopy
import numpy as np
import pandas as pd
import shutil
from collections import Counter
import tempfile
import boto3

LOG_LEVELS = { 'debug':logging.DEBUG,
            'info':logging.INFO,
            'warning':logging.WARNING,
            'error':logging.ERROR,
            'critical':logging.CRITICAL
            }

"""
def exception_hook(exc_type, exc_value, exc_traceback):
    logger.error(
                "Uncaught exception",
                exc_info=(exc_type, exc_value, exc_traceback)
        )

sys.excepthook = exception_hook



def log():
    def decorator(func):
        def wrapper(*args, **kw):
            logger.info("Running {0}()...".format(func.__name__))
            a=func(*args, **kw) 
            return a
        return wrapper
    return decorator

def set_up_logging(log_level):
    logger = logging.getLogger('ConfigAnsibleLogger')
    logger.setLevel(LOG_LEVELS[log_level])
    log_file=os.path.join(os.getcwd(), 'config_ansible.log')
    formatter = logging.Formatter('[%(asctime)s  %(levelname)s] %(message)s')
    handler = logging.handlers.TimedRotatingFileHandler(log_file, when='D', backupCount=10)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

"""




class MyConfigParser(ConfigParser.ConfigParser): 
    def optionxform(self, optionstr): 
        return optionstr

def del_dict_null(d):
    return {k:v for k,v in d.items() if v != ''}
def intersect_dict(d1, d2):
    return dict(set(d1.items()) & set(d2.items()))


def diff_dict(d1, d2):
    return dict(set(d1.items()) - set(d2.items()))

def merge_dict(d1, d2):
    # d1 with higher priority over d2
    return {k:d1.get(k, d2.get(k)) for k in set(d1.keys())|set(d2.keys())}
def reformat_dict(d):
    return {k.strip():v.strip().lower() if v.strip() in ('FALSE', 'TRUE') else v.strip() for k,v in d.items()}

def mkdir(path):
    if path and not os.path.exists(path) :
        os.makedirs(path)

def check_if_NaN(val):
    if type(val) == float:
        if np.isnan(val):
            return True
    return False



class Base(object):
    __metaclass__ = abc.ABCMeta
    def __init__(self, log_level, use_s3=False):
        if use_s3 is True:
            from log_cfg import logger
            self.logger = logger
        else:
            self.logger = self.set_up_logging(log_level)
        sys.excepthook = self.exception_hook

    
    def exception_hook(self, exc_type, exc_value, exc_traceback):
        self.logger.error(
                    "Uncaught exception",
                    exc_info=(exc_type, exc_value, exc_traceback)
            )

    @staticmethod
    def set_up_logging(log_level):
        logger = logging.getLogger('ConfigAnsibleLogger')
        logger.setLevel(LOG_LEVELS[log_level])
        log_file=os.path.join(os.getcwd(), 'config_ansible.log')
        formatter = logging.Formatter('[%(asctime)s  %(levelname)s] %(message)s')
        handler = logging.handlers.TimedRotatingFileHandler(log_file, when='D', backupCount=10)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def log(func):
        def wrapper(self,*args, **kw):
            self.logger.info("Running {0}()...".format(func.__name__))
            return func(self,*args, **kw) 
        return wrapper



class AnsibleHostParser(Base):
    def __init__(self, log_level, host_file, overwrite, dest_dir, basic_info_dict, use_s3=False, bucket="", data_bucket=""):
        super(AnsibleHostParser, self).__init__(log_level,use_s3)
        #self.logger = set_up_logging(log_level)
        self.host_file = host_file
        self.overwrite = overwrite
        self.dest_dir = dest_dir
          
        self.tc_svr_info = basic_info_dict
        self.host_dict = {}
        self.host_template_dict = {}
        self.use_s3 = use_s3
        if use_s3 is True:
            self.bucket = bucket
            self.data_bucket = data_bucket
            self.s3_client = boto3.client('s3')
        self.parse_ansible_hosts()
 


    def parse_ansible_hosts(self):
        cf = MyConfigParser(allow_no_value=True)
        if self.use_s3 is True:
            obj = self.s3_client.get_object(Bucket=self.data_bucket, Key=self.host_file)
            data=obj['Body'].read().decode('utf-8')
            cf = MyConfigParser(allow_no_value=True)
            cf.read_string(data)
        else:
            cf.read(self.host_file)
        secs = cf.sections()
        for sec in secs:
            self.host_template_dict[sec] = cf.options(sec)

    @Base.log
    def gen_ansible_hostfile(self):
        for market in self.host_dict.keys():
            cf = MyConfigParser(allow_no_value=True)
            for sec in sorted(self.host_dict[market].keys()):
                cf.add_section(sec)
                for obj in sorted(self.host_dict[market].get(sec)):
                    cf.set(sec,obj)
            if self.use_s3 is True:
                temporary_file = tempfile.NamedTemporaryFile()
                #temporary_file.name = "test.txt"
                with open(temporary_file.name, 'w') as f:
                    cf.write(f)
                self.s3_client.upload_file(Filename=temporary_file.name,Bucket=self.data_bucket, Key='/'.join([self.dest_dir, "production_"+market.lower()]))
                os.remove(temporary_file.name)
            else:
                with open(os.path.join(self.dest_dir, "production_"+market.lower()), 'w') as f:
                    cf.write(f)

    @Base.log
    def process_ansible_hosts(self):         
        # configure ansible host file based on hostnames
        # call parse_ansible_hosts
        # output: type_server_mapping, market_mapping, submarket_mapping
        server_type_mapping = {}
        market_mapping = submarket_mapping = market_submarket_mapping = {}
        for d in self.tc_svr_info:
            server_type_mapping.update({d['inventory_hostname']: list(map(lambda s: s.strip(), d['server_type'].upper().split(',')))}) 
       
        tc_svr_df = pd.DataFrame(self.tc_svr_info)
        if not tc_svr_df['submarket'].any():
            market_submarket_mapping = dict(tc_svr_df[['market','inventory_hostname']].groupby('market')['inventory_hostname'].apply(lambda x:set(x)))
        else:
            tc_svr_df['market'] = tc_svr_df['market'].apply(lambda x:x+":children")
            market_mapping = dict(tc_svr_df[['market','submarket']].drop_duplicates(inplace=False).groupby('market')['submarket'].apply(lambda x:set(x)))
            submarket_mapping= dict(tc_svr_df[['submarket','inventory_hostname']].groupby('submarket')['inventory_hostname'].apply(lambda x:set(x)))
            market_submarket_mapping = {k:{vv:submarket_mapping[vv] for vv in v} for k, v in market_mapping.items()}
        
        type_server_mapping = {}
        server_types = set(reduce(lambda x,y:x+y,server_type_mapping.values()))
        for type in server_types:
            type_server_mapping.update({type:[]})
        
        for market in market_submarket_mapping.keys():
            market_dict = deepcopy(self.host_template_dict)
            if isinstance(market_submarket_mapping[market], dict):
                hostnames = reduce(lambda x,y: x|y, market_submarket_mapping[market].values())
            else:
                hostnames = market_submarket_mapping[market]
            for hostname in hostnames:
                 for server_type in server_type_mapping[hostname]:
                    type_server_mapping[server_type].append(hostname)
                    market_dict[server_type].append(hostname)
            if isinstance(market_submarket_mapping[market], dict):
                market_dict.update({market:market_mapping[market]})
                market_dict.update(market_submarket_mapping[market])
            else:
                market_dict.update({market:market_submarket_mapping[market]})
            self.host_dict.update({market.split(':')[0]:market_dict})
            self.gen_ansible_hostfile()
            self.logger.info("Generating ansible config file complete. \nConfig outputs at {0}\n".format(self.dest_dir)+"Exit now!\n")
            if self.use_s3 is False:
                sys.exit("{0} Generating ansible config complete. \nConfig outputs at {1}\n".format(datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S"), self.dest_dir)+"Exit now!")

class AnsibleTemplateParser(Base):
    def __init__(self, log_level, host_template_file, *group_template_file):
        super(AnsibleTemplateParser, self).__init__(log_level)
        #self.logger = set_up_logging(log_level)
        self.hst_tf = host_template_file
        self.grp_tf = group_template_file
        self.tpt_all_w_null = {}
        self.tpt_all = {}

    def parse_tpt(self, tf):
        with io.open(tf, 'r', encoding='utf-8') as file:
            temp = [map(lambda x:x.strip(), f.split(':',1)) for f in file.read().split('\n') if ':' in f and not f.startswith('#')]
            return dict(zip(*zip(*temp)))

    @Base.log
    def process_tpt(self):
        # parse host and group vars yaml files
        if os.path.exists(self.hst_tf):
            tpt_w_null = [self.parse_tpt(self.hst_tf)]
        if self.grp_tf:
            tpt_w_null += [ self.parse_tpt(tf) for tf in self.grp_tf ]

        self.tpt_all_w_null = reduce(merge_dict, tpt_w_null)
        self.tpt_all = del_dict_null(self.tpt_all_w_null)
        return self.tpt_all, self.tpt_all_w_null



class SvrInfoParser(Base):
    def __init__(self,  log_level, truecall_server_info_file, default_yml, source_j2tmpt_dir, use_s3=False, bucket="", data_bucket=""):
        super(SvrInfoParser, self).__init__(log_level,use_s3)
        #self.logger = set_up_logging(log_level)
        self.tc_svr_info_file = truecall_server_info_file
        self.val_res = {}  
        self.basic_info_dict = {}
        self.use_s3 = use_s3
        if use_s3 is True:
            self.bucket = bucket
            self.data_bucket = data_bucket
            self.s3_client = boto3.client('s3')
            #self.s3_resource = boto3.resource('s3')
        self.pd_load_si_file() 

        self.tc_svr_info = []
        self.svr_grp_info = {}
        self.svr_hst_info = []
        self.mandatory_svr_info = set([])
        self.opt_field_ck = {
            'etl': set(['etl_multi_cyl_enabled', 'cyl_host']), 
            'cyl': set(['cyl_days_to_keep', 'cyl_fragments_to_keep']), 
            'tcs':set([])}
        self.fld_ck = {}
        self.pd_load_si_file()
        self.default_yml = default_yml
        self.source_j2tmpt_dir = source_j2tmpt_dir 

    @Base.log
    def pd_load_si_file(self):
        if self.use_s3 is True:
            obj = self.s3_client.get_object(Bucket=self.bucket, Key=self.tc_svr_info_file) 
            data= obj['Body'].read()
            self.tc_svr_info_df = pd.read_excel(io.BytesIO(data), sheet_name='truecall_server_info')
        else:
            self.tc_svr_info_df = pd.read_excel(self.tc_svr_info_file, sheet_name='truecall_server_info')
        self.tc_svr_info_fields = self.tc_svr_info_df.loc[6:, 'field']



    @Base.log
    def pd_update_tc_si_file(self, tpt_all, tpt_all_w_null, from_s3=False):
        # load in truecall server info file
        # load in yaml files
        # cross check and update original truecall_server_info.xlsx with new rows at bottom
        #   -with value mandatory
        #   -no value optional
        append_rows = []
        for f in tpt_all_w_null.keys():
            if f not in set(self.tc_svr_info_df['field']):
                if f in tpt_all.keys():
                    append_rows.append([f, tpt_all[f], True])
                else:
                    append_rows.append([f, '', False])
                #self.tc_svr_info_df = pd.concat([self.tc_svr_info_df, append_rows], sort=False)
        append_df = pd.DataFrame(append_rows,columns=['field', 'default value', 'mandatory'])
        self.tc_svr_info_df = pd.concat([self.tc_svr_info_df, append_df], sort=False)
        if self.use_s3 is True:
            output = io.BytesIO()
            writer = pd.ExcelWriter(output, engine='xlsxwriter')
        else:
            writer = pd.ExcelWriter(self.tc_svr_info_file, engine='xlsxwriter')
        workbook = writer.book
        format_lft_aln = workbook.add_format({'align': 'left'})
        self.tc_svr_info_df.to_excel(writer, 'truecall_server_info', index=False)
        worksheet = writer.sheets['truecall_server_info']
        worksheet.set_column('A:J',15, format_lft_aln)
        writer.save()
        if self.use_s3 is True:     
            data = output.getvalue()
            #self.s3_resource.Bucket(self.bucket).put_object(Key=self.tc_svr_info_file, Body=data)
            self.s3_client.put_object(Bucket=self.bucket,Key=self.tc_svr_info_file,Body=data)

        self.logger.info("Appended {0} rows to {1}!\n".format(len(append_rows), self.tc_svr_info_file)+json.dumps(append_rows)+"Exit now!\n")
        if self.use_s3 is False:
            sys.exit("Appended {0} rows to {1}!\n".format(len(append_rows), self.tc_svr_info_file)+json.dumps(append_rows)+"\nExit now!")


    @Base.log
    def pd_val_svr_info(self):
        self.val_res_df = self.tc_svr_info_df.copy()
        for i in range(4,len(self.val_res_df.columns)):
            column = self.tc_svr_info_df.columns[i]
            self.val_res_df[column] = self.val_res_df.apply(lambda x:check_if_NaN(x['default value']) and check_if_NaN(x[column]) and x.mandatory and (set(self.val_res_df.loc[5,column].split(',')) & set(map(lambda y:'common_lte_'+y, x['server type'].split(','))) or 'all' in x['server type'].split(',')), axis=1)
        if self.val_res_df.iloc[:,4:].sum().sum():
            self.val_res = {c: self.val_res_df.loc[i,'field'] for c in self.val_res_df.columns[4:] for i in self.val_res_df.index if self.val_res_df.loc[i,c]==True}
            self.logger.error("Ansible configuration file generation failed!\ntruecall_server_info file missing mandatory fields:\n "+json.dumps(self.val_res))
            if self.use_s3 is False:
                sys.exit("Ansible configuration file generation failed!\ntruecall_server_info file missing mandatory fields:\n "+json.dumps(self.val_res))  

    @Base.log
    def pd_gen_var_files(self, dest_dir, dest_gvd, dest_hvd):
        self.pd_val_svr_info()

        # use tc_svr_info_df 
        # if mandatory, fill up with default value
        # check for common values 
        # check on existing rules of ansible common values. 
        #   *********expand on customer input**********
        #   common value -> dest_gvf/TrueCall.yml
        #   submarket value -> dest_gvf/<submarket>.yml
        #   individual value -> dest_hvd/<inventory_hostname>.yml
        # tc_svr_info_df.loc[:,[False,False]+[True]*(len(tc_svr_info_df.columns)-2)]
        #tc_svr_info_df.iloc[:,[1,2,3]]

        # server_info + template
        #mkdir(dest_gvd)
        #mkdir(dest_hvd)
        
        #logger.info(self.tc_svr_info_df.iloc[3,4:])
        vtch_server_types = reduce(lambda x,y: x | y, map(lambda x:set(x.split(',')), self.tc_svr_info_df.iloc[5,4:])) 
        total_server_types = list(map(lambda x:x.split('_')[-1], vtch_server_types))
        self.logger.info(total_server_types)
        for i in range(4,len(self.tc_svr_info_df.columns)):
            column = self.tc_svr_info_df.columns[i]
            market = self.tc_svr_info_df.loc[3,column]
            submarket = self.tc_svr_info_df.loc[4,column]
            server_type = list(map(lambda x:x.strip(), set(self.tc_svr_info_df.loc[5,column].split(','))))
            vdr_tech = self.tc_svr_info_df.loc[6,column]
            self.logger.info(server_type)

            # DONE: if any server of server type in the submarket (or market if empty submarket) has data, not write default data 
            # TODO: ADD OTHER SERVER TYPES data in yml  

            self.tc_svr_info_df[column] = self.tc_svr_info_df.apply(lambda x:str(x[column]).lower() if str(x[column]).lower() in ["true", "false"] else x[column], axis=1)


            self.tc_svr_info_df[column] = self.tc_svr_info_df.apply(lambda x:x['default value'] if check_if_NaN(x[column]) and not check_if_NaN(x['default value']) and ((set(map(lambda m:'_'.join([vdr_tech,m]), x['server type'].split(','))) & set(server_type)) or not set(x['server type'].split(',')) & set(total_server_types)) else x[column], axis=1)


        # extract basic_info
        self.basic_info_dict = self.tc_svr_info_df.loc[:5, [False, True, False, False]+[True]*(len(self.tc_svr_info_df.columns)-4) ].set_index('field').T.to_dict('records')
        #basic_info_index_set = set(self.tc_svr_info_df[self.tc_svr_info_df['category'].isin(['basic_info'])].index)
        basic_info_index_set = set(self.tc_svr_info_df.loc[:5].index)

        # generate common_dict
        common_dict, common_indexes, partial_common_dict = self.pd_gen_common_dict(self.tc_svr_info_df, basic_info_index_set, {})
        self.logger.info("partial_common_dict: ")
        self.logger.info(partial_common_dict)
        # generate market_common_dicts
        markets = set(self.tc_svr_info_df.iloc[3,4:])
        market_dict = dict(zip(*[markets,[[]]*len(markets)]))
        group_common_dicts = [{"TrueCall":common_dict}]
        host_dicts = []
        self.logger.info(markets)

        for m in markets:
            m_partial_common_dict = {}
            #m_servers = [y['inventory_hostname'] for y in filter(lambda x:x['market']==m, self.basic_info_dict)]
            m_server_columns = [y for y in self.tc_svr_info_df.columns if self.tc_svr_info_df.loc[3,y]==m]
            m_svr_info_df = pd.concat([self.tc_svr_info_df.iloc[:,0:4], self.tc_svr_info_df.loc[:,m_server_columns]],axis=1)
            m_common_dict, m_indexes, m_partial_common_dict = self.pd_gen_common_dict(m_svr_info_df, basic_info_index_set | common_indexes, partial_common_dict)
            self.logger.info("m_partial_common_dict: ")
            self.logger.info(m_partial_common_dict)
            if m_common_dict:
                group_common_dicts.append({m: m_common_dict}) 
            
            # generate host_dicts
            ###################  
            for h in m_server_columns:
                h_svr_info_df = pd.concat([self.tc_svr_info_df.iloc[:,0:4], self.tc_svr_info_df.loc[:,h]],axis=1)
                h_common_dict, h_indexes, h_partical_common_dict= self.pd_gen_common_dict(h_svr_info_df, basic_info_index_set | common_indexes | m_indexes, m_partial_common_dict)
                self.logger.info("h_partical_common_dict")
                self.logger.info(h_partical_common_dict)
                if h_common_dict:
                    host_dicts.append({h: h_common_dict})

        self.write_var_files(group_common_dicts, dest_gvd)
        self.write_var_files(host_dicts, dest_hvd)
        self.write_roles_var_files(dest_dir)
        self.copy_var_tmpt_files(dest_gvd, dest_dir)
        
        return self.basic_info_dict

    @Base.log
    def write_var_files(self, var_dicts, dest_dir):
        for var_dict in var_dicts:
            #self.logger.info(var_dict)
            for yml_name, yml_info in var_dict.items():
                #content = [(k,str(yml_info[k])) for k in sorted(yml_info.keys()) if not check_if_NaN(yml_info[k]) and not str(yml_info[k]) == 'nan' ]
                content = [(k,str(yml_info[k])) for k in self.tc_svr_info_fields if k in yml_info.keys() and not check_if_NaN(yml_info[k]) and not str(yml_info[k]) == 'nan'] 
                if yml_name == "TrueCall":
                    content += [(k,'') for k in self.tc_svr_info_fields if k in yml_info.keys() and (check_if_NaN(yml_info[k]) or str(yml_info[k]) == 'nan')] 
                #self.logger.debug(json.dumps(content))

                if content:
                    if self.use_s3 is True:
                        data = ""
                        for c in content:
                            data += ": ".join(c)+'\n'

                        #self.logger.debug(data)
                        self.s3_client.put_object(Bucket=self.data_bucket, Key="/".join([dest_dir, yml_name+'.yml']), Body=data)
                    else:
                        if sys.version < '3':
                            with open(os.path.join(dest_dir, yml_name+'.yml'), 'w') as file:
                                for c in content:
                                    file.write(': '.join(c) + '\n')
                        else:
                            with open(os.path.join(dest_dir, yml_name+'.yml'), 'w', encoding='utf-8') as file:
                                for c in content:
                                    file.write(': '.join(c) + '\n')

    @Base.log
    def write_roles_var_files(self, dest_dir):
        # write ansible/roles/tc_install/vars/main.yml and ansible/roles/tc_upgrade/vars/main.yml
        self.logger.debug(self.basic_info_dict)
        truecall_rpms = set(filter(lambda y: not check_if_NaN(y), map(lambda x:x['truecall_rpm'], self.basic_info_dict)))
        gsrsvcs_rpms = set(filter(lambda y: not check_if_NaN(y), map(lambda x:x['gsrsvcs_rpm'], self.basic_info_dict)))
        self.logger.info(truecall_rpms)
        self.logger.info(gsrsvcs_rpms)
        roles_vars = {'truecall_rpm':truecall_rpms.pop(), 'gsrsvcs_rpm':gsrsvcs_rpms.pop()}

        for role in ['tc_install', 'tc_upgrade']:
            if self.use_s3 is True:
                data = yaml.dump(roles_vars, default_flow_style=False)
                self.logger.debug(data)
                self.s3_client.put_object(Bucket=self.data_bucket, Key="/".join([dest_dir, 'roles', role,'vars','main.yml']), Body=data)
            else:
                mkdir(os.path.join(dest_dir,'roles', role, 'vars'))
                with open(os.path.join(dest_dir,'roles', role, 'vars','main.yml'), 'w') as yml_file:
                    yaml.dump(roles_vars, yml_file, default_flow_style=False)

    @Base.log
    def copy_var_tmpt_files(self, dest_gvd, dest_dir):
        dest_gvd_all = "/".join([dest_gvd,'all'])
        install_template_dir = "/".join([dest_dir,'roles', 'tc_install', 'templates'])

        if self.use_s3 is True:
            def get_dest_file(source_file, dest_dir):
                return "/".join([dest_dir, source_file.split('/')[-1]])
            copy_source = {'Bucket': self.data_bucket, 'Key': self.default_yml}
            self.s3_client.copy(copy_source, self.data_bucket, get_dest_file(self.default_yml,dest_gvd_all)) 

            for tmpt_key in [x['Key'] for x in self.s3_client.list_objects(Bucket='lambda-data-kaiyuan')['Contents'] if x['Key'].startswith('config_input') and x['Key'].endswith('j2')]:
                copy_source = {'Bucket': self.data_bucket, 'Key': tmpt_key}
                self.s3_client.copy(copy_source, self.data_bucket, get_dest_file(tmpt_key, install_template_dir))

        else:
            
            for dir in dest_gvd_all, install_template_dir:
                mkdir(dir)
            shutil.copy(self.default_yml, dest_gvd_all)
            for tmpt in os.listdir(self.source_j2tmpt_dir):
                if tmpt.endswith('j2'):
                    shutil.copy(os.path.join(self.source_j2tmpt_dir,tmpt), install_template_dir)

    @Base.log
    def pd_gen_common_dict(self, common_info_df, excluded_indexes, partial_excluded_dict):
        partial_common_dict ={} 
        """
        self.logger.info("partial_common_dict")
        self.logger.info(partial_common_dict)     
        self.logger.info("partial_excluded_dict")
        self.logger.info(partial_excluded_dict)  
        self.logger.info("common_info_df")
        self.logger.info(common_info_df)
        """
        if partial_excluded_dict.keys():
            for i in partial_excluded_dict.keys():
                try:
                    common_info_df.loc[i]=common_info_df.loc[i].replace(partial_excluded_dict[i], np.nan)
                except Exception as e:
                    self.logger.info(e)
        self.logger.info("after common_info_df")
        #self.logger.info(common_info_df)
        # common with same values
        try:
            common_indexes = set([i for i in common_info_df.index if len(list(filter(lambda x: not check_if_NaN(x), set(common_info_df.iloc[i, 4:]))))==1]) - excluded_indexes
        except Exception as e:
                    self.logger.info(e)
        #self.logger.info("common_indexes")
        #self.logger.info(common_indexes)

        #common_df = common_info_df.iloc[list(common_indexes), 4:]
        #common_dict = common_df.set_index('field').T.to_dict('records')[0]

        common_dict = {}
        for index in common_indexes:
            common_dict.update({common_info_df.loc[index,"field"]:list(filter(lambda x: not check_if_NaN(x),set(common_info_df.iloc[index,4:])))[0]})



        partial_common_indexes = set([i for i in common_info_df.index if Counter(common_info_df.iloc[i, 4:]).most_common()[0][1]>len(common_info_df.iloc[i, 4:])/2]) - excluded_indexes - common_indexes

        partial_common_df = pd.concat([common_info_df.loc[list(partial_common_indexes), 'field'], common_info_df.iloc[list(partial_common_indexes), 4:].apply(lambda x:Counter(x).most_common()[0][0], axis=1)], axis=1)
        if partial_common_df.to_dict().get(0):
            partial_common_dict.update(partial_common_df.to_dict().get(0))
        partial_common_dict.update(partial_excluded_dict)
        partial_common_dict_1 = partial_common_df.set_index('field').T.to_dict('records')[0]
        common_dict.update(partial_common_dict_1)
        self.logger.info("common_dict")
        self.logger.info(common_dict)

        # common with regular expression
        if sys.version < '3': 
            re_common_dict = {common_info_df.loc[i, 'field']: common_info_df.iloc[i, 4].replace(common_info_df.columns[4], u'"{{ inventory_hostname }}"') for i in common_info_df.index if i not in excluded_indexes and list(common_info_df.columns[4:]) == list(map(lambda x: re.split('-', x)[0].strip('\"') if isinstance(x, unicode) else x, common_info_df.iloc[i,4:]))}
        else:
            re_common_dict = {common_info_df.loc[i, 'field']: common_info_df.iloc[i, 4].replace(common_info_df.columns[4], u'"{{ inventory_hostname }}"') for i in common_info_df.index if i not in excluded_indexes and list(common_info_df.columns[4:]) == list(map(lambda x: re.split('-', x)[0].strip('\"') if isinstance(x, str) else x, common_info_df.iloc[i,4:]))}
        re_common_indexes = set(self.tc_svr_info_df[common_info_df['field'].isin(re_common_dict.keys())].index)
        self.logger.info("re_common_dict")
        self.logger.info(re_common_dict)

        common_dict.update(re_common_dict)
        common_indexes = common_indexes | re_common_indexes



        return common_dict, common_indexes, partial_common_dict

    # depreciated
    def load_si_file(self):
        # parse truecall_server_info csv file

        with open(self.tc_svr_info_file,'rt') as file:
            reader = csv.DictReader(file)
            columns=reader.fieldnames
            for row in reader:
                if row['hostname']:
                    if row['hostname'] == 'mandatory':
                        self.mandatory_svr_info = set([i for i in row.keys() if row[i] == 'mandatory'])
                    elif row['hostname'] != 'notes':
                        self.tc_svr_info.append(reformat_dict(del_dict_null(row)))
        return self.tc_svr_info


    # depreciated
    def val_svr_info(self):
        self.fld_ck = {k:v|self.mandatory_svr_info for k,v in self.opt_field_ck.items()}
        for s in self.tc_svr_info:
            missing_field = []
            for svr_type in self.fld_ck.keys():
                if svr_type in s['server_type']:
                    for field in self.fld_ck[svr_type]:
                        try: 
                            s.get(field)
                        except:
                            missing_field.append(field)
            if missing_field:
                self.val_res.update({s['hostname']:missing_field})
        if self.val_res:
            self.logger.error("truecall_server_info.csv missing mandatory fields: ", self.val_res)
            raise KeyError("truecall_server_info.csv missing mandatory fields: ", self.val_res)

    # depreciated
    def gen_vars_file(self, tpt_all, dest_gvf, dest_hvd):
        self.val_svr_info()
        svr_info_w_tpt = [merge_dict(d, tpt_all) for d in self.tc_svr_info]
        for d in svr_info_w_tpt: d.pop('server_type')
        self.svr_grp_info = dict(reduce(intersect_dict, svr_info_w_tpt))
        self.svr_hst_info = [diff_dict(d, self.svr_grp_info) for d in svr_info_w_tpt]
        with open(dest_gvf, 'w') as file:
            #for k in sorted(self.svr_grp_info.keys()):
            #    file.write(': '.join([k, self.svr_grp_info[k]]) + '\n')
            self.logger.info(self.tc_svr_info_df['field'])
            for k in self.tc_svr_info_fields:
                if self.svr_grp_info.get(k):
                    file.write(': '.join([k, self.svr_grp_info[k]]) + '\n')

        for d in self.svr_hst_info:
            with open(os.path.join(dest_hvd, d['hostname']+'.yml'), 'w') as file:
                #for k in sorted(d.keys()):
                #    file.write(': '.join([k, d[k]]) + '\n')

                for k in self.tc_svr_info_fields:
                    if d.get(k):
                        file.write(': '.join([k, self.svr_grp_info[k]]) + '\n')    

class SiteBackupParser(Base):
    'python config_ansible.py --provision-si-from-backup --backup-data-dir "c:\Tektronix Work\TrueCall\Truecall_backup_20181119" --server-info-file config_ansible_input\truecall_server_info_jio.xlsx'
    # parse all other server related information from backup data
    # TODO: capture and parse csr file

    def __init__(self, log_level, backup_data_dir, server_info_output):
        super(SiteBackupParser, self).__init__(log_level)
        #self.logger = set_up_logging(log_level)
        self.backup_data_dir = backup_data_dir
        #"C:\\Tektronix Work\\TrueCall\\20161124 JIO Reliance\\17.3 upgrade\\Truecall_backup_20181119\\"
        self.backup_dirs = filter(os.path.isdir, map(lambda x:os.path.join(self.backup_data_dir,x), os.listdir(self.backup_data_dir)))
        self.server_info_output = server_info_output
        # 'C:\\TrueCall_Scripts\\SCRIPTS\\deployment\\ansible deployment\\config_ansible\\test\\test.xlsx'
        self.tc_info = {}
        self._parse_backup_files()

    def _parse_tcaccess(self,tcaccess):
        tcaccess_dict = {}
        cf = MyConfigParser(allow_no_value=True)
        cf.read(tcaccess)
        secs = cf._sections
        _ldap_sec = secs['LDAP']
        _database_sec = secs['Database']
        #ldap_sec = map(lambda (x,y) :(x.strip("\""),y.strip("\"")), _ldap_sec.items())
        #return dict(ldap_sec)
        ret_data = {}
        for x,y in _ldap_sec.items():
            ret_data.update({x:y})
        ret_data.update({'DbHost':_database_sec['DbHost']})
        return ret_data

        
        

    def _parse_backup_files(self):
        for bck_dir in self.backup_dirs: 
            tcaccess = os.path.join(bck_dir, 'etc', 'tcaccess.ini')
            config = os.path.join(bck_dir, 'etc', 'config.ini')
            pre_upgrade_info = os.path.join(bck_dir, 'sys_info', 'pre_upgrade_info.txt')
            daemon_cron = os.path.join(bck_dir,'cron','daemon')
            self.logger.info(bck_dir)
            tc_host = '_'.join(os.path.basename(bck_dir).split('_')[:2])
            self.tc_info[tc_host] = {}
            is_tcs, is_cyl, is_etl, is_lsr, is_qams = 0, 0, 0, 0, 0

            

           
            # tcs: timezone
            if os.path.exists(pre_upgrade_info):
                with open(pre_upgrade_info) as file:
                    content = file.readlines()
                    for line in content:
                        if 'zoneinfo' in line:
                            self.tc_info[tc_host].update({'timezone':'/'.join(line.split('/')[-2:]).strip()})
                            break
            if os.path.exists(config):
                with open(config) as file:
                    content = file.readlines()
                    tech = set(filter(lambda x: any([x in c for c in content]), ('gsm', 'umts', 'lte', 'GSM', 'UMTS', 'LTE'))).pop().lower()
                    vdr_tech = "common_"+tech
                    server_type = []


                    for line in content:
                        if not line.startswith('#'): 
                            if 'label=TcsTcpServer_COMMON_'+tech.upper() in line:
                                is_tcs = 1
                                server_type.append(vdr_tech+'_tcs')
                            if 'label=cylinderd_COMMON_'+tech.upper() in line:
                                is_cyl = 1
                                server_type.append(vdr_tech+'_cyl')
                            if 'label=processor-common-'+tech in line:
                                is_etl = 1
                                server_type.append(vdr_tech+'_etl')
                            if 'label=LSR_Server_COMMON_'+tech.upper() in line:
                                is_lsr = 1
                                server_type.append(vdr_tech+'_lsr')

                        if is_cyl:
                            # cyl: parse lsr dirs
                            self.tc_info[tc_host].update({'cyl_host':tc_host})
                            if not line.startswith('#'):
                                if 'label=cylinderd_COMMON_LTE' in line:
                                    cyl_proc_no = line.split('/')[0]
                                
                                if line.startswith(cyl_proc_no) and 'args' in line and '--port' in line:
                                    cyl_args = dict(map(lambda x: map(lambda y: y.strip("\"").strip(), x.split('=')), line.split('|')))
                                    self.tc_info[tc_host].update({'common_lte_cyl_port':cyl_args['--port']})
                                    if cyl_args.get('--ne-db-connection'):
                                        self.tc_info[tc_host].update({'tcs_host':cyl_args.get('--ne-db-connection')})


                                
                                if '--tmp-dir' in line:
                                    lsr_args = dict(map(lambda x: map(lambda y: y.strip("\"").strip(), re.sub('\d/args=','',x).split('=')), line.split('|')))
                                    self.tc_info[tc_host].update({'lsr_tmp_dir': lsr_args['--tmp-dir'], 'lsr_out_dir': lsr_args['--out-dir']})
                            
                        if is_tcs:
                            if not line.startswith('#') and '--cylinderd-address' in line:
                                tcs_args = dict(map(lambda x: map(lambda y: y.strip("\"").strip(), re.sub('\d/args=','',x).split('=')), line.split('|')))
                                # tcs: --cylinderd-address
                                cylinderd_addresses = tcs_args['--cylinderd-address'].split(',')
                                if len(cylinderd_addresses) > 1:
                                    self.tc_info[tc_host].update({'qams_cyl_list':re.sub(':\d+','',tcs_args['--cylinderd-address'])}) 
                                    self.tc_info[tc_host].update({'qams_port':tcs_args['--port']})
                                    is_qams = 1
                                    server_type.append(vdr_tech+'_qams')
                                else:
                                    self.tc_info[tc_host].update({'cyl_list':re.sub(':\d+','',tcs_args['--cylinderd-address'])})
                                    self.tc_info[tc_host].update({'common_lte_tcs_port':tcs_args['--port']})
                                # tcs: ssl cert dir and name
                                cert_dir_files = tcs_args.get('--certificate-file')
                                key_dir_files = tcs_args.get('--private-key-file')
                                if cert_dir_files:
                                    self.tc_info[tc_host].update({'ssl_cert_dir':re.sub('/[a-zA-Z,_]+.crt','/',cert_dir_files.split('=')[-1])})
                                    self.tc_info[tc_host].update({'ssl_cert_file':re.sub('[a-zA-Z,_/]+/','',cert_dir_files.split('=')[-1])})
                                if key_dir_files:
                                    self.tc_info[tc_host].update({'ssl_key_dir':re.sub('/[a-zA-Z,_]+.key','/',key_dir_files.split('=')[-1])})
                                    self.tc_info[tc_host].update({'ssl_key_file':re.sub('[a-zA-Z,_/]+/','',key_dir_files.split('=')[-1])})
                                
                        if is_etl:
                            if not line.startswith('#') and '--input-stream-port' in line:
                                etl_args = dict(map(lambda x: map(lambda y: y.strip("\"").strip(), re.sub('\d/args=','',x).split('=')), line.split('|')))
                                self.tc_info[tc_host].update({
                                    'common_lte_etl_port':etl_args['--input-stream-port'],
                                    'cyl_host':etl_args['--cyl-host']})

                                if etl_args.get('--ne-db-connection'):
                                        self.tc_info[tc_host].update({'tcs_host':etl_args.get('--ne-db-connection')})
            
            # cyl: check cleanup crons
            if is_cyl and os.path.exists(daemon_cron):
                with open(daemon_cron) as file:
                    content = file.readlines()
                    for line in content:
                        if not line.startswith('#'):
                            if "cylinder-cleanup.sh" in line:
                                self.tc_info[tc_host].update({'cyl_days_to_keep': line.split(' ')[6].strip('-')})
                            if 'cylinder-cleanup-fragments.sh' in line:
                                self.tc_info[tc_host].update({'cyl_fragments_to_keep': line.split(' ')[6].strip('-')})
                        
                        
            if os.path.exists(tcaccess):
                tcaccess_info = self._parse_tcaccess(tcaccess)
                if is_tcs:
                # parse tcaccess for ldap info
                    
                    if tcaccess_info.get('Enable', 0):
                        self.tc_info[tc_host].update({  
                            'ldap_search_base': tcaccess_info.get('SearchBase'),
                            'ldap_superuser_dn': tcaccess_info.get('SuperUserDn'),
                            'ldap_superuser_dn_password': tcaccess_info.get('SuperUserPassword'),
                            'ldap_uri': tcaccess_info.get('URI'),
                            'ldap_enabled':tcaccess_info.get('Enable'),
                            'ldap_groupsearch_enabled':tcaccess_info.get('EnableGroupSearch'),
                            'ldap_search_attribute_group_dn':tcaccess_info.get('SearchAttributeForGroupDn'),
                            'ldap_search_attribute_group_name':tcaccess_info.get('SearchAttributeForGroupName'),
                            'ldap_search_attribute_user_email':tcaccess_info.get('SearchAttributeForUserEmail'),
                            'ldap_search_attribute_user_firstname':tcaccess_info.get('SearchAttributeForUserFirstName'),
                            'ldap_search_attribute_user_lastname':tcaccess_info.get('SearchAttributeForUserLastName'),
                            'ldap_username_filter':tcaccess_info.get('UsernameFilter')
                            }) 
                    self.tc_info[tc_host].update({'tcs_host':tc_host})
                elif tcaccess_info.get('DbHost') != 'localhost' and is_etl or is_cyl or is_lsr:
                    #logger.info(tcaccess_info)
                    self.tc_info[tc_host].update({'tcs_host':tcaccess_info.get('DbHost')})

            self.tc_info[tc_host].update({  'inventory_hostname': tc_host,
                                            'vdr_tech': vdr_tech,
                                            'server_type': ','.join(server_type)
                                            })
        

    @Base.log
    def pd_write_si_file(self, tc_svr_info_df):
        self.tc_svr_info_df = tc_svr_info_df
        self.tc_info_df = pd.DataFrame(self.tc_info)
        cols_sorted_info = sorted(self.tc_info_df.columns)
        cols_sorted_backups = list(self.tc_svr_info_df.columns) + list(cols_sorted_info)
        self.tc_si_backup_df=tc_svr_info_df.set_index('field').join(self.tc_info_df[cols_sorted_info])
        self.tc_si_backup_df.reset_index(inplace=True)
        cols = self.tc_si_backup_df.columns
        #logger.info(self.tc_si_backup_df)
        writer = pd.ExcelWriter(self.server_info_output, engine='xlsxwriter')
        workbook = writer.book
        format_lft_aln = workbook.add_format({'align': 'left'})
        #self.tc_si_backup_df[cols[1::-1]|cols[2:]].to_excel(writer, 'truecall_server_info', index=False)
        self.tc_si_backup_df[cols_sorted_backups].to_excel(writer, 'truecall_server_info', index=False)
        worksheet = writer.sheets['truecall_server_info']
        worksheet.set_column(0,len(cols),15, format_lft_aln)
        writer.save()
        self.logger.info("Updated truecall server info spreadsheet with backup data of {0} servers. \nWriting to {1}.\n".format(len(self.tc_info.keys()), self.server_info_output)+"Exit now!\n")
        if self.use_s3 is False:
            sys.exit("Updated truecall server info spreadsheet with backup data of {0} servers. \nWriting to {1}.\n".format(len(self.tc_info.keys()), self.server_info_output)+"Exit now!")

def process_args(args):

    # Load destination directories from config
    default_output_dir = os.path.join(os.getcwd(), 'config_ansible_output')
    default_archive_dir = os.path.join(os.getcwd(), 'config_ansible_archive')
    if not args.overwrite_config_files and os.path.exists(default_output_dir) :
        shutil.move(default_output_dir, os.path.join(default_archive_dir,'_'.join(['config_ansible_output', datetime.datetime.now().strftime("%Y%m%d_%H%M%S")])))
    dest_dirs = list(map(lambda x:os.path.join(args.ansible_dir,x) if args.overwrite_config_files else os.path.join(default_output_dir, x), ['', 'group_vars', 'host_vars']))
    self.logger.info("dest_dirs: \n"+json.dumps(dest_dirs))

    for dir in dest_dirs: 
        mkdir(dir)
    mkdir(os.path.dirname(args.server_info_output))

    sip_input = [args.log_level, args.truecall_server_info_file, args.default_yml, args.source_j2tmpt_dir]
    sbp_input = [args.log_level, args.backup_data_dir, args.server_info_output]
    atp_input = [args.log_level, args.host_var_template, args.group_var_template]
    ahp_input = [args.log_level, args.hosts_file_template, args.overwrite_config_files, dest_dirs[0]]#, basic_info_dict]

    mode = {"G":args.generate_ansible_config,"P":args.provision_si_from_backup,"U":args.update_server_info_file}

    return sip_input, sbp_input, atp_input, ahp_input, mode, args.print_template_vars, dest_dirs


if __name__ == '__main__':

    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    parser = ArgumentParser(description="Configure Ansible related parameter files")
    parser.add_argument('-G', '--generate-ansible-config', dest='generate_ansible_config',          
        help='Mode 1: Generate ansible config files from server_info_file',
        default=False, action='store_true')
    parser.add_argument('-U', '--update-server-info-file', dest='update_server_info_file',          
        help='Mode 2: Update truecall_server_info_file with host and group var templates',
        default=False, action='store_true')
    parser.add_argument('-P', '--provision-si-from-backup', dest='provision_si_from_backup',          
        help='Mode 3: Provision server information file from TrueCall server backup data',
        default=False, action='store_true')
    """ 
    Mode 4 TBD
    parser.add_argument('-C', '--check-ansible-config', dest='check_ansible_config',          
        help='Sanity check for existing ansible configurations: production host files, group vars and host vars files against truecall_server_info.xlsx',
        default=False, action='store_true')
    """
    parser.add_argument('-s', '--server-info-file', dest='truecall_server_info_file',          
        help='truecall server info file', default=os.path.join(os.getcwd(), 'config_ansible_input', 'truecall_server_info.xlsx'), action='store')
    parser.add_argument('-o', '--overwrite-config-files', dest='overwrite_config_files',          
        help='When set to True, the script will overwrite yml files under ansible/group_vars and ansible/host_vars. When False, generate new TrueCall.yml under ansible_dir/config_ansible_output',
        default=False, action='store_true')
    parser.add_argument('--host-var-template', dest='host_var_template',
        help='Full directory of host template yml file', default=os.path.join(os.getcwd(), 'config_ansible_input', 'host_template.yml'), action='store')
    parser.add_argument('--group-var-template', dest='group_var_template',
        help='Full directory of group template yml file.', default=os.path.join(os.getcwd(), 'config_ansible_input', 'TrueCall_template.yml'), action='store')
    parser.add_argument('--hosts-template', dest='hosts_file_template',          
        help='Full directory of ansible hostfile template.', default=os.path.join(os.getcwd(), 'config_ansible_input', 'production_template'), action='store')
    parser.add_argument('--default-yml', dest='default_yml',          
        help='Default yml config file.', default=os.path.join(os.getcwd(), 'config_ansible_input', 'default.yml'), action='store')
    parser.add_argument('--source-j2tmpt-dir', dest='source_j2tmpt_dir',          
        help='Full directory of source j2 templates dir.', default=os.path.join(os.getcwd(), 'config_ansible_input'), action='store')
    parser.add_argument('--ansible-dir', dest='ansible_dir',
        help='Ansible directory. Mandatory if --overwrite-config-files or --check-ansible-config', action='store')
    parser.add_argument('--backup-data-dir', dest='backup_data_dir',
        help='directory of TrueCall server backup data. use together with --provision-si-from-backup', default=os.path.join(os.getcwd(), 'config_ansible_input', 'truecall_server_info.xlsx'), action='store')
    parser.add_argument('--server-info-output', dest='server_info_output',
        help='server info file output after updated with backup data. use together with --provision-si-from-backup', default=os.path.join(os.getcwd(), 'server_info_output', 'truecall_server_info_updated_'+datetime.datetime.now().strftime("%Y%m%d_%H%M%S")+'.xlsx'), action='store')
    parser.add_argument('--tc-rpm', dest='tc_rpm',
        help='name of tc rpm to be installed. i.e. TrueCall-Server-17.3.0.16-0-gaa28f3b-el7-x86_64.rpm', default=os.path.join(os.getcwd(), 'server_info_output', 'truecall_server_info_updated_'+datetime.datetime.now().strftime("%Y%m%d_%H%M%S")+'.xlsx'), action='store')
    
    parser.add_argument('--print-template-varibles', dest='print_template_var',          
        help='Print values in host and group templates as provisioned',
        default=False, action='store_true')

    parser.add_argument("-l", "--log-level",
        action="store", dest="log_level", default="info",
        help="log level for logfile at same location of script\navailable: critical error warning [info] debug")

    args = parser.parse_args() 

    logger = set_up_logging(args.log_level)

    logger.info("""ansible config provisioning starts. """)

    sip_input, sbp_input, atp_input, ahp_input, mode, print_template_vars, dest_dirs = process_args(args)


    # Parse truecall_server_info file 
    sip = SvrInfoParser(*sip_input)
    truecall_server_info = sip.tc_svr_info_df

    # Generate vars files
    if mode["G"]:
    # Parse and generate host (production) files
        sip_output = sip.pd_gen_var_files(*dest_dirs)
        ahp_input.append(sip_output)
        ahp = AnsibleHostParser(ahp_input)
        ahp.process_ansible_hosts()
    # Update server_info_file with truecall server backup data
    elif mode["P"]:
        sbp = SiteBackupParser(*sbp_input)
        sbp.pd_write_si_file(truecall_server_info)

    # Update server_info_file with host and group var templates
    elif mode["U"]:
        # Parse ansible host and group templates host_template.yml and TrueCall_template.yml
        atp = AnsibleTemplateParser(*atp_input)
        atp_output = atp.process_tpt()
        logger.info("template_all: \n"+json.dumps(atp_output[0]))
        sip.pd_update_tc_si_file(atp_output)
    

    if print_template_vars:
        for k in sorted(template_all.keys()):
                    print(': '.join([k, template_all[k]]))

    
    """ 
    TODO check_ansible_config
    if args.check_ansible_config:
        hosts_files = [f for f in os.listdir(ansible_dir) if f.startswith('production_')]
        for hf in hosts_files:
            ahp = AnsibleHostParser(os.path.join(ansible_dir, hf), False, dest_dirs[0], {})
            htd = ahp.host_template_dict
            market = hf[len('production_'):].upper()
            hostnames = reduce(lambda x,y: x+y, [htd[sm] for sm in htd[market+':children']])
            for hn in hostnames:
                atp = AnsibleTemplateParser(os.path.join(ansible_dir, 'host_vars', hn+'.yml'), os.path.join(ansible_dir, 'group_vars', market+'.yml'), os.path.join(ansible_dir, 'group_vars', 'TrueCall.yml'))
                vars_all_w_null, vars_all = atp.process_tpt()
    """



    """
    # test data based on vzw files
    # vzw test
    templates = ['C:\\TrueCall_Scripts\\SCRIPTS\\deployment\\ansible deployment\\ansible\\host_vars\\host_template.yml', 'C:\\TrueCall_Scripts\\SCRIPTS\\deployment\\ansible deployment\\ansible\\group_vars\\Truecall.yml']
    atp = AnsibleTemplateParser(*templates)
    template_all_w_null, template_all = atp.process_tpt()
    vzw_manual_files = map(lambda y:os.path.join('C:\\TrueCall_Scripts\\SCRIPTS\\deployment\\ansible deployment\\vzw_ansible_example', y), ['carotrclqspp99v.yml', 'UPNY.yml', 'TrueCall.yml'])
    atp_vzw_manual_market = AnsibleTemplateParser(*vzw_manual_files[1:])
    vzw_manual_market_w_null, vzw_manual_market = atp_vzw_manual_market.process_tpt()
    vzw_manual_market_input = diff_dict(vzw_manual_market, template_all)
    
    

    # df_tpt.to_csv('C:\\TrueCall_Scripts\\SCRIPTS\\deployment\\ansible deployment\\test.csv')
    # df_tpt.loc[df_tpt['default value'].notnull()]
    # set(result['field'].values.tolist()) - set(template_all_w_null.keys()) 
    # tc_svr_info_df[tc_svr_info_df.columns[2]]
    df_tpt = pd.read_excel('C:\\TrueCall_Scripts\\SCRIPTS\\deployment\\ansible deployment\\truecall_server_info.xlsx',sheetname='truecall_server_info')
    vzw_mkt_df = pd.DataFrame(list(vzw_manual_market_input.items()), columns=['field', 'vzw_market'])
    result = pd.merge(df_tpt, vzw_mkt_df, how='left', on='field')
    writer = pd.ExcelWriter('C:\\TrueCall_Scripts\\SCRIPTS\\deployment\\ansible deployment\\truecall_server_info_1.0.xlsx', engine='xlsxwriter')
    result.to_excel(writer, 'tc_svr_info_w_vzw_output', index=False)
    worksheet = writer.sheets['tc_svr_info_w_vzw_output']
    worksheet.set_column('A:J',15)
    worksheet.add_format({'align': 'left'})
    writer.save()
    """






