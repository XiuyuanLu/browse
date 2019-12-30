#!/usr/bin/env python3

import os, sys, re
from flask import request, Response

class BaseExtension(object):
	ERROR_NO_PREVIEW = "<h1>No Preview Available</h1>Please download the file instead."	

	AJAX_DIR_SIZE = """<i class="fa fa-spinner fa-spin"></i>"""
	AJAX_DIR_BYTES = """<i class="fa fa-spinner fa-spin"></i>"""
	AJAX_DIR_NUM_FILES = """<i class="fa fa-spinner fa-spin"></i>"""
	AJAX_DIR_NUM_DIRS = """<i class="fa fa-spinner fa-spin"></i>"""
	AJAX_DIR_NUM_LINKS = """<i class="fa fa-spinner fa-spin"></i>"""

	def info(self, data):
		response = Response()
		text = """
			<html>
				<head>
					<style>
						* {
							font-size: 1.1em;
							background: white;
						}
						%s
					</style>
		"""
		if os.path.isdir(request.path):
			text += """
					<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
					<script src="https://ajax.googleapis.com/ajax/libs/jquery/3.4.1/jquery.min.js"></script>
					<script>
						$(function () {
							$.getJSON(encodeURI("%s?extradirinfo"), function (data, status, xhr) {
								$("body>b").each(function() {
									var key = $(this).text().slice(0, -1)

									if (key in data) {
										$(this).next().html(data[key])
									}
								})
							})
						})
					</script>
			""" % request.path
		
		text += """
				</head>
				<body>
		"""
		
		for key, value in data:
			text += """
					<b>%s:</b> <span>%s</span><br/>
			""" % (key, value)

		text += """
				</body>
			</html>
		"""

		response.data = text

		return response
