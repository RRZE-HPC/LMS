#!/bin/bash

if [ -e /usr/local/bin/endjob.py ]; then
    /usr/local/bin/endjob.py -M ${PBS_NODEFILE} -j ${PBS_JOBID}
fi
