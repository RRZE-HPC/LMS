#!/usr/bin/env python

from setuptools import setup
from glob import glob

setup(name='adminjobmonitor',
      version='0.1',
      description='Listen to signal packets of the LMS and create the admin view',
      author='Thomas Roehl',
      author_email='Thomas.Roehl@fau.de',
      packages=["adminjobmonitor"],
      data_files=[("etc" , ["AdminJobMonitor.conf"])],
      entry_points={
        'console_scripts': [
            'adminJobMonitor=adminjobmonitor.adminjobmonitor:main'
            ]}
     )
