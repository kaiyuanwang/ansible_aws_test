# ansible_aws_test
Build one control server and multiple slave servers in AWS for ansible test.

1. Manually build EC2 control and slave servers with bootstraps and scripts after init:
	
		control_bootstrap.txt
		slave_bootstrap.txt
		config_control.sh

2. Use AWS cloudformation to build 1 control and 2 slaves for ansible test. Can extend to more servers.
	ansible_test_aws.yaml
	
	Dependecies:
		
		1. S3 bucket with pem file, packages, applications
		2. IAM role for S3 access
		3. Security group for My IP access only
		4. Building of control server depends on successful built of slave servers
		
	Functions:
	
		1. build 1 control server and 2 slave servers with all application dependency packages 
		2. On control, install ansible, git, copy applicaiton packages from private s3 bucket
		3. Use pem file from private s3 bucket for passwordless connections between all servers. change to rsa pair for enhanced security later.
		4. Update contorl /etc/hosts with slave IPs
		5. Need to update security group to allow laptop ip access
		6. Use AWS cfn-init for cloudformation metadata control
		7. Control server building depends on slave servers. Automatically roll back if control built fails.
		8. Output server public IPs in cloudformation Output

3. Use boto3 to manage AWS cloudformation stacks.
	cfn_launch.py
	
	Dependencies:
	
		pip install requests
		pip install boto3
		    IAM -> USERS -> Add user
		    aws configure -> access key + secret key
		    C:\Users\kwang1\.aws\credentials
		        [default]
		        aws_access_key_id = YOUR_ACCESS_KEY
		        aws_secret_access_key = YOUR_SECRET_KEY
		pip install awscli
		pip install yaml
		pip install json
	
	Functions:
	
		1. Create, describe and delete AWS CloudFormation Stackes using boto3.
		2. Provide local IP address to enable EC2 access to local laptop only. 
		3. When creating stacks, if not provided, stack name will be appended with current timestamp.
		4. Describe stack will generate Xshell access config file for stacks in "CREATE_COMPLETE" status.
		5. Describe stack will show stack information until "DELETE_COMPLETE".
		6. Delete stack will delete Xshell access config file of the stack.
		7. Serialize stack info data to cfn-StackInfo.json.
		8. Serialize stack parameters to cfn-parameters.json with local ip information.