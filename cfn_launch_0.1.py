#!/usr/bin/python
# -*- coding:utf8 -*-

import requests
import re
import os
import json
import yaml
import boto3
import botocore
import sys
import signal
import logging
import logging.handlers
import datetime
import subprocess
import shutil
try:
    import ConfigParser
except:
    import configparser as ConfigParser
from optparse import OptionParser
from warnings import filterwarnings

""" 
TODO: currently check on stacks created by this script, add option to check all stacks in region
TODO: change to functions and classes, and logging
TODO: load in the existing stack id json, and ask if more than one running. DONE
TODO: interact: ask which stack to delete, try! DONE
TODO: retrieve server ip from instance instead of output
"""



LOG_LEVELS = { 'debug':logging.DEBUG,
            'info':logging.INFO,
            'warning':logging.WARNING,
            'error':logging.ERROR,
            'critical':logging.CRITICAL
            }



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
    """Set up logger."""
    logger = logging.getLogger('ConfigAnsibleLogger')
    logger.setLevel(LOG_LEVELS[log_level])
    log_file=os.path.join(os.getcwd(), 'cfn_launch.log')
    formatter = logging.Formatter('[%(asctime)s  %(levelname)s] %(message)s')
    handler = logging.handlers.TimedRotatingFileHandler(log_file, when='D', backupCount=10)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

def fetch_local_ip():
    response = requests.get("http://txt.go.sohu.com/ip/soip")
    ip = re.findall(r'\d+.\d+.\d+.\d+',response.text)
    pub_ip = ip[0]
    

    local_ip_param = [
                        {
                            "ParameterKey": "SSHLocation",
                            "ParameterValue": pub_ip+"/32",
                            "ResolvedValue": "string"
                        }
                    ]
    with open('cfn-parameters.json', 'w') as fh: 
        json.dump(local_ip_param, fh)
    return local_ip_param

def yaml2json(yaml_file, json_file):
    with open(yaml_file, 'r', encoding='utf8') as fh:
      datastream = yaml.load(fh)
    with open(json_file, 'w') as fh: 
        json.dump(datastream, fh)

class MyConfigParser(ConfigParser.ConfigParser): 
    def optionxform(self, optionstr): 
        return optionstr
    
    """Virtually identical to the original method, but delimit keys and values with '=' instead of ' = '"""
    def write(self, fp):
        if self._defaults:
          fp.write("[%s]\n" % DEFAULTSECT)
          for (key, value) in self._defaults.items():
            fp.write("%s = %s\n" % (key, str(value).replace('\n', '\n\t')))
          fp.write("\n")
        for section in self._sections:
          fp.write("[%s]\n" % section)
          for (key, value) in self._sections[section].items():
            if key == "__name__":
              continue
            if (value is not None) or (self._optcre == self.OPTCRE):

              # This is the important departure from ConfigParser for what you are looking for
              key = "=".join((key, str(value).replace('\n', '\n\t')))

            fp.write("%s\n" % (key))
          fp.write("\n")

class XshellAccess(object):
    @staticmethod
    def create(stack_name, control_ip):
        config_basename = stack_name+'.xsh'
        if not os.path.exists(config_basename):
            aws_config_template = 'C:\\Users\\kwang1\\Documents\\NetSarang\\Xshell\\Sessions\\AWS\\template.xsh'
            config_dir = os.path.dirname(aws_config_template)
            config_dict = {}
            cf = MyConfigParser(allow_no_value=True)
            cf.read(aws_config_template)
            cf['CONNECTION']['Host'] = control_ip
            with open(config_basename, 'w') as fh:
                cf.write(fh)
    @staticmethod
    def delete(stack_name):
        os.remove(stack_name+'.xsh')


