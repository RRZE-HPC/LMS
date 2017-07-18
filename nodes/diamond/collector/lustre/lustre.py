# coding=utf-8

"""
Collect data from Lustre file system

modified by rdietric : 
* enable collection for multiple file systems
* added collection of lustre metrics from "extends_stats"
* write only values that have changed

#### Dependencies

 * [subprocess](http://docs.python.org/library/subprocess.html)

#### Configuration

Configuration is done by:

Create a file named: LustreCollector.conf in the collectors_config_path

 * enabled = true
 * sfile = "/proc/fs/lustre/llite/lnec-XXXXXX/stats"

Test your configuration using the following command:

diamond-setup --print -C LustreCollector

You should get a response back that indicates 'enabled': True

"""

import diamond.collector
import time
import os
import sys
import subprocess
import re

# get available file systems
from subprocess import Popen, PIPE, STDOUT

# number of array entries per file system and positions
FS_ENTRIES = 4
POS_FSNAME = 1
POS_LAST_VALUES = 2
POS_LAST_TIME = 3

class LustreCollector(diamond.collector.Collector):
    def __init__(self, *args, **kwargs):
        # initialize object attributes before calling the constructor of 
        # the super class, which triggers get_default_config()

        self.fsCount = 0

        # file systems info array: 
        # 4 entries per file system (full file system path, file system name, dict of last metrics values, last time stamp)
        self.fsInfo = [] 
        self.initialized = False

        super( LustreCollector, self ).__init__( *args, **kwargs )

    def get_default_config_help(self):
        config_help = super(LustreCollector, self).get_default_config_help()
        config_help.update({
            'lustre_path':   'Path to lustre file systems',
            'sfile':         'Lustre stats files',
        })
        return config_help

    def get_default_config(self):
        """
        Returns the default collector settings
        """
        config = super(LustreCollector, self).get_default_config()

        # avoid that this is executed more than once
        if self.initialized:
            return config

        self.initialized = True
        
        # find file systems
        cmd = 'find /proc/fs/lustre/llite/* -type d -maxdepth 0 2>/dev/null'
        p = Popen( cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE )
        stdout, stderr = p.communicate()
        fsPaths = stdout.replace('\n', ',')

        config.update({
            'lustre_path':       fsPaths,
            'sfile':             fsPaths,
        })
         
        #self.log.debug("Parsing file system paths (%s)", fsPaths)
        for idx,fsPath in enumerate( fsPaths.split(',') ):
            if not fsPath:
                continue

            self.fsCount += 1

            #self.log.debug("File System: %s", fsPath)
            p_start = fsPath.rfind('/')
            p_end   = fsPath.rfind('-')

            if p_start == -1:
                continue

            if p_end == -1:
                p_end = fsPath.len()

            #self.log.debug( "File system name: %s", fsPath[p_start+1:p_end] )

            self.fsInfo.append( fsPath ) # full path to the fily system /proc information files
            self.fsInfo.append( fsPath[ p_start + 1 : p_end ] ) # name of file system, e.g. scratch

            # append array entry with empty dictionary for lustre metrics
            self.fsInfo.append( {} )

            # append array entry for time stamp
            self.fsInfo.append( time.time() )

        #self.log.debug( "Found %d file systems", self.fsCount )

        return config

    # Parse the lustre stats file
    # return dictionary with metric names (key) and value (value)
    # TODO: catch index out of bound exceptions if stats file format changes
    def _parseLustreStats( self, finput ):
        lustrestat = {}
        for line in filter( None, finput.split('\n') ):
            linelist = line.split() #re.split( "\s+", line ) #split is faster than re.split
            if linelist[0] == "read_bytes":
                lustrestat["read_requests"] = float(linelist[1]) #do not record, can be generated from extended stats
                lustrestat["read_bytes"] = float(linelist[6])
            elif linelist[0] == "write_bytes":
                lustrestat["write_requests"] = float(linelist[1]) #do not record, can be generated from extended stats
                lustrestat["write_bytes"] = float(linelist[6])
            elif line.startswith("open"):
                lustrestat["open"] = float(linelist[1])
            elif line.startswith("close"):
                lustrestat["close"] = float(linelist[1])
            elif line.startswith("setattr"):
                lustrestat["setattr"] = float(linelist[1])
            elif line.startswith("getattr"):
                lustrestat["getattr"] = float(linelist[1])
            elif line.startswith("statfs"):
                lustrestat["statfs"] = float(linelist[1])
            elif line.startswith("inode_permission"):
                lustrestat["inode_permission"] = float(linelist[1])

        return lustrestat

    # parse the input from lustre extents_stats file
    # return dictionary with metric names (key) and value (value)
    def _parseLustreExtendsStats( self, finput ):
        lustrestat = {}
        for line in filter(None, finput.split('\n')):
            #self.log.debug(line)
            # split (by whitespace) into array
            values = line.split() #split is faster than re.split

            #ignore non-values lines (value lines have 11 values)
            #if pattern_value.match(line): #savely identify values lines
            if len(values) != 11:  #fast access values lines
                continue

            #self.log.debug(values)
            try:
                # reads
                value = float(values[4])
                if value > 0:
                    lustrestat[ "read_"+values[0]+"-"+values[2] ] = value

                # writes
                value = float(values[8])
                if value > 0:
                    lustrestat[ "write_"+values[0]+"-"+values[2] ] = value
            except ValueError as ve:
                self.log.error( "Could not convert to float", repr(ve) )

        return lustrestat

    def _publishLustreMetrics( self, fsIdx, lustreMetrics, timestamp ): 
        fsname     = self.fsInfo[ fsIdx + POS_FSNAME ]
        lastValues = self.fsInfo[ fsIdx + POS_LAST_VALUES ]
        lastTime   = self.fsInfo[ fsIdx + POS_LAST_TIME ]

        # for all lustre metrics
        for metric in lustreMetrics.keys():
            #self.log.debug( "lustre_" + fsname + "_" + metric )
            
            currValue = lustreMetrics[ metric ]

            # in the first call a metric has no last value, hence publish metric and set last value
            if not lastValues.has_key( metric ):
                # publish the metric
                self.publish( fsname + "_" + metric, currValue, precision = 2, timestamp=timestamp )
                    
                # add metric, set value and mark it as written
                lastValues[ metric ] = [ currValue, True ]
                continue

            lastValueInfo = lastValues[ metric ]

            # if metric value changed
            if lastValueInfo[0] != currValue:
                # if last value has not been written
                if lastValueInfo[1] == False:
                    self.publish( fsname + "_" + metric, lastValueInfo[0], precision = 2, timestamp=lastTime )

                # publish current value
                self.publish( fsname + "_" + metric, currValue, precision = 2, timestamp=timestamp )
                    
                # set new last value
                lastValueInfo[0] = currValue
                lastValueInfo[1] = True
            else:
                # value has not been written
                lastValueInfo[1] = False


    def collect(self):
        #self.log.debug("Collect for %d file systems", len(self.fsInfo) / FS_ENTRIES );
        # iterate over file system info list in steps of FS_ENTRIES (as we have FS_ENTRIES entries per file system)
        for idx in xrange( 0, self.fsCount*FS_ENTRIES, FS_ENTRIES):
            fs = self.fsInfo[ idx ]
            if not fs:
                continue 
         
            # get time stamp for all lustre metric values that we read
            timestamp = time.time()

            #self.log.debug("Collect from lustre %s (idx: %d), %d metrics", fs, idx, len(self.fsInfo[idx+2]))
            statFile = fs + "/stats"
            try:
                f = open( statFile, "r" )
                finput = f.read()
                f.close()
            except IOError as ioe:
                self.log.error( "Cannot read from stats file: %s", repr(ioe) )
            else:
                # parse the data into dictionary (key is metric name, value is metric value)
                lustrestat = self._parseLustreStats( finput )

                self._publishLustreMetrics( idx, lustrestat, timestamp )

            statFile = fs + "/extents_stats"
            try:
                f = open( statFile, 'r' )
                finput = f.read()
                f.close()
            except IOError as ioe:
                self.log.error( "Cannot read from extents_stats file: %s", repr(ioe) )
            else:
                # parse the data into dictionary (key is metric name, value is metric value)
                lustrestat = self._parseLustreExtendsStats( finput )

                self._publishLustreMetrics( idx, lustrestat, timestamp )
                
            # save the time stamp for the last values
            self.fsInfo[ idx + POS_LAST_TIME ] = timestamp
    