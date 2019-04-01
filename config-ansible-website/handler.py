import json
import boto3
#import requests
import os, datetime, shutil
from config_ansible import SvrInfoParser, SiteBackupParser, AnsibleTemplateParser, AnsibleHostParser
import io
from log_cfg import logger
import re

#s3 = boto3.client('s3',aws_access_key_id='AKIAIFIFTEDH367NAK3Q',aws_secret_access_key='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')
s3 = boto3.client('s3')

def requestUploadURL(event, context):
    logger.info(event)
    params = json.loads(event['body'])
    #data = params['data_a']

    s3_params = {
        'Bucket': 'serverless-website1-kaiyuan',
        'Key':  datetime.datetime.now().strftime("%Y%m%d%H%M%S")+'_'+params['name'],
        #'Key': params['name'],
        'ContentType': params['type'],
        'ACL': 'public-read'
    }
    logger.info(s3_params)
    uploadURL = s3.generate_presigned_url('put_object', ExpiresIn=60, Params=s3_params)
    logger.info(uploadURL)
    #files = StringIO("asdfsdfsdf")
    #s3_response = s3.put_object(*s3_params, Body=data)
    #s3_response = requests.put(uploadURL, data=data)
    #logger.info(s3_response)
    body = {
        "uploadURL": uploadURL,
        "uploadFile": s3_params["Key"],
        "ansibleConfigFile": re.sub('.xls[x]?$', '.zip', s3_params["Key"])
    }
    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    response = {
        "statusCode": 200,
        "headers": headers,
        "body": json.dumps(body)
    }
    logger.info(body)
    return response

def s3_ansible_config_generator(event, context):
    logger.info(event)
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    data_bucket="lambda-data-kaiyuan"
    data_dir = sip_ahp_process(bucket, key, data_bucket)
    zip_upload_config_files(bucket, data_bucket, data_dir, '/tmp/config_output')


def sip_ahp_process(bucket, key, data_bucket):
    sip_input = [key, "config_input/default.yml","config_input"]
    sip = SvrInfoParser("info", *sip_input, use_s3=True, bucket=bucket, data_bucket=data_bucket)
    truecall_server_info = sip.tc_svr_info_df
    logger.debug(truecall_server_info)
    # store to datetime.datetime.now().strftime("%Y%m%d%H%M%S")_truecall_server_info_aws_3servers dir
    #output_dir = "config_output/"+"_".join([key.strip('.xlsx'), datetime.datetime.now().strftime("%Y%m%d%H%M%S")])
    output_dir = "config_output/"+re.sub('.xls[x]?$', '', key)
    dest_dirs = list(map(lambda x:output_dir+x, ['', '/group_vars', '/host_vars']))
    logger.info(dest_dirs)
    sip_output = sip.pd_gen_var_files(*dest_dirs)
    logger.info(sip_output)

    ahp_input = ["info", "config_input/production_template", 0, output_dir]
    ahp_input.append(sip_output)
    ahp = AnsibleHostParser(*ahp_input, use_s3=True, bucket=bucket, data_bucket="lambda-data-kaiyuan")
    ahp.process_ansible_hosts()
    return output_dir

def zip_upload_config_files(bucket, data_bucket, data_dir, local_dir):
    config_output_files = [x['Key'] for x in s3.list_objects(Bucket=data_bucket)['Contents'] if x['Key'].startswith(data_dir)]
    for cof in config_output_files:
        local_file = os.path.join(local_dir,*cof.split('/')[2:])
        logger.info(local_file)
        mkdir(os.path.dirname(local_file))
        s3.download_file(data_bucket,cof, local_file)
    zip_file = config_output_files[0].split('/')[1]
    logger.info(zip_file)
    shutil.make_archive(os.path.join(local_dir, zip_file), 'zip', local_dir)
    s3.upload_file(os.path.join(local_dir, zip_file+'.zip'), bucket, zip_file+'.zip')
    shutil.rmtree(local_dir)

def mkdir(path):
    if path and not os.path.exists(path):
        os.makedirs(path)
