#!/usr/bin/env python3

import sys, os, re
from flask import request, Response
from extensions import BaseExtension

class Extension(BaseExtension):
	PATTERN = re.compile(r".*\.(mp4|mkv|avi|mov|wmv|webm|vob|mpeg|ts|mpeg2|mpg)$", re.IGNORECASE)
	PRIORITY = 100

	def __init__(self, *args, **kwargs):
		BaseExtension.__init__(self, *args, **kwargs)

	def preview(self):
		response = Response()

		response.data = """
			<html>
				<head>
					<style>
						* {
							border: 0px;
							margin: 0px;
							padding: 0px;
						}
					</style>
				</head>
				<body>
					<video width="100%%" controls autoplay>
						<source src="%s?dl">
						Your browser does not support HTML5 video.
					</video>
				</body>
			</html>
		""" % request.path

		return response
