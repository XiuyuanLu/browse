#!/usr/bin/env python3

import sys, os, re, html, csv
import chardet
from flask import request, Response
from extensions import BaseExtension
from extensions.other import Extension as OtherExtension
from subprocess import Popen, PIPE

class Extension(BaseExtension):
	PATTERN = re.compile(r".*\.(csv|tsv)$", re.IGNORECASE)
	PRIORITY = 100

	def __init__(self, *args, **kwargs):
		BaseExtension.__init__(self, *args, **kwargs)

	def preview(self):
		response = Response()
		rawText = open(request.path, "rb").read()

		try:
			rawText = rawText.decode("UTF-8")

		except:
			try:
				codec = chardet.detect(rawText)["encoding"]
				rawText = rawText.decode(codec)

			except:
				return OtherExtension().preview()

		dialect = csv.Sniffer().sniff(rawText[: 4096])
		reader = csv.reader(rawText.splitlines(keepends = True), dialect = dialect)

		text = """
			<html>
				<head>
					<style>
						* {
							font-size: 1.1em;
							background: white;
						}

						td {
							padding: 0 10px;
						}
					</style>
				</head>
				<body>
					<table border="1">
		"""

		for row in reader:
			text += """
						<tr>
			"""

			for cell in row:
				text += """
							<td>%s</td>
				""" % (html.escape(cell))

			text += """
						</tr>
			"""

		text += """
					</table>
				</body>
			</html>
		"""

		response.data = text

		return response
