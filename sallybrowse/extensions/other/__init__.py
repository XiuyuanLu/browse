#!/usr/bin/env python3

import sys, os, re, html
from flask import request, abort, Response
from pygments import highlight
from pygments.lexers import guess_lexer_for_filename
from pygments.formatters import HtmlFormatter
import chardet
from textblob import TextBlob
from sallybrowse.extensions import BaseExtension

class Extension(BaseExtension):
	PATTERN = re.compile(r".*")
	PRIORITY = 1

	def __init__(self, *args, **kwargs):
		BaseExtension.__init__(self, *args, **kwargs)

	def preview(self):
		response = Response()
		format = True

		if "/s3buckets/" in request.path:
			text = self.ERROR_NO_PREVIEW
			format = False
		else:
			if os.path.getsize(request.path) > 50000000: # 50MB
				text = self.ERROR_NO_PREVIEW
				format = False

			else:
				text = open(request.path, "rb").read()

		try:
			text = text.decode("UTF-8")

		except:
			try:
				codec = chardet.detect(text)["encoding"]
				text = text.decode(text, codec)

			except:
				text = self.ERROR_NO_PREVIEW
				format = False

		if not format or request.path.lower().endswith(".html"):
			style = ""

		else:
			try:
				lexer = guess_lexer_for_filename(request.path, text)

			except:
				lexer = None

			if lexer == None:
				text = "<pre>%s</pre>" % html.escape(text) 
				style = ""

			else:
				text = highlight(text, lexer, HtmlFormatter())
				style = HtmlFormatter().get_style_defs(".highlight")

		response.data = """
			<html>
				<head>
					<style>
						* {
							font-size: 1.1em;
							background: white;
						}
						%s
					</style>
				</head>
				<body>
					%s
				</body>
			</html>
		""" % (style, text)

		return response

	def info(self, data):
		text = ""

		try:
			text = open(request.path, "rb").read()
			codec = chardet.detect(text)["encoding"]
			text = text.decode(codec)

		except:
			return BaseExtension.info(self, data)

		data.append(("Likely encoding", codec))
		data.append(("Lines", len(text.splitlines())))
		data.append(("Words", len(text.split())))
		data.append(("Characters", len(text)))
		data.append(("Characters (excluding whitespace)", len(re.sub(r"\s", "", text))))

		try:
			data.append(("Likely language", TextBlob(text).detect_language()))

		except:
			return BaseExtension.info(self, data)

		return BaseExtension.info(self, data)
