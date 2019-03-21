#!/usr/bin/python
# -*- coding:utf8 -*-

"""
Name: cfn_generate.py

History:
---------
03/14/2019 Kaiyuan Wang 0.1
    Functions using troposphere for cloudformation creations.
03/19/2019 Kaiyuan Wang 1.0
    1. Encapsulate CfnGenerator
    2. Add ansible packages
    3. Add control, slave rsa
    4. Change to ArgumentParser and usage nargs
    5. Add DependsOn slaves
    6. Replace server_name in cfn files
# TODO: 
    1. encapsulate data 
    2. open interfaces

"""



"""
troposphere examples 
https://github.com/cloudtools/troposphere/blob/master/examples/EC2InstanceSample.py
https://github.com/cloudtools/troposphere/blob/master/examples/Autoscaling.py
https://github.com/cloudtools/troposphere/blob/master/examples/VPC_single_instance_in_subnet.py
https://github.com/kaiyuanwang/troposphere/blob/master/examples/CloudFormation_Init_ConfigSet.py
https://github.com/cloudtools/troposphere/blob/master/troposphere/cloudformation.py
"""
import re
import os
import json
import yaml
import sys
import signal
import logging
import logging.handlers
import datetime
from argparse import ArgumentParser
from warnings import filterwarnings

from troposphere import Base64, Select, FindInMap, GetAtt, GetAZs, Join, Sub, Output, If, And, Not, Or, Equals, Condition
from troposphere import Parameter, Ref, Tags, Template
from troposphere.cloudformation import Init, InitFile, InitFiles, Metadata, InitConfig, Authentication, AuthenticationBlock
from troposphere.cloudfront import Distribution, DistributionConfig
from troposphere.cloudfront import Origin, DefaultCacheBehavior
from troposphere.ec2 import PortRange
from troposphere.ec2 import SecurityGroupIngress
from troposphere.ec2 import SecurityGroup
from troposphere.ec2 import Instance, NetworkInterfaceProperty, PrivateIpAddressSpecification
from troposphere.policies import CreationPolicy, ResourceSignal



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
    logger = logging.getLogger('GenerateAnsibleLogger')
    logger.setLevel(LOG_LEVELS[log_level])
    log_file=os.path.join(os.getcwd(), 'logs', 'cfn_generate.log')
    formatter = logging.Formatter('[%(asctime)s  %(levelname)s] %(message)s')
    handler = logging.handlers.TimedRotatingFileHandler(log_file, when='D', backupCount=10)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

logger = set_up_logging('info')


