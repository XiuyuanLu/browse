#!/usr/bin/env python3

import sys, os, re, importlib, time, datetime, logging, locale
import boto3, botocore

from urllib.parse import quote, unquote
from io import BytesIO
from pwd import getpwuid
from grp import getgrgid
from collections import namedtuple, defaultdict
from subprocess import Popen, PIPE
from zipstream import ZipFile, ZIP_DEFLATED
from humanize import naturalsize
from flask import Flask, send_file, escape, request, abort, Response, render_template, jsonify, redirect, stream_with_context, g, make_response
from magic import Magic
from sallybrowse.extensions import BaseExtension
from s3path import S3Path
from pathlib import Path
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from urllib.parse import urlparse
from functools import wraps
import json
import jwt


ARG_DOWNLOAD = "dl"
ARG_INFO = "info"
ARG_LIST = "list"
ARG_EXTRA_DIR_INFO = "extradirinfo"
ARG_DOWNLOAD_ALAW_TO_WAV = "alaw2wavdl"
ARG_DOWNLOAD_ULAW_TO_WAV = "ulaw2wavdl"
EXTENSION_DIR = os.path.join(os.path.dirname(__file__), "extensions")
COMMON_ROOT = None # Do not change
WHITELIST = []
TEMP_WHITELIST = ["appensydney-audio4-backups"]

if "SERVE_DIRECTORIES" in os.environ:
	SERVE_DIRECTORIES = os.environ["SERVE_DIRECTORIES"].split(":")
else:
	SERVE_DIRECTORIES = tuple([
	# Put the directories you wish to serve here.
	# If left empty, all directories (/) will be served.
])

app = Flask(__name__, static_url_path = "/static", template_folder = os.path.join(os.path.dirname(__file__), "templates"))

extensions = []


s3_cl = boto3.client('s3')
s3_re = boto3.resource('s3')
BUCKET_NAME = re.compile(".*\/s3buckets(?P<bucket>\/[^\/]*).*")

# for bucket in s3_re.buckets.all():
# 	s3_bucket_name = bucket.name
# 	if s3_bucket_name in TEMP_WHITELIST:
# 		WHITELIST.append("/{}".format(s3_bucket_name))
# 	else:
# 		try:
# 			response = s3_cl.get_bucket_tagging(Bucket=s3_bucket_name)
# 			for tag in response["TagSet"]:
# 				tag = dict(tag)
# 				if tag["Key"] == "SallyBrowse" and tag["Value"] == "Yes":
# 					WHITELIST.append("/{}".format(s3_bucket_name))
# 		except Exception as e:
# 			print (e)


@app.before_request
def parse_path():
	logging.error(("Request", type(request.path), repr(request.path), request.path))
	try:
		g.path = unquote(request.path).encode("utf-8").decode('unicode_escape').encode("ISO-8859-1").decode("utf-8")
	except Exception:
		logging.exception("Failed to decode request....")
		try:
			g.path = unquote(request.path)
		except Exception:
			logging.exception("Failed to decode request.... fallback...")
			g.path = request.path

	logging.error(("g.path", type(g.path), repr(g.path), g.path))


def browseS3Dir(path):
	global WHITELIST
	if path == "/s3buckets":
		p = S3Path('/')
		bucket_list = [path for path in p.iterdir() if str(path) in WHITELIST]
	else:
		p = S3Path(path.replace("/s3buckets", ""))
		bucket_list = [path for path in p.iterdir()]

	return bucket_list

def stream_template(template_name, **context):
	app.update_template_context(context)
	t = app.jinja_env.get_template(template_name)
	rv = t.stream(context)
	rv.enable_buffering(5)
	return rv

