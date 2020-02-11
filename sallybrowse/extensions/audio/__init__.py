#!/usr/bin/env python3

import sys, os, re
from flask import request, Response
from sallybrowse.extensions import BaseExtension

class Extension(BaseExtension):
	PATTERN = re.compile(r".*\.(mp3|ogg|wav|wma|aac|m4a|opus|flac|alaw|a8|ulaw|mulaw|u8)$", re.IGNORECASE)
	PRIORITY = 100

	def __init__(self, *args, **kwargs):
		BaseExtension.__init__(self, *args, **kwargs)

	def preview(self):
		response = Response()
		if request.url.lower().split("?")[0].endswith((".alaw", ".a8")):
			suffix = "alaw2wavdl"

		elif request.url.lower().split("?")[0].endswith((".ulaw", ".mulaw", ".u8")):
			suffix = "ulaw2wavdl"

		else:
			suffix = "dl"

		response.data = """
			<html>
				<head>
					<script src="https://unpkg.com/wavesurfer.js"></script>
					<style>
						* {
							border: 0px;
							margin: 0px;
							padding: 0px;
						}

						body {
							background: black;
						}
					</style>
					<script>
						window.onload = function () {
							var wavesurfer = WaveSurfer.create({
								container: '#audio',
								waveColor: 'violet',
								progressColor: 'purple',
								pixelRatio: 1,
								splitChannels: true,
								backend: "MediaElement",
								mediaControls: true
							})

							wavesurfer.on("ready", function () {
								wavesurfer.play()
							})

							wavesurfer.load("%s?%s")
						}
					</script>
				</head>
				<body>
					<div id="audio"></div>
				</body>
			</html>
		""" % (request.path, suffix)

		return response
