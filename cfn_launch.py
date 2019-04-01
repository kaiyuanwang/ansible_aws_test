#!/usr/bin/python
# -*- coding:utf8 -*-

"""
Name: cfn_launch.py

Dependencies:
pip install requests
pip install boto3
    IAM -> USERS -> Add user
    aws configure -> access key + secret key
    C:\\Users\\kwang1\\.aws\\credentials
        [default]
        aws_access_key_id = YOUR_ACCESS_KEY
        aws_secret_access_key = YOUR_SECRET_KEY
pip install awscli
pip install PyYAML

Functions:
1. Create, describe and delete AWS CloudFormation Stackes using boto3.
2. Provide local IP address to enable EC2 access to local laptop only. 
3. When creating stacks, if not provided, stack name will be appended with current timestamp.
4. Describe stack will generate Xshell access config file for stacks in "CREATE_COMPLETE" status.
5. Describe stack will show stack information until "DELETE_COMPLETE".
6. Delete stack will delete Xshell access config file of the stack.
7. Serialize stack info data to cfn-StackInfo.json.
8. Serialize stack parameters to cfn-parameters.json with local ip information.

History:
---------
03/04/2019 Kaiyuan Wang 0.1
    Functions using awscli for stack creation. Stack describe and delete with boto3.
03/07/2019 Kaiyuan Wang 1
    Change stack create to boto3. Encapsulation stack management into class CfnClient. Documentation.

TODO:
    open interfaces
"""

__author__ = "Kaiyuan Wang"

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
from argparse import ArgumentParser
from warnings import filterwarnings

