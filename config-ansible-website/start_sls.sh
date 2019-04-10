#!/bin/bash

output=`sls deploy`
echo $output 
url=`echo $output | tr -s ' ' '\n' | grep https | awk -F/ '{print $3}'`
echo $url
sed -i "s%https://\([a-zA-Z0-9.]*\)execute-api.ap-southeast-2.amazonaws.com%https://${url}%g" client/dist/index.html
sls client deploy << EOF
y
EOF
