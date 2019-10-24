#!/usr/bin/env python3

import sys, os, re, importlib, time
import boto3, botocore

from io import BytesIO
from pwd import getpwuid
from grp import getgrgid
from collections import namedtuple, defaultdict
from subprocess import Popen, PIPE
from zipstream import ZipFile, ZIP_DEFLATED
from humanize import naturalsize
from flask import Flask, send_file, escape, request, abort, Response, render_template, jsonify, redirect
from magic import Magic
from sallybrowse.extensions import BaseExtension

ARG_DOWNLOAD = "dl"
ARG_INFO = "info"
ARG_LIST = "list"
ARG_EXTRA_DIR_INFO = "extradirinfo"
ARG_DOWNLOAD_ALAW_TO_WAV = "alaw2wavdl"
ARG_DOWNLOAD_ULAW_TO_WAV = "ulaw2wavdl"
EXTENSION_DIR = os.path.join(os.path.dirname(__file__), "extensions")
COMMON_ROOT = None # Do not change

if "SERVE_DIRECTORIES" in os.environ:
	SERVE_DIRECTORIES = os.environ["SERVE_DIRECTORIES"].split(":")

else:
	SERVE_DIRECTORIES = tuple([
	# Put the directories you wish to serve here.
	# If left empty, all directories (/) will be served.
])

app = Flask(__name__, static_url_path = "/static", template_folder = os.path.join(os.path.dirname(__file__), "templates"))
extensions = []

session = boto3.Session(profile_name='AWS.AD.CORP.PeDeveloper_profile')

dev_s3_client = session.client('s3')

s3 = session.resource('s3')

S3Obj = namedtuple('S3Obj', ['key', 'mtime', 'size', 'ETag'])

def folders(client, bucket, prefix=''):
	return_list = []
	paginator = client.get_paginator('list_objects')
	q = []
	for result in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter='/'):
		if 'CommonPrefixes' in result:
			q = [S3Obj(f['Prefix'], None, None, None) for f in result['CommonPrefixes']]
		if 'Contents' in result:
			q += ([S3Obj(f['Key'], f['LastModified'], f['Size'], f['ETag']) for f in result['Contents']])
	return q

def s3BucketBrowse(bucket, prfx):
	entries = []
	try:
		list_dir = folders(dev_s3_client, bucket, prefix=prfx)
		for item in list_dir:
			print (prfx, item[0].replace(prfx, ""))
			if not item[-1]: #Means it's a folder i believe
				entry = {
					"dir": item[0].replace(prfx, ""),
					"name": item[0].replace(prfx, ""),
					"size": "N/A",
					"type": "directory"
				}
			else:
				entry = {
					"dir": item[0].split("/")[:-1],
					"name": item[0].split("/")[-1],
					"size": naturalsize(item[2]),
					"type": "file"
				}
			entries.append(entry)
	except Exception as e:
		print(e)
	return entries

def s3TopLevelBrowse():
	entries = []
	for bucket in dev_s3_client.list_buckets()["Buckets"]:
		entry = {
			"dir": bucket["Name"],
			"name": bucket["Name"],
			"size": "N/A",
			"type": "S3 Bucket"
		}
		entries.append(entry)
	return entries