def generate_s3_rows(files):
	for s3object in files:
		try:
			entry = {
				"dir": str(s3object),
				"name": str(s3object).split("/")[-1],
				"path": "/s3buckets" + str(s3object),
				"type": "directory" if s3object.is_dir() else "file",
				"bytes": "N/A",
				"size": "N/A",
				"last_modified": "N/A",
			}

			if entry["type"] == "file":
				stats = s3object.stat()
				entry["bytes"] = stats.size
				entry["size"] = naturalsize(stats.size)
				entry["last_modified"] = stats.last_modified
			yield (entry)

		except Exception:
			logging.exception("Failed generating folder entry")
			continue

def generate_efs_rows(files):
	for file in files:
		path = get_path()
		path = path.joinpath(file)

		if not str(path).startswith(SERVE_DIRECTORIES):
			continue

		try:
			path_str = str(path)
			entry = {
				"dir": g.path,
				"path": quote(path_str),
				"name": file,
				"type": getType(path_str)
			}

			if not os.path.isdir(path_str) and (os.path.isfile(path_str) or os.path.islink(path_str)) and os.path.exists(path_str):
				entry["bytes"] = os.path.getsize(path_str)
				entry["size"] = naturalsize(entry["bytes"])
				l_modified = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
				entry["last_modified"] = l_modified
			else:
				entry["bytes"] = "N/A"
				entry["size"] = "N/A"
				entry["last_modified"] = "N/A"

			yield (entry)

		except Exception:
			logging.exception("Failed generating folder entry")
			continue

	# PATCH FOR S3 FUNCTIONALITY
	if g.path == "/":
		s3entry = {
			"dir": "/s3buckets",
			"name": "s3buckets",
			"path": "/s3buckets/",
			"type": "directory",
			"size": "N/A",
			"last_modified": "N/A",
		}
		yield (s3entry)

def browseDir():
	entries = []

	if g.path.startswith("/s3buckets"):
		if not g.path.startswith(SERVE_DIRECTORIES):
			abort(403)
		entries = generate_s3_rows(browseS3Dir(g.path))
	else:
		try:
			files = sorted(os.listdir(g.path))
		except:
			files = []

		if os.path.islink(g.path):
			if not os.readlink(g.path).startswith(SERVE_DIRECTORIES):
				abort(403)

		entries = generate_efs_rows(files)

	return Response(stream_with_context(stream_template('dir.html', entries=entries)))

def previewFile():
	for extension in extensions:
		if extension.Extension.PATTERN.match(g.path):
			return extension.Extension().preview()
	abort(404)

def listDir():
	paths = []
	curr_path = get_path()

	if str(curr_path) == "." and str(type(curr_path)) == "<class 's3path.S3Path'>":
		curr_path = S3Path("/")

	try:
		files = curr_path.glob('*')
	except:
		files = []

	for file in files:
		path = str(file)

		if str(type(file)) != "<class 's3path.S3Path'>" and not path.startswith(SERVE_DIRECTORIES):
			continue

		paths.append(path)

	return "<br/>".join(sorted(paths))



def downloadDir():
	def generateFileChunks(path):
		with path.open(mode="rb") as handle:
			while True:
				chunk = handle.read(1024)
				if len(chunk) == 0:
					return
				yield chunk

	def generateChunks(path):
		stream = ZipFile(mode = "w", compression = ZIP_DEFLATED)

		for item in path.glob('*'):
			if not item.exists() or item.is_dir():
				continue
			try:
				stream.write_iter((item.name.split('/')[-1]).lstrip("/"), generateFileChunks(item))
			except:
				continue

			for chunk in stream.next_file():
				yield chunk

		for chunk in stream:
			yield chunk

	path = get_path()
	filename = (path.name.split('/')[-1] or "root") + ".zip"

	response = Response(generateChunks(path), mimetype = "application/zip")
	response.headers["Content-Disposition"] = "attachment; filename=%s" % filename

	return response


def get_path():
	path = g.path

	if path.startswith("/s3buckets"):
		path = path.replace("/s3buckets", "")
		return S3Path(path)
	else:
		return Path(path)


def downloadFile():
	rpath = get_path()

	return send_file(rpath.open(mode="rb"), attachment_filename=rpath.name, conditional = True, as_attachment = True)