class CfnClient(object):
    def __init__(self, region='ap-southeast-2'):
        self.region = region
        self.cfn_conn = boto3.client('cloudformation', region_name=self.region)
        self.stack_info_json = 'cfn-StackInfo.json'
        self.stack_info_dict = {}
        #with open(self.template_yaml) as yh:
        #    self.cfn_template = yaml.load(yh)
            #self.cfn_template = json.dumps(yh)


    def load_stack_info(self):
        try:
            with open(self.stack_info_json) as fh:
                self.stack_info_dict = json.load(fh)

        except:
            logger.error("{0} loading error. {1}".format(stack_info_json, e))
            self.stack_info_dict = {}



    def dump_stack_info(self):
        with open(self.stack_info_json, 'w') as fh: 
            json.dump(self.stack_info_dict, fh)

    def query_cfn_status(self, stack_id_list):
        # change to use *list
        stack_dict_tmp = {}
        for stack_id in stack_id_list:
            boto_resp = self.cfn_conn.describe_stacks(StackName=stack_id)
            #output_dict = {d["OutputKey"]:d["OutputValue"] for d in boto_resp['Stacks'][0]['Outputs']}
            stack_details = boto_resp['Stacks'][0]
            stack_name = stack_id.split('/')[1]
            stack_status = stack_details['StackStatus']
            stack_parameters = stack_details['Parameters']
            logger.info("stack_info:\n{0}".format(stack_info))
            logger.info("stack_info['StackStatus']: {0}".format(stack_details['StackStatus']))
            logger.info("stack_info['Parameters']:\n{0}".format(stack_details['Parameters']))

            if 'Outputs' in stack_details.keys():
                stack_output = {d["OutputKey"]:d["OutputValue"] for d in stack_details['Outputs']}
                logger.info("stack_info['Outputs']:\n{0}".format(stack_details['Outputs']))
                #print("ControlPublicIp: "+output_dict['ControlPublicIp'])
                
                XshellAccess.create(stack_name, output_dict['ControlPublicIp'])


            if stack_status != "DELETE_COMPLETE":
                stack_dict_tmp.update({stack_id:{"stack_name":stack_name, "stack_status":stack_status, "stack_parameters":stack_parameters, "stack_output":stack_output}})
            else: 
                logger.info(" ".join(stack_name, stack_status))
        return stack_dict_tmp




    @log()
    def build_cfn(self, cfn_template, stack_name):
        self.cfn_parameters = []
        self.cfn_template = cfn_template
        self.stack_name = stack_name
        self.validate_cfn()

        self.cfn_parameters.append(fetch_local_ip())

        self.load_stack_info()
        self.stack_info_dict = self.query_cfn_status(self.stack_info_dict.keys())

     

        if self.stack_info_dict:
            create_confirm=input("Stacks {0} in system. \nAre you sure you want to create another stack from (y or n): {1}?\n".format(self.stack_info_dict.keys(),self.cfn_template))
            if create_confirm != "y":
                sys.exit("Stack creation aborted. Script exit now!")

        try:
            with open(self.cfn_template, 'r', encoding='utf8') as fh:
                self.stack_id = self.cfn_conn.create_stack(
                    StackName=self.stack_name,
                    TemplateBody=fh.read(),
                    Parameters=self.cfn_parameters
                    )['StackId']
        except  Exception as e:
            logger.error("{0} loading error. {1}".format(self.cfn_template, e))
            sys.exit("{0} loading error. {1}".format(self.cfn_template, e))

        stack_id_list = self.stack_info_dict.keys().append(stack_id)
        self.stack_info_dict= self.query_cfn_status()
        self.dump_stack_info()

        logger.info("""Create cloudformation stack finished. """)
        sys.exit("Stack creation initiated. Exit now!")


    @log()
    def describe_cfn(self, input_stack_id=""):
        if input_stack_id:
            logger.info(input_stack_id)
            self.print_cfn_desc([input_stack_id])
        else:
            self.stack_info_dict = self.print_cfn_desc(self.stack_info_dict.keys())
            self.dump_stack_info()
        
        logger.info("""describe cloudformation stack finished. """)

    def print_cfn_desc(self, stack_id_list):
        stack_info_dict = self.query_cfn_status(stack_id_list)
        if not stack_info_dict:
            logger.info("""Describe cloudformation stack finished. \nNo cloudformatation stack can be found. Exit now!""")
            sys.exit("No cloudformatation stack can be found. Exit now!")

        for si in stack_info_dict.keys():
            print(si)
            print("Stack Status: "+stack_info[si].get('stack_status'))
            output = stack_info_dict[si].get("stack_output")
            if output:
                for k,v in sorted(output.items()):
                    print(': '.join([k,v]))
        return stack_info_dict


    @log()
    def delete_cfn(self,input_stack_id=""):
        if input_stack_id:
            stack_info_dict = self.query_cfn_status([input_stack_id])
            del_cfn_action(stack_info_dict)
        else:
            self.load_stack_info()
            self.stack_info_dict = self.query_cfn_status(self.stack_info_dict)
            if not self.stack_info_dict:
                sys.exit("No cloudformatation stack created by {0} is in the system. Exit now!".format(sys.argv[0]))
            else:
                del_cfn_action(self.stack_info_dict)
                


    def del_cfn_action(self, stack_info_dict):

        stack_list_remain, stack_list_delete = [], []
        for stack_id in stack_info_dict.keys():
            
            stack_status = stack_info_dict[stack_id].get(stack_status)
            print(stack_id, stack_status)
            if stack_status.startswith('DELETE'):
                print('Already initiated DELETE action.')
                pass
            delete_confirm=input("Are you sure you want to delete this stack (y or n): "+'?\n') 
            if delete_confirm == "y":
                try:
                    self.cfn_conn.delete_stack(StackName=stack_id)
                    XshellAccess.delete(stack_info_dict[stack_id].get('stack_name'))
                except:
                    pass
                finally:
                    stack_list_delete.append(stack_id_dict)
            else:
                stack_list_remain.append(stack_id_dict) 

        logger.info("""delete cloudformation stack initiation finished. """)
        if stack_list_delete:
            sys.exit("Stack deleting initiated. Exit now!")
        else:
            sys.exit("Stack deleting aborted. Exit now!")  


    def validate_cfn(self):
        try:
            with open(self.cfn_template, 'r', encoding='utf8') as fh:
                response = self.cfn_conn.validate_template(TemplateBody=fh.read())
        except Exception as e:
            sys.exit(': '.join([cfn_template,str(e)]))
        