def browseDir():
	print ("BROWSEDIR")
	entries = []
	if request.path == "/s3buckets":
		try:
			entries = s3TopLevelBrowse()
		except Exception as e:
			print (e)
	elif request.path.startswith("/s3buckets/"):
		try:
			bucketname = request.path.split("/")[2]
			prefix_target = ("/".join(request.path.split("/")[3:])).strip()
			if prefix_target == "/":
				prefix_target = ""
			print (request.path, bucketname, prefix_target)
			entries = s3BucketBrowse(bucketname, prefix_target)
		except Exception as e:
			print (e)
	else:
		try:
			files = os.listdir(request.path)
		except:
			files = []


		for file in files:
			path = os.path.join(request.path, file)

			if not path.startswith(SERVE_DIRECTORIES):
				continue

			try:
				entry = {
					"dir": request.path,
					"name": file,
					"type": getType(path)
				}

				if not os.path.isdir(path) and (os.path.isfile(path) or os.path.islink(path)) and os.path.exists(path):
					entry["bytes"] = os.path.getsize(path)
					entry["size"] = naturalsize(entry["bytes"])

				else:
					entry["bytes"] = "N/A"
					entry["size"] = "N/A"

				entries.append(entry)

			except:
				continue
		if request.path == "/":
			s3entry = {
				"dir": "/s3buckets",
				"name": "s3buckets",
				"type": "S3 Bucket"
			}
			entries.append(s3entry)
	return render_template("dir.html", entries = sorted(entries, key = lambda entry: entry["name"]))

def previewFile():

	print ("PREVIEW")
	for extension in extensions:
		if extension.Extension.PATTERN.match(request.path):
			return extension.Extension().preview()

	abort(404)

def listDir():

	print ("LISTDIR")
	paths = []

	try:
		files = os.listdir(request.path)

	except:
		files = []

	for file in files:
		path = os.path.join(request.path, file)

		if not path.startswith(SERVE_DIRECTORIES):
			continue

		paths.append(path)

	return "<br/>".join(sorted(paths))

def downloadDir():

	print ("DLDIR")
	def generateFileChunks(path):
		with open(path, "rb") as handle:
			while True:
				chunk = handle.read(1024)

				if len(chunk) == 0:
					return

				yield chunk

	def generateChunks(path):
		stream = ZipFile(mode = "w", compression = ZIP_DEFLATED)

		for root, _, files in os.walk(path):
			for file in files:
				filePath = os.path.join(root, file)

				if not os.path.exists(filePath):
					continue

				try:
					stream.write_iter(os.path.relpath(filePath, os.path.dirname(path)).lstrip("/"), generateFileChunks(filePath))

				except:
					continue

				for chunk in stream.next_file():
					yield chunk

		for chunk in stream:
			yield chunk

	filename = (os.path.basename(request.path) or "root") + ".zip"

	response = Response(generateChunks(request.path), mimetype = "application/zip")
	response.headers["Content-Disposition"] = "attachment; filename=%s" % filename

	return response

def downloadFile():
	return send_file(request.path, conditional = True, as_attachment = True)

def downloadAlaw2Wav():
	pipe = Popen(("sox", "-t", ".raw", "-e", "a-law", "-c", "1", "-r", "8000", request.path, "-t", "wavpcm", "-"), stdout = PIPE)
	out, _ = pipe.communicate()

	if pipe.returncode != 0:
		abort(404)

	buffer = BytesIO(out)
	filename = os.path.basename(request.path) + ".wav"

	return send_file(buffer, conditional = True, as_attachment = True, attachment_filename = filename)

def downloadUlaw2Wav():
	pipe = Popen(("sox", "-t", ".raw", "-e", "u-law", "-c", "1", "-r", "8000", request.path, "-t", "wavpcm", "-"), stdout = PIPE)
	out, _ = pipe.communicate()

	if pipe.returncode != 0:
		abort(404)

	buffer = BytesIO(out)
	filename = os.path.basename(request.path) + ".ulaw"

	return send_file(buffer, conditional = True, as_attachment = True, attachment_filename = filename)

