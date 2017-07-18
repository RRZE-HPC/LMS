#!/usr/bin/env python

from setuptools import setup
from glob import glob

setup(name='AdminJobMonitor',
      version='0.1',
      description='Listen to signal packets of the LMS and create the admin view',
      author='Thomas Roehl',
      author_email='Thomas.Roehl@fau.de',
      packages=["AdminJobMonitor"],
      data_files=[("etc" , ["AdminJobMonitor.conf"])],
      entry_points={
        'console_scripts': [
            'adminJobMonitor=AdminJobMonitor.AdminJobMonitor:main'
            ]}
     )
