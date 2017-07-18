# coding=utf-8

"""
Collect number of open file descriptors

#### Dependencies

 * [subprocess](http://docs.python.org/library/subprocess.html)

#### Configuration

Configuration is done by:

Create a file named: OpenFDsCollector.conf in the collectors_config_path

 * enabled = true

Test your configuration using the following command:

diamond-setup --print -C OpenFDsCollector

You should get a response back that indicates 'enabled': True

"""

import diamond.collector
import time
import os
import sys
import subprocess
import re



class OpenFDsCollector(diamond.collector.Collector):
    def get_default_config_help(self):
        config_help = super(OpenFDsCollector, self).get_default_config_help()
        return config_help

    def get_default_config(self):
        """
        Returns the default collector settings
        """
        config = super(OpenFDsCollector, self).get_default_config()
        return config

    def collect(self):
        fname = "/proc/sys/fs/file-nr"
        fds = 0
        try:
            fp = open(fname)
            fds = int(re.split("\s+", fp.read().strip())[0])
            fp.close()
        except:
            pass
        self.publish("openfds", fds)
