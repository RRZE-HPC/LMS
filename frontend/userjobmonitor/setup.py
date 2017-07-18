#!/usr/bin/env python

from setuptools import setup
from glob import glob

setup(name='userjobmonitor',
      version='0.1',
      description='Listen to signal packets of the LMS and create views for users',
      author='Thomas Roehl',
      author_email='Thomas.Roehl@fau.de',
      packages=["userjobmonitor"],
      data_files=[("etc" , ["UserJobMonitor.conf"])],
      entry_points={
        'console_scripts': [
            'userJobMonitor=userjobmonitor.UserJobMonitor:main'
            ]}
     )
