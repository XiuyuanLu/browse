import setuptools

with open("README.md", "r") as fh:
	long_description = fh.read()

setuptools.setup(
	name="sallybrowse",
	version="1.0.0",
	author="Simon Allen",
	author_email="author@example.com",
	description="Easy to use web-based file/directory viewer.",
	long_description=long_description,
	long_description_content_type="text/markdown",
	url="https://gitlab.com/garfunkel/sallybrowse",
	packages=setuptools.find_packages(),
	classifiers=[
		"Programming Language :: Python :: 3",
		"License :: OSI Approved :: MIT License",
		"Operating System :: OS Independent",
	],
	python_requires='>=3.6',
)
