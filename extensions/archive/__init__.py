#!/usr/bin/env python3

import sys, os, re, html
from flask import request, Response
from extensions import BaseExtension
from subprocess import Popen, PIPE

class Extension(BaseExtension):
	PATTERN = re.compile(r".*\.(zip|rar|7z|tar|tar\.gz|tgz|tar\.bz2|tbz2|tar\.xz|txz)$", re.IGNORECASE)
	PRIORITY = 100

	def __init__(self, *args, **kwargs):
		BaseExtension.__init__(self, *args, **kwargs)

	def preview(self):
		response = Response()

		try:
			pipe = Popen(("7z", "l", request.path), stdout = PIPE)
			text, _ = pipe.communicate()

			if pipe.returncode != 0:
				text = self.ERROR_NO_PREVIEW

			else:
				text = "<pre>%s</pre>" % html.escape(text.decode("UTF-8"))

		except:
			text = self.ERROR_NO_PREVIEW

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
		""" % text

		return response
