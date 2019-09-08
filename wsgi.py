#!/usr/bin/env python3

import sys, os

appPath = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(0, appPath)

def application(environ, start_response):
	from sallybrowse import app as _app

	return _app(environ, start_response)
