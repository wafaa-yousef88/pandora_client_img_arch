#!/usr/bin/env python
# vi:si:et:sw=4:sts=4:ts=4
# encoding: utf-8
from distutils.core import setup

setup(
    name="pandora_client",
    version="1.0",
    description='''pandora_client - headless archive client for pan.do/ra

can be used instead of OxFF to keep archive and pan.do/ra instance in sync.
''',
    author="j",
    author_email="j@mailb.org",
    url="http://code.0x2620.org/pandora_client",
    download_url="http://code.0x2620.org/pandora_client/download",
    license="GPLv3",
    scripts = [
        'bin/pandora_client',
    ],
    packages=[
        'pandora_client'
    ],
    keywords = [
],
    classifiers = [
      'Operating System :: OS Independent',
      'Programming Language :: Python',
      'License :: OSI Approved :: GNU General Public License (GPL)',
    ],
)

