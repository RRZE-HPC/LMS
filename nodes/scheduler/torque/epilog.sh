#!/bin/bash

# Signal the ending of a job
# The nodefile (-M) and the Job identifiers are the minimum.
# Further information can be supplied with -f
if [ -e /usr/local/bin/endjob.py ]; then
    /usr/local/bin/endjob.py -M ${PBS_NODEFILE} -j ${PBS_JOBID}
fi

# return permission to hpcop for gangliametrics.pl to do
# measurements
if [ -f /var/run/likwid.lock ] ; then
        chown hpcop:root /var/run/likwid.lock
fi


# if you saves system state in prolog, you can reset it here