def getType(path):

	print ("TYPE")
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

	print ("EXTRADIR")
	data = {}
	size = 0
	numFiles = 0
	numDirs = 0
	numLinks = 0
	
	for root, dirs, files in os.walk(request.path):
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

	print ("INFODIR")
	if not os.path.exists(request.path):
		abort(404)

	data = [
		("Path", request.path),
		("Type", getType(request.path)),
		("Last modified", time.ctime(os.path.getmtime(request.path))),
		("Permissions", "0" + oct(os.stat(request.path).st_mode & 0o777)[2 :])
	]

	owner = os.stat(request.path).st_uid
	group = os.stat(request.path).st_gid

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

	if os.path.isdir(request.path):
		data.append(("Bytes", BaseExtension.AJAX_DIR_BYTES))
		data.append(("Size", BaseExtension.AJAX_DIR_SIZE))
		data.append(("Number of files", BaseExtension.AJAX_DIR_NUM_FILES))
		data.append(("Number of links", BaseExtension.AJAX_DIR_NUM_LINKS))
		data.append(("Number of directories", BaseExtension.AJAX_DIR_NUM_DIRS))

	else:
		numBytes = os.path.getsize(request.path)

		data.append(("Bytes", numBytes))
		data.append(("Size", naturalsize(numBytes)))

	if not os.path.isdir(request.path) and (os.path.isfile(request.path) or os.path.islink(request.path)) and os.path.exists(request.path):
		data.append(("Likely MIME type", Magic(mime = True).from_file(request.path)))

	return data

def infoDir():
	return BaseExtension().info(getInfo())

def infoFile():
	for extension in extensions:
		if extension.Extension.PATTERN.match(request.path):
			return extension.Extension().info(getInfo())

	return BaseExtension().info(getInfo())

@app.route("/")
@app.route("/<path:path>")
def browse(*args, **kwargs):
	print (args, kwargs)
	print ("Processing path {} with args {}".format(request.path, request.args))
	if request.path == "/s3buckets":
		print ("Top levle of all buckets")
		return browseDir()

	if "/s3buckets/" in request.path:
		print ("Buckets and things in it")

		#If it's a directory
		bucket_path = "/".join(request.path.split("/")[:3])
		if request.path.endswith("/") or request.path == bucket_path:
			# if ARG_DOWNLOAD in request.args:
			# 	return downloadDir()

			# elif ARG_INFO in request.args:
			# 	return infoDir()

			# elif ARG_EXTRA_DIR_INFO in request.args:
			# 	return getExtraDirInfo()

			# elif ARG_LIST in request.args:
			# 	return listDir()
			return browseDir()
		if not request.path.startswith("/s3buckets"):
			abort(403)

		# if ARG_DOWNLOAD in request.args:
		# 	return downloadFile()

		# elif ARG_INFO in request.args:
		# 	return infoFile()

		# elif ARG_DOWNLOAD_ALAW_TO_WAV in request.args:
		# 	return downloadAlaw2Wav()

		# elif ARG_DOWNLOAD_ULAW_TO_WAV in request.args:
		# 	return downloadUlaw2Wav()
			
		return previewFile()

	if not os.path.isabs(request.path):
		abort(403)

	if not request.path.startswith(COMMON_ROOT):
		if request.path == "/":
			return redirect(COMMON_ROOT)

		abort(403)

	if os.path.exists(request.path):
		if os.path.isdir(request.path):
			if ARG_DOWNLOAD in request.args:
				return downloadDir()

			elif ARG_INFO in request.args:
				return infoDir()

			elif ARG_EXTRA_DIR_INFO in request.args:
				return getExtraDirInfo()

			elif ARG_LIST in request.args:
				return listDir()

			return browseDir()

		if not request.path.startswith(SERVE_DIRECTORIES):
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

	print ("SETUP")
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

	print ("EXTENSION")
	global extensions

	for extension in os.listdir(EXTENSION_DIR):
		if not extension.startswith("__"):
			extensionPath = os.path.join(EXTENSION_DIR, extension)

			if os.path.isdir(extensionPath):
				extension = "sallybrowse.extensions.%s" % extension

				extensions.append(importlib.import_module(extension))

	extensions = sorted(extensions, reverse = True, key = lambda extension: extension.Extension.PRIORITY)

if __name__ == "__main__":
	app.run(debug = True)
