#!/usr/bin/env python3

import sys, os, re
import boto3, botocore
from flask import request, Response
from s3path import S3Path, PureS3Path
from sallybrowse.extensions import BaseExtension

class Extension(BaseExtension):
	PATTERN = re.compile(r".*\.(jpg|jpeg|png|gif|webp)$", re.IGNORECASE)
	PRIORITY = 100

	def __init__(self, *args, **kwargs):
		BaseExtension.__init__(self, *args, **kwargs)

	def preview(self):
		print ("hi?", request.path)
		path = ""
		response = Response()
		if "/s3buckets/" not in request.path:
			path = request.path
		else:
			s3_client = boto3.client('s3')
			p = PureS3Path(request.path.replace("/s3buckets", ""))
			# print (p)
			# print ("lol", p.bucket, p.key)
			bucketname = str(p.bucket).replace("/", '')
			itemkey = str(p.key)
			path = s3_client.generate_presigned_url('get_object', Params = {'Bucket': bucketname, 'Key': itemkey}, ExpiresIn = 100)
			
		# print (path)
		response.data = """
			<html>
				<head>
					<style>
						* {
							border: 0px;
							margin: 0px;
							padding: 0px;
						}

						body {
							background: black;
						}

						img {
							max-width: 100%%;
							max-height: 100%%;
							margin: auto;
							display: block;
							position: absolute;
							top: 50%%;
							bottom: 50%%;
						}
					</style>
				</head>
				<body>
					<img src="%s?dl">
				</body>
			</html>
		""" % request.path 

		return response
