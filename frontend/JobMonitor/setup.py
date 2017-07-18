#!/usr/bin/env python

from setuptools import setup
from glob import glob

setup(name='JobMonitor',
      version='0.1',
      description='Basic class to react on data coming from the InfluxDBRouter',
      author='Thomas Roehl',
      author_email='Thomas.Roehl@fau.de',
      packages=["JobMonitor"],
      data_files=[("etc" , ["JobMonitor.conf"])],
     )
