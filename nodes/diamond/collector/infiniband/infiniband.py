# coding=utf-8

"""
Collect data from InfiniBand devices

#### Dependencies

 * [subprocess](http://docs.python.org/library/subprocess.html)

#### Configuration

Configuration is done by:

Create a file named: IBCollector.conf in the collectors_config_path

 * enabled = true
 * iblid = "/sys/class/infiniband/mlx4_0/ports/1/lid"

Test your configuration using the following command:

diamond-setup --print -C IBCollector

You should get a response back that indicates 'enabled': True

"""

import diamond.collector
import time
import os
import sys
import subprocess
import re



class IBCollector(diamond.collector.Collector):

    def __init__(self, *args, **kwargs):
        """
        Create a new instance of the IBCollector
        """

        self.iblid = ''

        super( IBCollector, self ).__init__( *args, **kwargs )
    

    def get_default_config_help(self):
        config_help = super(IBCollector, self).get_default_config_help()
        config_help.update({
            'iblid':'InfiniBand device',
        })
        return config_help

    def get_default_config(self):
        """
        Returns the default collector settings
        """
        config = super(IBCollector, self).get_default_config()
        config.update({
            'iblid':'/sys/class/infiniband/mlx4_0/ports/1/lid',
        })

        try:
            f = open( config[ "iblid" ], 'r' )
            finput = f.read()
            f.close()
        except IOError as ioe:
            self.log.error( "Cannot read iblid from file: %s", repr(ioe) )
        else:
            self.iblid = finput.rstrip('\n')

        return config

    def collect(self):
        cmd = "/usr/sbin/perfquery -r " + self.iblid + " 1 0xf000"
        recv = 0
        send = 0
        try:
            proc = subprocess.Popen([cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (out, err) = proc.communicate()
        except subprocess.CalledProcessError, e:
            self.log.error("%s error launching: %s; skipping" % (cmd, e))
            return
        if proc.returncode:
            self.log.error("%s return exit value %s; skipping" % (cmd, proc.returncode))
            return
        if not out:
            self.log.info("%s return no output" % absolutescriptpath)
            return
        if err:
            self.log.error("%s return error output: %s" % (cmd, err))
            return

        timestamp = time.time()

        for line in filter(None, out.split('\n')):
            if line.startswith("PortRcvData:") or line.startswith("RcvData:"):
                recv = float(line.rpartition('.')[2])
            elif line.startswith("PortXmitData:") or line.startswith("XmtData:"):
                send = float(line.rpartition('.')[2])

        self.publish("ib_recv", recv, precision=2, timestamp=timestamp)
        self.publish("ib_xmit", send, precision=2, timestamp=timestamp)