DEFAULT_CONFIG = {
    "Version": "2010-09-09",
    "Mapping": {
        "AWSInstanceType2Arch": {
            u't2.large': {u'Arch': u'HVM64'},
            u't2.medium': {u'Arch': u'HVM64'},
            u't2.micro': {u'Arch': u'HVM64'},
            u't2.nano': {u'Arch': u'HVM64'},
            u't2.small': {u'Arch': u'HVM64'}
        },
        "AWSRegionArch2AMI": {
            u'ap-southeast-2': {u'HVM64': u'ami-08589eca6dcc9b39c'}
        }
    },
    "Description": """\
AWS Cloudformation template generated by troposphere.
Dependecies:
1. S3 bucket with docker templates
2. IAM role for S3 access
3. Security group for My IP access only
""",
    "Metadata": {
        "AWS::CloudFormation::Interface": {
            "ParameterGroups": [{
                "Label": {"default": "EC2 Configuration"},
                "Parameters": ["SSHLocation", "VpcId", "InstanceType"]
            },
            {
                "Label": {"default": "Connection Configuration"},
                "Parameters": ["KeyName", "RoleName"]
            }]
        }
    },
    "AnsibleMetadata": {
                "Label": {"default": "Ansible Configuration"},
                "Parameters": ["AnsiblePackage", "TrueCallPackage", "GsrPackage", "ConfigAnsibleOutputConf", "ConfigAnsiblePkg", "TruecallSiteBackup"]
    },            

    "Parameter": {
      "KeyName": {
        "Description": "Name of an existing EC2 KeyPair to enable SSH access to the instances",
        "Type": "AWS::EC2::KeyPair::KeyName",
        "Default": "MyEC2KeyPair",
        "ConstraintDescription": "must be the name of an existing EC2 KeyPair."
      },
      "RoleName": {
        "Description": "Name of IAM Role for EC2 instances",
        "Type": "String",
        "Default": "S3-Admin-Access",
        "ConstraintDescription": "must be the name of an existing IAM Role."
      },
      "VpcId": {
        "Type": "AWS::EC2::VPC::Id",
        "Default": "vpc-0fa16d5fa89c52bd9",
        "Description": "VpcId of your existing Virtual Private Cloud (VPC)"
      },
      "InstanceType": {
        "Description": "EC2 instance type",
        "Type": "String",
        "Default": "t2.micro",
        "AllowedValues": ["t1.micro", "t2.nano", "t2.micro", "t2.small", "t2.medium", "t2.large", "m1.small", "m1.medium", "m1.large", "m1.xlarge", "m2.xlarge", "m2.2xlarge", "m2.4xlarge", "m3.medium", "m3.large", "m3.xlarge", "m3.2xlarge", "m4.large", "m4.xlarge", "m4.2xlarge", "m4.4xlarge", "m4.10xlarge", "c1.medium", "c1.xlarge", "c3.large", "c3.xlarge", "c3.2xlarge", "c3.4xlarge", "c3.8xlarge", "c4.large", "c4.xlarge", "c4.2xlarge", "c4.4xlarge", "c4.8xlarge", "g2.2xlarge", "g2.8xlarge", "r3.large", "r3.xlarge", "r3.2xlarge", "r3.4xlarge", "r3.8xlarge", "i2.xlarge", "i2.2xlarge", "i2.4xlarge", "i2.8xlarge", "d2.xlarge", "d2.2xlarge", "d2.4xlarge", "d2.8xlarge", "hi1.4xlarge", "hs1.8xlarge", "cr1.8xlarge", "cc2.8xlarge", "cg1.4xlarge"],
        "ConstraintDescription": "must be a valid EC2 instance type."
      },
      "SSHLocation": {
        "Description": "The IP address range that can be used to SSH to the EC2 instances",
        "Type": "String",
        "MinLength": "9",
        "MaxLength": "18",
        "AllowedPattern": "(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})/(\\d{1,2})",
        "ConstraintDescription": "must be a valid IP CIDR range of the form x.x.x.x/x."
      }
    }, 

    "AnsibleParameter": {
      "AnsiblePackage": {
        "Description": "ansible package name in s3://ansible-test-kaiyuan bucket",
        "Type": "String",
        "Default": "ansible_truecall_v17.3_02Nov18.tar.gz",
        "ConstraintDescription": "Available ansible package"
      },
      "TrueCallPackage": {
        "Description": "TrueCall package name in s3://ansible-test-kaiyuan bucket",
        "Type": "String",
        "Default": "TrueCall-Server-17.3.0.16-0-gaa28f3b-el7-x86_64.rpm",
        "ConstraintDescription": "Available TrueCall package,"
      },
      "GsrPackage": {
        "Description": "Gsr package name in s3://ansible-test-kaiyuan bucket",
        "Type": "String",
        "Default": "GSRservices-V7.17.3.0.3_PR_CP23-0_el7.x86_64.rpm",
        "ConstraintDescription": "Available Gsr package file."
      },
      "ConfigAnsibleOutputConf": {
        "Description": "Ansible Configuration files in s3://ansible-test-kaiyuan bucket. Generated by config_ansible.py. Available options are 1 server config_ansible_output_one_server.zip, and 3 servers config_ansible_output_aws.zip",
        "Type": "String",
        "Default": "config_ansible_output_aws.zip",
        "ConstraintDescription": "Available Ansible Configuration files."
      },
      "ConfigAnsiblePkg": {
        "Description": "Software package of config_ansible.py in s3://ansible-test-kaiyuan bucket",
        "Type": "String",
        "Default": "config_ansible.zip",
        "ConstraintDescription": "Available Ansible Configuration file pkg."
      },
      "TruecallSiteBackup": {
        "Description": "Site backups of TrueCall servers in s3://ansible-test-kaiyuan bucket",
        "Type": "String",
        "Default": "Truecall_backup_20181119.zip",
        "ConstraintDescription": "Available TrueCall site backup demos."
      },
      "OptScriptPkg": {
        "Description": "Operation script pkg uploaded to s3://ansible-test-kaiyuan bucket. From /opt in cf_ansible_test_one_server.yml",
        "Type": "String",
        "Default": "opt_scripts.tar.gz",
        "ConstraintDescription": "Available Operation script pkg."
      }
    },

    # parameters t be provisioned 
    "SecurityGroup":  {
        "resource_name": '',
        "VpcId": "__".join(["ref_Parameter","VpcId"]),
        "GroupDescription": "Security group for Docker sls Test Servers",
        "SecurityGroupIngress": [

        {
          "IpProtocol": "tcp",
          "CidrIp": "0.0.0.0/0",
          "FromPort": "80",
          "ToPort": "80",
          "Description": "http"
        },
        {
          "IpProtocol": "tcp",
          "CidrIp": "0.0.0.0/0",
          "FromPort": "8443",
          "ToPort": "8443",
          "Description": "https"
        }
        ]

    },

    "SecurityGroupIngress" : {
        'resource_name': '',
        "GroupId": "__".join(["ref_SecurityGroup","resource_name"]),
        "IpProtocol": "tcp",
        "FromPort": "0",
        "ToPort": "65535", 
        "SourceSecurityGroupId": "__".join(["ref_SecurityGroup","resource_name"])
    },
    "Instance" : {
        'resource_name': '',
        "InstanceType": "__".join(["ref_Parameter","InstanceType"]),
        "IamInstanceProfile": "__".join(["ref_Parameter","RoleName"]),
        "SecurityGroupIds": ["__".join(["ref_SecurityGroup","resource_name"])],
        "KeyName": "__".join(["ref_Parameter","KeyName"]),
        # type: control, slave
        "Tags": [{
          "Key": "Type",
          "Value": "Slave"
      }]

    }
}


