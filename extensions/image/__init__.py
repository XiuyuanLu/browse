#!/usr/bin/env python3

import sys, os, re
from flask import request, Response
from extensions import BaseExtension

class Extension(BaseExtension):
	PATTERN = re.compile(r".*\.(jpg|jpeg|png|gif|webp)$", re.IGNORECASE)
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