def downloadAlaw2Wav():
	pipe = Popen(("sox", "-t", ".raw", "-e", "a-law", "-c", "1", "-r", "8000", g.path, "-t", "wavpcm", "-"), stdout = PIPE)
	out, _ = pipe.communicate()

	if pipe.returncode != 0:
		abort(404)

	buffer = BytesIO(out)
	filename = os.path.basename(g.path) + ".wav"

	return send_file(buffer, conditional = True, as_attachment = True, attachment_filename = filename)

def downloadUlaw2Wav():
	pipe = Popen(("sox", "-t", ".raw", "-e", "u-law", "-c", "1", "-r", "8000", g.path, "-t", "wavpcm", "-"), stdout = PIPE)
	out, _ = pipe.communicate()

	if pipe.returncode != 0:
		abort(404)

	buffer = BytesIO(out)
	filename = os.path.basename(g.path) + ".ulaw"

	return send_file(buffer, conditional = True, as_attachment = True, attachment_filename = filename)


def getType(path):
	file = os.path.basename(path)

	if file.startswith("."):
		fileType = "hidden "

	else:
		fileType = ""

	if os.path.isdir(path) and os.path.islink(path):
		if not os.path.exists(path):
			fileType += "broken "

		fileType += "directory link"

	elif os.path.isdir(path):
		fileType += "directory"

	elif os.path.islink(path):
		if not os.path.exists(path):
			fileType += "broken "

		fileType += "link"

	elif os.path.ismount(path):
		fileType += "mount"

	elif os.path.isfile(path):
		fileType += "file"

	else:
		fileType += "other"

	return fileType

def getExtraDirInfo():
	data = {}
	size = 0
	numFiles = 0
	numDirs = 0
	numLinks = 0

	for root, dirs, files in os.walk(g.path):
		numDirs += len(dirs)

		for file in files:
			path = os.path.join(root, file)

			if os.path.isfile(path):
				size += os.path.getsize(path)
				numFiles += 1

			elif os.path.islink(path):
				numLinks += 1

	data["Bytes"] = size
	data["Size"] = naturalsize(size)
	data["Number of files"] = numFiles
	data["Number of links"] = numLinks
	data["Number of directories"] = numDirs

	return jsonify(data)

def getInfo():
	if g.path.startswith("/s3buckets"):
		bucket_path = get_path()
		bucket_name, item_path = str(bucket_path.bucket).lstrip("/"), str(bucket_path.key)
		if bucket_path.is_dir():
			data = [
				("Path", g.path),
				("Type", "directory" if bucket_path.is_dir() else "file"),
			]
		else:
			stats = s3_re.ObjectSummary(bucket_name, item_path)
			data = [
				("Path", g.path),
				("Type", "directory" if bucket_path.is_dir() else "file"),
				("Last modified", stats.last_modified),
				("Bytes", stats.size),
				("Size", naturalsize(stats.size)),
				("e_tag", stats.e_tag),
				("Owner", stats.owner)
			]
	else:
		if not os.path.exists(g.path):
			abort(404)

		data = [
			("Path", g.path),
			("Type", getType(g.path)),
			("Last modified", time.ctime(os.path.getmtime(g.path))),
			("Permissions", "0" + oct(os.stat(g.path).st_mode & 0o777)[2 :])
		]


	if not g.path.startswith("/s3buckets/"):
		owner = os.stat(g.path).st_uid
		group = os.stat(g.path).st_gid

		try:
			owner = getpwuid(owner).pw_name

		except:
			pass

		try:
			group = getgrgid(group).gr_name

		except:
			pass

		data.append(("Owner", owner))
		data.append(("Group", group))

	if not g.path.startswith("/s3buckets/"):
		if os.path.isdir(g.path):
			data.append(("Bytes", BaseExtension.AJAX_DIR_BYTES))
			data.append(("Size", BaseExtension.AJAX_DIR_SIZE))
			data.append(("Number of files", BaseExtension.AJAX_DIR_NUM_FILES))
			data.append(("Number of links", BaseExtension.AJAX_DIR_NUM_LINKS))
			data.append(("Number of directories", BaseExtension.AJAX_DIR_NUM_DIRS))

		else:

			numBytes = os.path.getsize(g.path)

			data.append(("Bytes", numBytes))
			data.append(("Size", naturalsize(numBytes)))


	if not os.path.isdir(g.path) and (os.path.isfile(request-path) or os.path.islink(g.path)) and os.path.exists(g.path):
		data.append(("Likely MIME type", Magic(mime = True).from_file(g.path)))

	return data

