#!/usr/bin/python
# -*- coding:utf8 -*-

"""
Name: cfn_generate.py

History:
---------
03/14/2019 Kaiyuan Wang 0.1
    Functions using troposphere for cloudformation creations.
# TODO: to be objectified
"""



"""
troposphere examples 
https://github.com/cloudtools/troposphere/blob/master/examples/EC2InstanceSample.py
https://github.com/cloudtools/troposphere/blob/master/examples/Autoscaling.py
https://github.com/cloudtools/troposphere/blob/master/examples/VPC_single_instance_in_subnet.py
https://github.com/kaiyuanwang/troposphere/blob/master/examples/CloudFormation_Init_ConfigSet.py
https://github.com/cloudtools/troposphere/blob/master/troposphere/cloudformation.py
"""

from troposphere import Base64, Select, FindInMap, GetAtt, GetAZs, Join, Output, If, And, Not, Or, Equals, Condition
from troposphere import Parameter, Ref, Tags, Template
from troposphere.cloudformation import Init, InitFile, InitFiles, Metadata, InitConfig, Authentication, AuthenticationBlock
from troposphere.cloudfront import Distribution, DistributionConfig
from troposphere.cloudfront import Origin, DefaultCacheBehavior
from troposphere.ec2 import PortRange
from troposphere.ec2 import SecurityGroupIngress
from troposphere.ec2 import SecurityGroup
from troposphere.ec2 import Instance, NetworkInterfaceProperty, PrivateIpAddressSpecification
from troposphere.policies import CreationPolicy, ResourceSignal



t_version = "2010-09-09"
t_description = """\
AWS Cloudformation template for Docker and serverless framework testing
Dependecies:
  1. S3 bucket with docker templates
  2. IAM role for S3 access
  3. Security group for My IP access only
"""
t_mappings = {
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
}

t_parameters = {
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
}


template = Template()

# supporting info: version, description, parameters, mapping
template.add_version(t_version)
template.add_description(t_description)

for k,v in t_mappings.items():
    template.add_mapping(k,v)

param_dict = {}
for k,v in t_parameters.items():
    try:
        param_dict[k] = template.add_parameter(Parameter.from_dict(k,v))
    except:
        pass

ref_stack_id = Ref('AWS::StackId')
ref_stack_region = Ref('AWS::Region')
ref_stack_name = Ref('AWS::StackName')