META_CONFIG = {
    "buckets": ["lambda-code-kaiyuan", "ansible-test-kaiyuan"],
    "creation_policy": CreationPolicy(ResourceSignal=ResourceSignal(Timeout='PT15M')),
    "sources": {
        "serverless": {'root': '/'.join([ "https://lambda-code-kaiyuan.s3.amazonaws.com", "python-s3-thumbnail.zip" ])},
        "ansible": {k:'/'.join(["https://ansible-test-kaiyuan.s3.amazonaws.com",v]) for k,v in 
            {
            "/opt":  DEFAULT_CONFIG["AnsibleParameter"]["AnsiblePackage"]["Default"], 
            "/opt/ansible": DEFAULT_CONFIG["AnsibleParameter"]["ConfigAnsibleOutputConf"]["Default"],
            "/opt/config_ansible": DEFAULT_CONFIG["AnsibleParameter"]["ConfigAnsiblePkg"]["Default"], 
            "/opt/config_ansible/Truecall_backup": DEFAULT_CONFIG["AnsibleParameter"]["TruecallSiteBackup"]["Default"],  
            "/opt/tc3/scripts": "tc_scripts.tar.gz", 
            '/opt/scripts':'opt_scripts.tar.gz'
            }.items()},

    },
    "files": {
            "/etc/cfn/cfn-hup.conf": "cfn-hup.conf", 
            "/etc/cfn/hooks.d/cfn-auto-reloader.conf": "cfn-auto-reloader.conf",
            "/etc/hosts": "hosts.txt",
            "/home/ec2-user/.ssh/config": "ssh_config.txt"            
    },
    "commands": {
        'test':{
            'test':{'command':'echo "$CFNTEST" > text.txt','env': {'CFNTEST': 'I come from config2.'},'cwd': '~'}},
        'ansible':
            {"config_ansible_connections": {
                'command': 'sed -i "s/production$/production_test/g" /opt/ansible/ansible.cfg; sed -i "s/^control/control ansible_connection=local/g" /opt/ansible/production_test;chmod 755 -R /opt/ansible; chown -R ec2-user:ec2-user /opt/ansible; /opt/scripts/download_ansible_packages.sh'}},
        'control':{'config_etc_hosts': {
              'command': 'private_ip=`curl http://169.254.169.254/latest/meta-data/local-ipv4`; sed -i "s/^control$/${private_ip} control/g" /etc/hosts'}}
    },
    "userdata": {
        "pre_config": """#!/bin/bash -xe
        # pre_config, put at first line, it will break the userdata
yum update -y
yum install git python-pip tree -y
""",
        "cfn_init": """
# cfn_init
yum update -y aws-cfn-bootstrap
aws s3 cp s3://ansible-test-kaiyuan/MyEC2KeyPair.pem /home/ec2-user/.ssh/
# Start cfn-init
/opt/aws/bin/cfn-init -s ${AWS::StackId} -r server_name --region ${AWS::Region} || error_exit 'Failed to run cfn-init'
# Start up the cfn-hup daemon to listen for changes to the EC2 instance metadata
/opt/aws/bin/cfn-hup || error_exit 'Failed to start cfn-hup'

""",
        "serverless": """
# serverless
curl https://raw.githubusercontent.com/creationix/nvm/v0.32.0/install.sh --output ~/nvm_install.sh
export HOME=/root
bash ~/nvm_install.sh 
. ~/.nvm/nvm.sh
nvm install node
nvm use node
node -e "console.log('Running Node.js ' + process.version)"
npm install -g serverless
aws s3 cp s3://ansible-test-kaiyuan/lambda_credentials.csv .
awk -F'\t' 'NR>1{printf "serverless config credentials --provider aws --key "$2" --secret "$3" --profile "$1}' lambda_credentials.csv
""",
        "docker": """
# docker
amazon-linux-extras install docker -y
service docker start
usermod -a -G docker ec2-user
curl -L https://github.com/docker/compose/releases/download/1.16.1/docker-compose-`uname -s`-`uname -m` -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
aws s3 cp s3://ansible-test-kaiyuan/docker-compose.yml /root/
base=https://github.com/docker/machine/releases/download/v0.16.0 &&
curl -L $base/docker-machine-$(uname -s)-$(uname -m) >/tmp/docker-machine &&
sudo install /tmp/docker-machine /usr/local/bin/docker-machine
#curl -sLf https://spacevim.org/install.sh | bash
aws s3 cp s3://lambda-code-kaiyuan/aws-lambda-20190103.zip /root/
git clone https://github.com/BretFisher/udemy-docker-mastery.git /root/udemy-docker-mastery
""",
        "ansible": """
# ansible
amazon-linux-extras install ansible2 -y
pip install numpy pandas xlrd xlsxwriter
cd /opt/ansible
git init

# truecall dependencies
yum groupinstall -y @core @debugging @development @hardware-monitoring @large-systems @performance @postgresql @security-tools @web-server @hardware-monitoring @large-systems @system-admin-tools @system-management @system-management-snmp --setopt=group_package_types=mandatory,default,optional
yum install -y chrony python-psycopg2 httpd-tools libICE libSM libicu libyaml mailcap python-markupsafe perl-Archive-Zip protobuf libunwind sysfsutils lynx base install htop iftop ncurses-compat-libs postgresql postgresql-server mod_ssl m2crypto
""",
        "rfb": """
# Install RFB dependencies
yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
yum install -y armadillo arpack atlas blas dbus git gzip libcap-ng libunwind lzma mcelog mlpack net-snmp-libs perl sshpass tbb zlib hdf5 lapack libgfortran libgnome-keyring libicu libquadmath
wget http://mirror.centos.org/centos/7/extras/x86_64/Packages/libssh-0.7.1-3.el7.x86_64.rpm; yum localinstall -y libssh-0.7.1-3.el7.x86_64.rpm
# download RFB related pkgs
for rfb_pkg in Netscout-FlowBroker-V7.17.3.0.3-0_rhel7.x86_64.rpm Netscout-FlowBroker-V7.17.4.0.3-1_cos731611el7.x86_64.rpm{,.md5} {xhhny82708_config.zip,JKT-RFB-01_config.tgz,boost_rpms.tgz} RFB_NE_TABLE_RRC_20181207.csv; do
aws s3 cp s3://ansible-test-kaiyuan/$rfb_pkg /opt
done
#rpm -qa | grep boost | tr -s '\n' ' '| xargs rpm -e
tar xvf /opt/boost_rpms.tgz && yum -y localinstall boost*.rpm && rm -rf boost*.rpm
""",
        "cfn_signal": """
# cfn_signal
chmod 400 /home/ec2-user/.ssh/*
chown ec2-user:ec2-user /home/ec2-user/.ssh/*
# All done so signal success
/opt/aws/bin/cfn-signal -e $? --stack ${AWS::StackId} --resource server_name --region ${AWS::Region}
"""
    }         
} 





