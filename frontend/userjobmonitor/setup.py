#!/usr/bin/env python

from setuptools import setup
from glob import glob
import os, os.path

def recursive_glob(path):
    flist = glob(path+"/*")
    outlist = []
    for f in flist:
	if os.path.isdir(f):
	    outlist += recursive_glob(f)
	else:
	    outlist.append(f)
    return outlist
	    

setup(name='userjobmonitor',
      version='0.1',
      description='Listen to signal packets of the LMS and create views for users',
      author='Thomas Roehl',
      author_email='Thomas.Roehl@fau.de',
      packages=["userjobmonitor"],
      data_files=[("etc" , ["UserJobMonitor.conf"]), ( "share/userjobmonitor", recursive_glob("templates"))],
      entry_points={
        'console_scripts': [
            'userJobMonitor=userjobmonitor.userjobmonitor:main'
            ]}
     )