if __name__ == '__main__':
    logger = set_up_logging('info')
    parser = OptionParser() 
    parser.add_option('-t', '--template', dest='cfn_template',          
        help='Cloudformation template. Default: cfn_ansible_test_one_server.yaml. 3 server template: cfn_ansible_test.yaml',
        default='cfn_ansible_test_one_server.yaml', action='store')
    parser.add_option('-n', '--stack-name', dest='stack_name',          
        help='Cloudformation stack name', action='store')
    parser.add_option('-i', '--stack-id', dest='stack_id',          
        help='Cloudformation stack id. Used by stack-describe, stack-delete', action='store')
    parser.add_option('-p', '--parameter-file', dest='parameter_file',          
        help='Cloudformation parameter file. default: cfn-parameter.json',
        default='cfn-parameter.json', action='store')
    parser.add_option('-r', '--region', dest='region',          
        help='Cloudformation parameter file. default: ap-southeast-2',
        default="ap-southeast-2", action='store')
    parser.add_option('-m', '--mode', dest='mode',          
        help='Cloudformation management mode. Available options: stack-create, stack-delete, stack-describe.',
        default="stack-describe", action='store')
    (options, largs) = parser.parse_args() 

    logger.info("""script start. \n{0}""".format(options))
    cfn_conn = boto3.client('cloudformation', region_name=options.region)

    if options.stack_name:
        stack_name = options.stack_name
    else:
        stack_name = '-'.join(re.findall("([0-9a-zA-Z]+)",options.cfn_template)[:-1]+[datetime.datetime.now().strftime("%Y%m%d%H%M%S")])
   

    # CREATE STACK
    if options.mode == "stack-create":
        logger.info("""create cloudformation stack starts. """)



        local_ip_param = fetch_local_ip()

        """ yaml2json for aws cli
        if re.split("\.", options.cfn_template)[-1] in ["yml", "yaml"]:
            cfn_template =  re.split("\.", options.cfn_template)[0]+'.json'
            yaml2json(options.cfn_template, cfn_template)
        else:
            cfn_template = options.cfn_template
        """
        cfn_template = options.cfn_template

        # cfn-StackId.json: [{"StackId": "arn:aws:cloudformation:ap-southeast-2:813556749890:stack/AnsibleTest-20190302115934/73f8a4f0-3c86-11e9-9b63-02181cf5d610"}]
        try:
            with open('cfn-StackId.json') as fh:
                stack_list = json.load(fh)
        except:
            stack_list = []

        if stack_list:
            create_confirm=input("Stacks {0} already in system. \nAre you sure you want to create another stack from (y or n): {1}?\n".format(stack_list,options.cfn_template))
            if create_confirm != "y":
                sys.exit("Stack creation aborted. Script exit now!")

        """
        aws cli create
        #aws cloudformation create-stack --stack-name example-cli-stack --template-body file://cfn_ansible_test_one_server.json --parameters file://cfn-parameters.json --region ap-southeast-2
        aws_cmd = "aws cloudformation create-stack --stack-name {0} --template-body file://{1} --parameters file://{2} --region {3}".format(stack_name, cfn_template, "cfn-parameters.json", options.region)
        p = subprocess.Popen(aws_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(p.communicate())
        stack_id_dict = json.loads(p.communicate()[0].decode('utf-8'))
        """        

        """
        boto3 create
        """
        with open(cfn_template, 'r', encoding='utf8') as f:
            response = cfn_conn.create_stack(StackName=stack_name,TemplateBody=f.read(), Parameters=local_ip_param)
        stack_id_dict = {'StackId': response['StackId']}


        stack_list.append(stack_id_dict)
        with open('cfn-StackId.json', 'w') as fh: 
            json.dump(stack_list, fh)
        logger.info("""create cloudformation stack finished. """)
        sys.exit("Stack creation initiated. Exit now!")
    
    # DESCRIBE STACK    
    elif options.mode == "stack-describe":
        logger.info("""describe cloudformation stack starts. """)

        if options.stack_id:
            stack_list = [{'StackId':options.stack_id}]
        else:
            try:
                with open('cfn-StackId.json') as fh:
                    stack_list = json.load(fh)
            except:
                stack_list = []

        logger.info(stack_list)
        if not stack_list:
            logger.info("""describe cloudformation stack finished. """)
            sys.exit("No cloudformatation stack created by {0} are active. Exit now!".format(sys.argv[0]))
        for stack_id_dict in stack_list:
            print('\n',stack_id_dict)
            boto_resp = cfn_conn.describe_stacks(StackName=stack_id_dict['StackId'])
            #output_dict = {d["OutputKey"]:d["OutputValue"] for d in boto_resp['Stacks'][0]['Outputs']}
            stack_info = boto_resp['Stacks'][0]
            stack_name = stack_id_dict['StackId'].split('/')[1]

            logger.info("stack_info:\n{0}".format(stack_info))
            logger.info("stack_info['StackStatus']: {0}".format(stack_info['StackStatus']))
            print("Stack Status:",stack_info['StackStatus'])
            logger.info("stack_info['Parameters']:\n{0}".format(stack_info['Parameters']))
            

            # change to try
            if 'Outputs' in stack_info.keys():
                output_dict = {d["OutputKey"]:d["OutputValue"] for d in stack_info['Outputs']}
                logger.info("stack_info['Outputs']:\n{0}".format(stack_info['Outputs']))
                #print("ControlPublicIp: "+output_dict['ControlPublicIp'])
                for k,v in sorted(output_dict.items()):
                    print(": ".join([k,v]))
                
                XshellAccess.create(stack_name, output_dict['ControlPublicIp'])

        logger.info("""describe cloudformation stack finished. """)
    
    # DELETE STACK
    elif options.mode == "stack-delete":
        logger.info("""delete cloudformation stack starts. """)
        if options.stack_id:
            stack_list = [options.stack_id]
        else:
            try:
                with open('cfn-StackId.json') as fh:
                    stack_list = json.load(fh)
            except:
                stack_list = []
        if not stack_list:
            sys.exit("No cloudformatation stack created by {0}. Exit now!".format(sys.argv[0]))
        stack_list_remain, stack_list_delete = [], []
        for stack_id_dict in stack_list:
            delete_confirm=input("Are you sure you want to delete stack (y or n): "+stack_id_dict['StackId']+'?\n') 
            if delete_confirm == "y":
                try:
                    cfn_conn.delete_stack(StackName=stack_id_dict['StackId'])
                    stack_name = stack_id_dict['StackId'].split('/')[1]
                    XshellAccess.delete(stack_name)
                except:
                    pass
                finally:
                    stack_list_delete.append(stack_id_dict)
            else:
                stack_list_remain.append(stack_id_dict)
        

        # remove deleted stacks from tracking
        with open('cfn-StackId.json', 'w') as fh: 
            json.dump(stack_list_remain, fh)
        
        logger.info("""delete cloudformation stack initiation finished. """)
        if stack_list_delete:
            sys.exit("Stack deleting initiated. Exit now!")
        else:
            sys.exit("Stack deleting aborted. Exit now!")  


    else:
        sys.exit("Not a valid mode option!")