#!/bin/bash


aws s3 rm s3://serverless-website1-kaiyuan --recursive
sls remove 
sls client remove << EOF
y
EOF