""" 
TODO: currently check on stacks created by this script, add option to check all stacks in region
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
    log_file=os.path.join(os.getcwd(), 'logs', 'cfn_launch.log')
    formatter = logging.Formatter('[%(asctime)s  %(levelname)s] %(message)s')
    handler = logging.handlers.TimedRotatingFileHandler(log_file, when='D', backupCount=10)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = set_up_logging('info')


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
    with open(os.path.join('cfn_template','cfn-parameters.json'), 'w') as fh: 
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
        #if not os.path.exists(config_basename):
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
    def __init__(self, cfn_dir, region='ap-southeast-2', ):
        self.region = region
        self.cfn_conn = boto3.client('cloudformation', region_name=self.region)
        self.stack_info_json = os.path.join(cfn_dir,'cfn-StackInfo.json')
        self.stack_info_dict = {}
        #with open(self.template_yaml) as yh:
        #    self.cfn_template = yaml.load(yh)
            #self.cfn_template = json.dumps(yh)


    def load_stack_info(self):
        try:
            with open(self.stack_info_json) as fh:
                self.stack_info_dict = json.load(fh)
        except Exception as e:
            logger.error("{0} loading error. {1}".format(self.stack_info_json, e))
            self.stack_info_dict = {}



    def dump_stack_info(self):
        with open(self.stack_info_json, 'w') as fh: 
            json.dump(self.stack_info_dict, fh)

    @log()
    def query_cfn_status(self, stack_id_list):
        # change to use *list
        logger.info(stack_id_list)
        stack_dict_tmp = {}
        for stack_id in stack_id_list:
            boto_resp = self.cfn_conn.describe_stacks(StackName=stack_id)
            #output_dict = {d["OutputKey"]:d["OutputValue"] for d in boto_resp['Stacks'][0]['Outputs']}
            stack_details = boto_resp['Stacks'][0]
            stack_name = stack_id.split('/')[1]
            stack_status = stack_details['StackStatus']
            stack_parameters = stack_details['Parameters']
            logger.info("stack_details:\n{0}".format(stack_details))
            logger.info("stack_details['StackStatus']: {0}".format(stack_details['StackStatus']))
            logger.info("stack_details['Parameters']:\n{0}".format(stack_details['Parameters']))

            stack_info = {"stack_name":stack_name, "stack_status":stack_status, "stack_parameters":stack_parameters}

            if stack_status == "DELETE_COMPLETE":
                logger.info(" ".join([stack_name, stack_status]))
                continue

            if 'Outputs' in stack_details.keys():
                stack_output = {d["OutputKey"]:d["OutputValue"] for d in stack_details['Outputs']}
                logger.info("stack_details['Outputs']:\n{0}".format(stack_details['Outputs']))
                #print("ControlPublicIp: "+stack_output['ControlPublicIp'])
                
                if not stack_status.startswith("DELETE"):
                    try:
                        XshellAccess.create(stack_name, stack_output['ControlPublicIp'])
                    except:
                        pass
                stack_info.update({"stack_output":stack_output})
            
            stack_dict_tmp.update({stack_id:stack_info})

            
        return stack_dict_tmp




    @log()
    def build_cfn(self, cfn_template, stack_name):
        ''' aws cli connection. AWS cli supports JASON only
        # yaml2json for aws cli
        if re.split("\.", options.cfn_template)[-1] in ["yml", "yaml"]:
            cfn_template =  re.split("\.", options.cfn_template)[0]+'.json'
            yaml2json(options.cfn_template, cfn_template)
        else:
            cfn_template = options.cfn_template
        # cfn-StackId.json: [{"StackId": "arn:aws:cloudformation:ap-southeast-2:813556749890:stack/AnsibleTest-20190302115934/73f8a4f0-3c86-11e9-9b63-02181cf5d610"}]
        #aws cloudformation create-stack --stack-name example-cli-stack --template-body file://cfn_ansible_test_one_server.json --parameters file://cfn-parameters.json --region ap-southeast-2
        aws_cmd = "aws cloudformation create-stack --stack-name {0} --template-body file://{1} --parameters file://{2} --region {3}".format(stack_name, cfn_template, "cfn-parameters.json", options.region)
        p = subprocess.Popen(aws_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(p.communicate())
        stack_id_dict = json.loads(p.communicate()[0].decode('utf-8'))

        '''

        self.cfn_parameters = []
        self.cfn_template = cfn_template
        self.stack_name = stack_name
        self.validate_cfn()
        self.cfn_parameters = fetch_local_ip()

        self.load_stack_info()
        logger.debug(self.stack_info_dict.keys())
        self.stack_info_dict = self.query_cfn_status(self.stack_info_dict.keys())
        logger.debug(self.stack_info_dict.keys())
     

        if self.stack_info_dict:
            create_confirm=input("Stacks {0} in system. \nAre you sure you want to create another stack from template {1} (y or n)?\n".format(list(self.stack_info_dict.keys()),self.cfn_template))
            if create_confirm != "y":
                sys.exit("Stack creation aborted. Script exit now!")

        try:
            with open(self.cfn_template, 'r', encoding='utf8') as fh:
                stack_id = self.cfn_conn.create_stack(
                    StackName=self.stack_name,
                    TemplateBody=fh.read(),
                    Parameters=self.cfn_parameters,
                    # when creating IAM
                    Capabilities=['CAPABILITY_IAM']
                    )['StackId']
        except  Exception as e:
            logger.error("{0} loading error. {1}".format(self.cfn_template, e))
            sys.exit("{0} loading error. {1}".format(self.cfn_template, e))
        logger.debug(stack_id)
        stack_id_list = list(self.stack_info_dict.keys())+[stack_id]
        logger.debug(stack_id_list)
        self.stack_info_dict= self.query_cfn_status(stack_id_list)
        self.dump_stack_info()

        logger.info("""Create cloudformation stack finished. """)
        sys.exit("Stack creation initiated. Exit now!")


    @log()
    def describe_cfn(self, input_stack_id=""):
        if input_stack_id:
            logger.info(input_stack_id)
            self.print_cfn_desc([input_stack_id])
        else:
            self.load_stack_info()
            self.stack_info_dict = self.print_cfn_desc(self.stack_info_dict.keys())
            self.dump_stack_info()
        
        if not self.stack_info_dict:
            logger.info("""Describe cloudformation stack finished. \nNo cloudformatation stack can be found. Exit now!""")
            sys.exit("No cloudformatation stack can be found. Exit now!")
        else:
            logger.info("""Describe cloudformation stack finished. """)
            sys.exit("""Describe cloudformation stack finished. """)
        

    def print_cfn_desc(self, stack_id_list):
        stack_info_dict = self.query_cfn_status(stack_id_list)
        if not stack_info_dict:
            return stack_info_dict
            

        for si in stack_info_dict.keys():
            print(si)
            logger.info(stack_info_dict[si])
            print("Stack Status: "+stack_info_dict[si].get('stack_status'))
            output = stack_info_dict[si].get("stack_output")
            if output:
                for k,v in sorted(output.items()):
                    print(': '.join([k,v]))
        return stack_info_dict


    @log()
    def delete_cfn(self,input_stack_id=""):
        if input_stack_id:
            stack_info_dict = self.query_cfn_status([input_stack_id])
            self.del_cfn_action(stack_info_dict)
        else:
            self.load_stack_info()
            self.stack_info_dict = self.query_cfn_status(self.stack_info_dict)
            if not self.stack_info_dict:
                sys.exit("No cloudformatation stack created by {0} is in the system. Exit now!".format(sys.argv[0]))
            else:
                self.del_cfn_action(self.stack_info_dict)
                


    def del_cfn_action(self, stack_info_dict):

        stack_list_remain, stack_list_delete = [], []
        if not stack_info_dict:
            sys.exit('Stack already DELETE_COMPLETE. Exit now!')

        for stack_id in stack_info_dict.keys():
            
            stack_status = stack_info_dict[stack_id].get('stack_status')
            print(stack_id, stack_status)
            if stack_status.startswith('DELETE'):
                print('Already initiated DELETE action.')
                continue
            delete_confirm=input("Are you sure you want to delete this stack (y or n)?\n") 
            if delete_confirm == "y":
                try:
                    self.cfn_conn.delete_stack(StackName=stack_id)
                    logger.info(stack_info_dict)
                    XshellAccess.delete(stack_info_dict[stack_id].get('stack_name'))
                except:
                    pass
                finally:
                    stack_list_delete.append(stack_id)
            else:
                stack_list_remain.append(stack_id) 

        logger.info("""Delete cloudformation stack initiation finished. """)
        if stack_list_delete:
            sys.exit("Stack deleting initiated. Exit now!")
        else:
            sys.exit("Stack deleting aborted. Exit now!")  


    def validate_cfn(self):
        try:
            with open(self.cfn_template, 'r', encoding='utf8') as fh:
                response = self.cfn_conn.validate_template(TemplateBody=fh.read())
        except Exception as e:
            sys.exit(': '.join([self.cfn_template,str(e)]))
        


if __name__ == '__main__':

    parser = ArgumentParser(description="Launch, describe and delete cloudformation stacks") 
    parser.add_argument('-t', '--template', dest='cfn_template',          
        help='Cloudformation template. Default: cfn_test.yaml. 3 server template: cfn_ansible_test.yaml',
        default='cfn_test.yaml', action='store')
    parser.add_argument('-d', '--dir', dest='cfn_dir',          
        help='Cloudformation dir. Default: cfn_template. ',
        default='cfn_template', action='store')
    parser.add_argument('-n', '--stack-name', dest='stack_name',          
        help='Cloudformation stack name', action='store')
    parser.add_argument('-i', '--stack-id', dest='stack_id',          
        help='Cloudformation stack id. Used by stack-describe, stack-delete', 
        default='', action='store')
    parser.add_argument('-p', '--parameter-file', dest='parameter_file',          
        help='Cloudformation parameter file. default: cfn-parameter.json',
        default='cfn-parameter.json', action='store')
    parser.add_argument('-r', '--region', dest='region',          
        help='Cloudformation parameter file. default: ap-southeast-2',
        default="ap-southeast-2", action='store')
    parser.add_argument('-m', '--mode', dest='mode',          
        help='Cloudformation management mode. Available options: create, delete, describe.',
        default="describe", action='store')
    parser.add_argument('-l', '--log-level', dest='log_level',          
        help='Availalbe log_level: debug, info, warning, error, critical.',
        default="info", action='store')
    args = parser.parse_args()  

    logger.info("""script start. \n{0}""".format(args))


    # CREATE CfnClient INSTANCE
    cfn_client = CfnClient(args.cfn_dir)

    # CREATE STACK
    if args.mode == "create":
        if args.stack_name:
            stack_name = args.stack_name
        else:
            stack_name = '-'.join(re.findall("([0-9a-zA-Z]+)",args.cfn_template)[:-1]+[datetime.datetime.now().strftime("%Y%m%d%H%M%S")])
        cfn_client.build_cfn(os.path.join(args.cfn_dir,args.cfn_template), stack_name)

    elif args.mode == "describe":
        cfn_client.describe_cfn(args.stack_id)

    elif args.mode == "delete":
        cfn_client.delete_cfn(args.stack_id)

    else:
        sys.exit("Not a valid mode option!")