class CfnGenerator(object):
    def __init__(self, template_name, config_dir, cfn_usage, server_count, input_config=DEFAULT_CONFIG):
        self.template = Template()
        self.template_name = template_name
        self.config_dir = config_dir
        self.input_config = input_config
        self.cfn_usage = cfn_usage
        self.server_count = server_count

        self.ref_stack_id = Ref('AWS::StackId')
        self.ref_stack_region = Ref('AWS::Region')
        self.ref_stack_name = Ref('AWS::StackName')
        self.parameters = {}
        self.security_groups = {}
        self.security_group_ingress = {}
        self.instance = {}
        self.output = {}
        self.output_config = {}
        self.template_config = {
            "Parameter": self.parameters,
            "SecurityGroup": self.security_groups,
            "SecurityGroupIngress": self.security_group_ingress,
            "Instance": self.instance,
            "Output": self.output
        }
        self.add_basic_info()


    def read_user_data(self, user_data_file, resource_name):
        cfn_init_hup = re.sub("server_name", resource_name, """#!/bin/bash -xe
yum update -y aws-cfn-bootstrap
# Start cfn-init
/opt/aws/bin/cfn-init -s ${AWS::StackId} -r server_name --region ${AWS::Region} || error_exit 'Failed to run cfn-init'
# Start up the cfn-hup daemon to listen for changes to the EC2 instance metadata
/opt/aws/bin/cfn-hup || error_exit 'Failed to start cfn-hup'
""")
        cfn_signal = re.sub("server_name", resource_name, """
# All done so signal success
/opt/aws/bin/cfn-signal -e $? --stack ${AWS::StackId} --resource server_name --region ${AWS::Region}
""")

        with open(user_data_file) as fh:
            #return Base64(Sub(fh.read().replace('server_name', resource_name)))
            return Base64(Sub(cfn_init_hup+fh.read()+cfn_signal))

    def read_init_file(self, init_file, resource_name):
        with open(os.path.join(self.config_dir,init_file)) as fh:
            return Sub(re.sub("server_name", resource_name, fh.read()))        

    @log()
    def add_basic_info(self):
        if "ansible" in self.cfn_usage:
            self.input_config["Parameter"].update(self.input_config["AnsibleParameter"])
            self.input_config["Metadata"]["AWS::CloudFormation::Interface"]["ParameterGroups"].append(self.input_config["AnsibleMetadata"])


        self.template.add_version(self.input_config["Version"])
        self.template.add_description(self.input_config["Description"])
        for k,v in self.input_config["Mapping"].items():
            self.template.add_mapping(k,v)
        for k,v in self.input_config["Parameter"].items():
            try:
                self.template_config["Parameter"][k] = self.template.add_parameter(Parameter.from_dict(k,v))
            except Exception as e:
                logger.error("add_parameter {0} error. {1}".format(k, e))
        self.template.add_metadata(self.input_config['Metadata'])

    @log()
    def sub_ref_val(self):
        info = json.dumps(self.input_config)
        #logger.info("self.input_config",self.input_config)


        for conf_name, conf in self.input_config.items():
            if self.template_config.get(conf_name) is not None:
                logger.info(conf_name)
                def _get_config(matched):
                    ParamStr = matched.group("param")
                    logger.info("   "+ParamStr)
                    if conf_name == 'Parameter':
                        #logger.info(Ref(self.template_config[conf_name][ParamStr]))
                        #return '!Ref '+self.template_config[conf_name][ParamStr]
                        return Ref(self.template_config[conf_name][ParamStr])
                    else:
                        return Ref(self.input_config[conf_name][ParamStr])
                #info = re.sub('ref_'+conf_name+'_{2}(?P<param>\w+)', "Ref(self.input_config['"+conf_name+"']['\g<param>'])", info)
                info = re.sub('ref_'+conf_name+'_{2}(?P<param>\w+)', _get_config, info)
                
        self.input_config = json.loads(info)


 

    # add_resource("SecurityGroup", "TestSecurityGroup")
    # add_resource("Instance", "AnsibleControl", UserDataFile='cfn_userdata.txt', MetaData={'buckets':buckets, 'sources': sources, 'files': files, 'commands': commands}})
    @log()
    def add_resource(self, resource_type, resource_name, **resource_data):
        #self.sub_ref_val()

        content = {k:v for k,v in self.input_config[resource_type].items() if k not in ['resource_name', 'CreationPolicy', 'Metadata']}

        if resource_type.startswith("SecurityGroup"):
            if resource_type == "SecurityGroup":
                content["VpcId"] = Ref(self.template_config["Parameter"]["VpcId"])
                content["SecurityGroupIngress"].append({
                      "IpProtocol": "tcp",
                      "CidrIp": Ref(self.template_config["Parameter"]["SSHLocation"]),
                      "FromPort": "22",
                      "ToPort": "22",
                      "Description": "ssh"
                })
            elif resource_type == "SecurityGroupIngress":
                content["GroupId"] = Ref(self.input_config["SecurityGroup"]["resource_name"])
                content["SourceSecurityGroupId"] = Ref(self.input_config["SecurityGroup"]["resource_name"])
            self.template_config[resource_type][resource_name] = eval(resource_type).from_dict(resource_name,content)
            self.template.add_resource(self.template_config[resource_type][resource_name])
            self.input_config[resource_type]["resource_name"] = resource_name

        elif resource_type == 'Instance':
            content["InstanceType"] = Ref(self.template_config['Parameter']['InstanceType'])
            content["IamInstanceProfile"] = Ref(self.template_config['Parameter']['RoleName'])
            content["KeyName"] = Ref(self.template_config['Parameter']['KeyName'])
            content["SecurityGroupIds"] = [Ref(self.input_config["SecurityGroup"]["resource_name"])]
            if "Control" in resource_name:
                content["Tags"] = [{ "Key": "Type", "Value": "Control"}]

            logger.info(resource_name, content)
            ec2_instance = eval(resource_type).from_dict(resource_name, content)
            ec2_instance.ImageId = FindInMap('AWSRegionArch2AMI', Ref('AWS::Region'), FindInMap('AWSInstanceType2Arch',
          Ref(self.template_config['Parameter']['InstanceType']), 'Arch')) 

            if "Control" in resource_name and int(self.server_count) > 1:
                ec2_instance.DependsOn = [re.sub('Control','Slave',resource_name)+str(i) for i in range(1,int(self.server_count))]


            if resource_data.get('Metadata') is not None:
                logger.info(resource_data['Metadata'])
                ec2_instance.Metadata = self.compile_meta_data(resource_data['Metadata'], resource_name)
            if resource_data.get('CreationPolicy') is not None:
                ec2_instance.CreationPolicy = resource_data['CreationPolicy']

            if resource_data.get('UserData') is not None:
                ec2_instance.UserData = Base64(Sub(re.sub("server_name", resource_name, resource_data['UserData'])))
            elif content.get('UserData') is not None:
                ec2_instance.UserData = Base64(Sub(content['UserData']))


            self.template_config[resource_type][resource_name] = self.template.add_resource(ec2_instance)

    @log()
    def compile_meta_data(self, metadata, resource_name):
        Metadata_InitFiles_input = {}
        metadata_init_files_dict = {}
        init_config = {}

        # files: {"/etc/cfn/cfn-hup.conf": "cfn-hup.conf"}
        if metadata.get('files'):
            logger.info(metadata.get('files'))
            index = 1
            for k, v in metadata.get('files').items():
                Metadata_InitFiles_input[k] = InitFile.from_dict("file"+str(index), {
                    "content": self.read_init_file(v, resource_name),
                    'mode': '000755',
                    'owner': 'root',
                    'group': 'root'
                })
                index +=1
            init_config["files"] = InitFiles(Metadata_InitFiles_input)

        # sources: {'root': Join('/', [ "https://lambda-code-kaiyuan.s3.amazonaws.com", "python-s3-thumbnail.zip" ])}
        if metadata.get('sources'):
            init_config["sources"] = metadata.get('sources')

        # commands: {'test':{'command':'echo "$CFNTEST" > text.txt','env': {'CFNTEST': 'I come from config2.'},'cwd': '~'}}
        if metadata.get('commands'):
            init_config["commands"] = metadata.get('commands')


        if metadata.get('buckets'):
            metadata_auth = {
                "type": "S3",
                "roleName": Ref("RoleName"),
                "buckets": metadata.get('buckets')
            }
            if init_config:
                return Metadata(
                    Authentication({'S3AccessCreds':AuthenticationBlock.from_dict('MetadataAuth',metadata_auth)}),
                    Init({'config': InitConfig.from_dict("initconf",init_config)})
                )
            else:
                return Metadata(
                    Authentication({'S3AccessCreds':AuthenticationBlock.from_dict('MetadataAuth',metadata_auth)})
                )
        elif init_config:
            return Metadata(
                Init({'config': InitConfig.from_dict("initconf",init_config)})
            )

    @log()
    def add_output(self):
        server_names = self.template_config["Instance"].keys()
        if len(server_names) == 1:
            server_name = list(server_names)[0]
            self.output_config["ControlPublicIp"] = {
                "Description": "Public IP address of the control server",
                "Value": GetAtt(self.template_config["Instance"][server_name], "PublicIp")
            }

        else:
            for server_name in self.template_config["Instance"].keys():
                if "Control" in server_name:
                    self.output_config["ControlPublicIp"] = {
                        "Description": "Public IP address of the control server",
                        "Value": GetAtt(self.template_config["Instance"][server_name], "PublicIp")
                    }

                else:
                    self.output_config[server_name+"PublicIp"] = {
                        "Description": "Public IP address of the control server",
                        "Value": GetAtt(self.template_config["Instance"][server_name], "PublicIp")
                    }

        for k,v in self.output_config.items():
            self.output = self.template.add_output(Output.from_dict(k,v))

    def gen_cfn_template(self, cfn_dir):
        print(self.template.to_yaml())
        with open(os.path.join(cfn_dir,self.template_name), 'w') as f:
            f.write(self.template.to_yaml())

