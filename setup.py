#!/usr/bin/env python
# vi:si:et:sw=4:sts=4:ts=4
# encoding: utf-8
from distutils.core import setup

def get_bzr_version():
    import os
    rev = int(os.popen('bzr revno').read())
    if rev:
        return u'%s' % rev
    return u'unknown'

setup(
    name="pandora_client",
    version="1.0.%s" % get_bzr_version() ,
    description='''pandora_client - commandline client and python api for pan.do/ra

can be used interact with pan.do/ra instance via its api.
or instead of OxFF to keep archive and pan.do/ra instance in sync.
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

