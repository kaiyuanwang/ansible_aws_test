#!/bin/bash
# run config_control.sh every time one slave server is provisioned
# need to run dos2unix in linux
# ansible -i dev control -a "hostname"
aws s3 cp s3://ansible-test-kaiyuan/host_slave ~
# check slave number in /etc/hosts and add slave info
slave_no=`echo "\`grep slave /etc/hosts | wc -l\`+1" | bc`
echo -e `cat host_slave`"_$slave_no" >> /etc/hosts
aws s3 cp s3://ansible-test-kaiyuan/id_rsa_slave.pub ~/.ssh
cat ~/.ssh/id_rsa_slave.pub >> ~/.ssh/authorized_keys
awk '{print "Host "$1}' ~/host_slave >> ~/.ssh/config; echo -e "User root\nIdentityFile ~/.ssh/id_rsa_control" >> ~/.ssh/config
echo -e "Host slave_${slave_no}\nUser root\nIdentityFile ~/.ssh/id_rsa_control" >> ~/.ssh/config