# resource SecurityGroup and SecurityGroupIngress
t_res_sec_grp = {
    "DockerSlsSecurityGroup": {
        "VpcId": Ref(param_dict["VpcId"]),
        "GroupDescription": "Security group for Docker sls Test Servers",
        "SecurityGroupIngress": [
        {
          "IpProtocol": "tcp",
          "CidrIp": Ref(param_dict["SSHLocation"]),
          "FromPort": "22",
          "ToPort": "22",
          "Description": "ssh"
        },
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
    }
}

res_sec_grp_dict = {}
for k, v in t_res_sec_grp.items():
    res_sec_grp_dict[k] = SecurityGroup.from_dict(k,v)
    template.add_resource(res_sec_grp_dict[k])

t_res_sec_grp_ingress = {
    "DockerSlsSecurityGroupIngress": {
        "GroupId": Ref(res_sec_grp_dict["DockerSlsSecurityGroup"]),
        "IpProtocol": "tcp",
        "FromPort": "0",
        "ToPort": "65535",
        "SourceSecurityGroupId": Ref(res_sec_grp_dict["DockerSlsSecurityGroup"])
    }
}
res_sec_grp_ingress_dict = {}
for k, v in t_res_sec_grp_ingress.items():
    res_sec_grp_ingress_dict[k] = SecurityGroupIngress.from_dict(k,v)
    template.add_resource(res_sec_grp_ingress_dict[k])

# instance
user_data = Base64(Join('',[
        '#!/bin/bash -xe\n',
        '\n',
        '## Get the latest CloudFormation package\n',
        'yum update -y aws-cfn-bootstrap\n',
        '# Start cfn-init\n',
        '/opt/aws/bin/cfn-init -s ', ref_stack_id, ' -r DockerSlsTestServer --region ', ref_stack_region, ' || error_exit "Failed to run cfn-init"\n',
        '# Start up the cfn-hup daemon to listen for changes to the EC2 instance metadata\n',
        '/opt/aws/bin/cfn-hup || error_exit "Failed to start cfn-hup"\n',
        '\n',
        'curl https://raw.githubusercontent.com/creationix/nvm/v0.32.0/install.sh --output ~/nvm_install.sh\n',
        'export HOME=/root\n',
        'bash ~/nvm_install.sh \n',
        '. ~/.nvm/nvm.sh\n',
        'nvm install node\n',
        'nvm use node\n',
        'node -e "console.log(\'Running Node.js \' + process.version)"\n',
        'npm install -g serverless\n',
        'aws s3 cp s3://ansible-test-kaiyuan/lambda_credentials.csv .\n',
        '`awk -F\'\t\' \'NR>1{printf "serverless config credentials --provider aws --key "$2" --secret "$3" --profile "$1}\' lambda_credentials.csv`\n',
        'yum update -y\n',
        'amazon-linux-extras install docker -y\n',
        'service docker start\n',
        'usermod -a -G docker ec2-user\n',
        'aws s3 cp s3://lambda-code-kaiyuan/aws-lambda-20190103.zip /root/\n',
        'curl -L https://github.com/docker/compose/releases/download/1.16.1/docker-compose-`uname -s`-`uname -m` -o /usr/local/bin/docker-compose\n',
        'chmod +x /usr/local/bin/docker-compose\n',
        'aws s3 cp s3://ansible-test-kaiyuan/docker-compose.yml /root/\n',
        'base=https://github.com/docker/machine/releases/download/v0.16.0 &&\n',
        'curl -L $base/docker-machine-$(uname -s)-$(uname -m) >/tmp/docker-machine &&\n',
        'sudo install /tmp/docker-machine /usr/local/bin/docker-machine\n',
        'yum install git -y\n',
        'git clone https://github.com/BretFisher/udemy-docker-mastery.git /root/udemy-docker-mastery\n',
        '#curl -sLf https://spacevim.org/install.sh | bash            \n',
        '\n',
        '# All done so signal success\n',
        '/opt/aws/bin/cfn-signal -e $? --stack ', ref_stack_id, ' --resource DockerSlsTestServer --region ', ref_stack_region]))


metadata_init_files_dict = {
    "file1": {
        "file_name": "/etc/cfn/cfn-hup.conf",
        "config": {
            "content": Join('',
                   ['[main]\n',
                    'stack=', ref_stack_id, '\n',
                    'region=', ref_stack_region, '\n',
                   ]),
            'mode': '000400',
            'owner': 'root',
            'group': 'root'
        }
    },
    "file2": {
        "file_name": "/etc/cfn/hooks.d/cfn-auto-reloader.conf",
        "config": {
            'content': Join('',
                 ['[cfn-auto-reloader-hook]\n',
                  'triggers=post.update\n',
                  'path=Resources.WebServerInstance.Metadata.AWS::CloudFormation::Init\n',
                  'action=/opt/aws/bin/cfn-init -v --stack ', ref_stack_name, ' --resource WebServerInstance ', ' --region ', ref_stack_region, '\n', 'runas=root\n',
                ]),
            'mode': '000400',
            'owner': 'root',
            'group': 'root'
        }
    }  
}

Metadata_InitFiles_input = {}
for k,v in metadata_init_files_dict.items():
    Metadata_InitFiles_input[v["file_name"]] = InitFile.from_dict(k,v["config"])

metadata_auth = {
    "type": "S3",
    "roleName": Ref("RoleName"),
    "buckets": ["lambda-code-kaiyuan", "ansible-test-kaiyuan"]
}

instance_metadata = Metadata(
    Authentication({'S3AccessCreds':AuthenticationBlock.from_dict('MetadataAuth',metadata_auth)}),
    Init({
        'config': InitConfig(
            sources={'root': Join('/', [ "https://lambda-code-kaiyuan.s3.amazonaws.com", "python-s3-thumbnail.zip" ])},
            files = InitFiles(Metadata_InitFiles_input)
            )
        })
)


ec2_instance = {
    "DockerSlsTestServer" : {
      "InstanceType": Ref(param_dict["InstanceType"]),
      "IamInstanceProfile": Ref(param_dict["RoleName"]),
      "SecurityGroupIds": [
        Ref(res_sec_grp_dict["DockerSlsSecurityGroup"])
      ],
      "KeyName": Ref(param_dict["KeyName"]),
      "ImageId": FindInMap('AWSRegionArch2AMI', Ref('AWS::Region'), FindInMap('AWSInstanceType2Arch',
          Ref(param_dict['InstanceType']), 'Arch')),
      "Tags": [{
          "Key": "Type",
          "Value": "DockerServerless"
      }],
      "CreationPolicy": CreationPolicy(ResourceSignal=ResourceSignal(Timeout='PT15M')),
      "Metadata": instance_metadata,
      "UserData": user_data      
    }
}


ec2_instance_dict = {}
for k,v in ec2_instance.items():
    # from_dict does not support Metadata or CreationPolicy. Workaround applied
    v_sel = {kv:vv for kv, vv in v.items() if kv not in ['Metadata', 'CreationPolicy']}
    ec2_instance = Instance.from_dict(k,v_sel)
    if v.get('Metadata') is not None:
        ec2_instance.Metadata = v.get('Metadata')
    if v.get('CreationPolicy') is not None:
        ec2_instance.CreationPolicy =v.get('CreationPolicy')  
    ec2_instance_dict[k] = template.add_resource(ec2_instance)


# output
t_output = {
  "ControlPublicIp": {
    "Description": "Public IP address of the control server",
    "Value": GetAtt(ec2_instance_dict["DockerSlsTestServer"], "PublicIp")
  }
}

for k,v in t_output.items():
    template.add_output(Output.from_dict(k,v))


print(template.to_yaml())
with open('test.yaml', 'w') as f:
    f.write(template.to_yaml())