def infoDir():
	return BaseExtension().info(getInfo())

def infoFile():
	for extension in extensions:
		if extension.Extension.PATTERN.match(g.path):
			return extension.Extension().info(getInfo())

	return BaseExtension().info(getInfo())

def check_s3_perms(s3_bucket_name):
	global WHITELIST

	if s3_bucket_name in WHITELIST:
		return True
	try:
		response = s3_cl.get_bucket_tagging(Bucket=s3_bucket_name)
		for tag in response["TagSet"]:
			tag = dict(tag)
			if tag["Key"] == "SallyBrowse":
				if tag["Key"]["SallyBrowse"] == "No":
					if s3_bucket_name in WHITELIST:
						WHITELIST.remove(s3_bucket_name)
					return True
				else:
					WHITELIST.append(s3_bucket_name)
					return False
	except Exception as e:
		print (e)


def init_saml_auth(req):
	auth = OneLogin_Saml2_Auth(req, custom_base_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saml'))
	return auth


def prepare_flask_request(request):
	# If server is behind proxys or balancers use the HTTP_X_FORWARDED fields
	url_data = urlparse(request.url)
	return {
		'https': 'on',
		'http_host': request.host,
		'server_port': url_data.port,
		'script_name': request.path,
		'get_data': request.args.copy(),
		# Uncomment if using ADFS as IdP, https://github.com/onelogin/python-saml/pull/144
		# 'lowercase_urlencoding': True,
		'post_data': request.form.copy()
	}


@app.route('/saml/sso', methods=['GET', 'POST'])
def saml():
	req = prepare_flask_request(request)
	logging.error(json.dumps(req))
	auth = init_saml_auth(req)
	try:
		auth.process_response()
	except Exception as e:
		logging.error("Auth error: ", e)

	# logging.info("error reason: " + auth.get_last_error_reason())
	logging.info("auth.is_authenticated() " + str(auth.is_authenticated()))

	if auth.is_authenticated():
		logging.info("Admin user logged in: " + json.dumps(auth.get_nameid()))
		response = make_response(redirect('https://browser.appen.com.cn/'))
		cookie_jwt = jwt.encode({'user': auth.get_nameid()}, os.environ.get("COOKIE_SECRET") or app.config.get("COOKIE_SECRET"), algorithm='HS256')
		response.set_cookie(key='X-AC-Auth', value=cookie_jwt, max_age=28800, secure=True)
		return response

	return redirect(os.environ.get("SSO_URL") or app.config.get("SSO_URL"))


def requires_auth(fn):
	@wraps(fn)
	def decorated(*args, **kwargs):

		# encoded_jwt = request.headers.get("X-Amzn-Oidc-Data")
		encoded_jwt = request.cookies.get("X-AC-Auth")
		if encoded_jwt:
			try:
				payload = jwt.decode(encoded_jwt, os.environ.get("COOKIE_SECRET") or app.config.get("COOKIE_SECRET"),
									 algorithms=['HS256'])
				g.username = payload["user"]
			except Exception as e:
				logging.error("decrypt token error: ", e)
				return redirect(os.environ.get("SSO_URL") or app.config.get("SSO_URL"))

		else:
			# No data forwarded from load balancer.
			# Authentication is probably not configured in load balancer or app is hosted locally... or whatever.
			g.username = "Appen User"
			return redirect(os.environ.get("SSO_URL") or app.config.get("SSO_URL"))

		return fn(*args, **kwargs)

	return decorated


@app.route("/")
@app.route("/<path:path>")
@requires_auth
def browse(*args, **kwargs):
	global WHITELIST

	if "/s3buckets" in g.path:
		if g.path == "/s3buckets/":
			g.path = "/s3buckets"
		match = re.match(BUCKET_NAME, g.path)
		if match:
			match = match.groupdict()
			if not check_s3_perms(match["bucket"]):
				abort(403)
		# If it's a directory
		bucket_path = get_path()
		if not bucket_path.name or bucket_path.is_dir():
			if ARG_DOWNLOAD in request.args:
				return downloadDir()

			elif ARG_INFO in request.args:
				return infoDir()

			# elif ARG_EXTRA_DIR_INFO in request.args:
			# 	return getExtraDirInfo()

			elif ARG_LIST in request.args:
				return listDir()
			return browseDir()
		if not g.path.startswith("/s3buckets"):
			abort(403)

		# File stuff now
		if ARG_DOWNLOAD in request.args:
			return downloadFile()

		elif ARG_INFO in request.args:
			return infoFile()

		# elif ARG_DOWNLOAD_ALAW_TO_WAV in request.args:
		# 	return downloadAlaw2Wav()

		# elif ARG_DOWNLOAD_ULAW_TO_WAV in request.args:
		# 	return downloadUlaw2Wav()

		return previewFile()

	if not os.path.isabs(g.path):
		abort(403)

	if not g.path.startswith(COMMON_ROOT):
		if g.path == "/":
			return redirect(COMMON_ROOT)

		abort(403)

	if os.path.exists(g.path):
		if os.path.isdir(g.path):
			if ARG_DOWNLOAD in request.args:
				return downloadDir()

			elif ARG_INFO in request.args:
				return infoDir()

			elif ARG_EXTRA_DIR_INFO in request.args:
				return getExtraDirInfo()

			elif ARG_LIST in request.args:
				return listDir()

			return browseDir()

		if not g.path.startswith(SERVE_DIRECTORIES):
			abort(403)
		if ARG_DOWNLOAD in request.args:
			return downloadFile()

		elif ARG_INFO in request.args:
			return infoFile()

		elif ARG_DOWNLOAD_ALAW_TO_WAV in request.args:
			return downloadAlaw2Wav()

		elif ARG_DOWNLOAD_ULAW_TO_WAV in request.args:
			return downloadUlaw2Wav()

		return previewFile()

	abort(404)

@app.before_first_request
def setupCommonRoot():
	global COMMON_ROOT
	global SERVE_DIRECTORIES

	if len(SERVE_DIRECTORIES) == 0:
		SERVE_DIRECTORIES = ("/",)
		COMMON_ROOT = "/"

		return

	else:
		SERVE_DIRECTORIES = tuple([os.path.abspath(d) for d in SERVE_DIRECTORIES])

	partsList = []

	for d in SERVE_DIRECTORIES:
		partsList.append(d.split("/"))

	i = 0
	commonParts = []

	while True:
		part = None

		for parts in partsList:
			if i >= len(parts):
				break

			if part is None:
				part = parts[i]

			elif part != parts[i]:
				break

		else:
			commonParts.append(part)

			i += 1

			continue

		break

	COMMON_ROOT = "/".join(commonParts) or "/"


@app.before_first_request
def loadExtensions():
	global extensions

	for extension in os.listdir(EXTENSION_DIR):
		if not extension.startswith("__"):
			extensionPath = os.path.join(EXTENSION_DIR, extension)

			if os.path.isdir(extensionPath):
				extension = "sallybrowse.extensions.%s" % extension
				extensions.append(importlib.import_module(extension))

	extensions = sorted(extensions, reverse = True, key = lambda extension: extension.Extension.PRIORITY)


if __name__ == "__main__":
	app.run(debug=True)