@log()
def gen_meta_config(cfn_usage):
    meta_config = {}
    for mk in ["buckets", "creation_policy", "files"]:
        meta_config[mk] = META_CONFIG[mk]
    meta_config["sources"] = {}
    meta_config["commands"] = META_CONFIG["commands"]["control"]
    control_userdata = ""
    meta_config["slave_userdata"] = META_CONFIG["userdata"]["pre_config"]
    for usage in cfn_usage:
        control_userdata +=  META_CONFIG["userdata"].get(usage)
        for init_item in ["sources", "commands"]:
            try:
                meta_config[init_item].update(META_CONFIG[init_item].get(usage))
            except TypeError as e:
                logger.info("No {0} for {1}".format(init_item, usage))
    default_control_userdata = [META_CONFIG["userdata"][x] for x in ["pre_config", "cfn_init", "cfn_signal"]]
    meta_config["control_userdata"] = "\n".join(default_control_userdata[:-1]+[control_userdata]+default_control_userdata[-1:])
    return meta_config

@log()
def gen_server_info(count, dir, **meta_config):

    server_info = {}
    ctl_metadata = {k:v for k,v in meta_config.items() if not re.search("^creation|userdata$", k)}
    slv_metadata = {'buckets':meta_config['buckets']}
    creation_policy = meta_config['creation_policy']
    slave_userdata = meta_config["slave_userdata"]
    control_userdata = meta_config["control_userdata"]

    server_info[server_name_pre+"Control"] = {
        "Metadata": ctl_metadata,
        "CreationPolicy": creation_policy
    }
    if control_userdata:
        server_info[server_name_pre+"Control"]["UserData"] = control_userdata

    if int(count) > 1:
        for i in range(1,int(count)):
            server_info[server_name_pre+"Slave"+str(i)] = {
                "Metadata": slv_metadata
            }
            if slave_userdata:
                server_info[server_name_pre+"Slave"+str(i)]["UserData"] = slave_userdata
    with open(os.path.join(dir,"hosts.txt"),'w') as fh:
        fh.write("""127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4 control
::1         localhost6 localhost6.localdomain6\n""")
        for key in server_info.keys():
            if re.search("[Cc]ontrol", key):
                fh.write("{0}\n".format(key))
            else:
                fh.write("${{{0}.PrivateIp}} {1}\n".format(key, "slave"+re.findall('\d+',key)[-1]))
    with open(os.path.join(dir,"ssh_config.txt"),'w') as fh:

        for key in server_info.keys():
            if re.search("[Cc]ontrol", key):
                fh.write("Host {}\nIdentityFile ~/.ssh/MyEC2KeyPair.pem\n".format(key))
            else:
                fh.write("Host {}\nIdentityFile ~/.ssh/MyEC2KeyPair.pem\n".format("slave"+re.findall('\d+',key)[-1]))
    return server_info

