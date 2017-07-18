#!/usr/bin/env python

from setuptools import setup
from glob import glob

setup(name='influxdbrouter',
      version='0.1',
      description='HTTP Router for InfluxDB measurements with tagging and routing to different databases',
      author='Thomas Roehl',
      author_email='Thomas.Roehl@fau.de',
      packages=["influxdbrouter"],
      scripts=["scripts/startjob.py", "scripts/endjob.py"],
      data_files=[("etc" , ["influxdb-router.conf"])],
      entry_points={
        'console_scripts': [
            'influxdb-router=influxdbrouter.influxdbrouter:main'
            ]}
     )
