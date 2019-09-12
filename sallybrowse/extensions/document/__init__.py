#!/usr/bin/env python3

import sys, os, re, html
from flask import request, Response
from sallybrowse.extensions import BaseExtension
from subprocess import Popen, PIPE

class Extension(BaseExtension):
	PATTERN = re.compile(r".*\.(pdf|xlsx|xls|docx|doc|ods|odt|xlt|ppt|pptx|odp|otp|ltx)$", re.IGNORECASE)
	PRIORITY = 100

	def __init__(self, *args, **kwargs):
		BaseExtension.__init__(self, *args, **kwargs)

	def preview(self):
		response = Response()
		error = False

		if request.path.lower().endswith(".pdf"):
			try:
				data = open(request.path, "rb").read()

			except:
				error = True

		else:
			try:
				pipe = Popen(("unoconv", "--stdout", "-f", "pdf", request.path), stdout = PIPE)
				data, _ = pipe.communicate()

				if pipe.returncode != 0:
					error = True

			except:
				error = True

		if error:
			response.data = """
				<html>
					<head>
						<style>
							* {
								font-size: 1.1em;
							}

							body {
								background: white;
							}
						</style>
					</head>
					<body>
						%s
					</body>
				</html>
			""" % self.ERROR_NO_PREVIEW

		else:
			response.data = data
			response.mimetype = "application/pdf"

		return response