if __name__ == '__main__':

    parser = ArgumentParser(description="Generate cloudformation template")
    parser.add_argument('-c', '--count', dest='server_count',          
        help='Number of servers. 1 control and additional slave servers.',
        default='2', action='store')
    parser.add_argument('-t', '--template-name', dest='template_name',          
        help='Name of template to generate.',
        default='TestTest.yaml', action='store')
    parser.add_argument('--cfn-dir', dest='cfn_dir',          
        help='Cloudformation dir. Default: cfn_template.',
        default='cfn_template', action='store')
    parser.add_argument('--config-dir', dest='config_dir',          
        help='Cloudformation dir. Default: cfn_config. ',
        default='cfn_config', action='store')
    parser.add_argument('-u', '--usage', dest='cfn_usage', type=str, nargs='+',
        help='Cloudformation usage. Options: ansible (truecall), serverless, docker, rfb',
        default=['ansible'])



    args = parser.parse_args() 

    logger.info("""script start. \n{0}""".format(args))    

    
    server_name_pre = "".join(map(lambda x: x.capitalize(), re.split(r'_|\.',args.template_name)[:-1]))


    meta_config = gen_meta_config(args.cfn_usage)
    server_info = gen_server_info(args.server_count, args.config_dir, **meta_config)
    logger.info(server_info)



    cfn_generator = CfnGenerator(args.template_name, args.config_dir, args.cfn_usage, args.server_count)
    cfn_generator.add_resource("SecurityGroup", "TestSecurityGroup")
    cfn_generator.add_resource("SecurityGroupIngress", "TestSecurityGroupIngress")


    for server, v in server_info.items():
        cfn_generator.add_resource("Instance", server, **v)

    cfn_generator.add_output()
    cfn_generator.gen_cfn_template(args.cfn_dir)
