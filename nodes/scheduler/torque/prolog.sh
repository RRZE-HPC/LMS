#!/bin/bash

JOBID=$1
USER=$2
QUEUE=$9
GROUP=$3
JOBNAME=$4
REQRES=$5


# Signal the starting of a new job
# Detect some system parameters. Can be used e.g. for templating later
# or for pretty printing
CPU_FAMILY=$(grep "family" /proc/cpuinfo | sort -u | rev | cut -d ' ' -f1 | rev)
CPU_MODEL=$(grep "model" /proc/cpuinfo | grep -v "name" | sort -u | rev | cut -d ' ' -f1 | rev)
CPU_MODELNAME=$(grep "model name" /proc/cpuinfo | sort -u | cut -d ':' -f2 | xargs)

if [ -e /usr/local/bin/startjob.py ]; then
    # You can add additonal fields with -f to startjob.
    # For tags you can use -t but be aware that tags will be added to each
    # measurement of the job
    /usr/local/bin/startjob.py -M ${PBS_NODEFILE} -j ${PBS_JOBID} -f walltime=${PBS_WALLTIME} -f jobname=${PBS_JOBNAME} -f queue=${PBS_QUEUE} -f march=${CPU_FAMILY}_${CPU_MODEL} -f cpuname="${CPU_MODELNAME}"
fi


LIKWID_LOCK=/var/run/likwid.lock
# only change permissions if LIKWID_LOCK is a regular
# file; grant permissions to user (if requested) or to hpcop (system user)
if [ -f ${LIKWID_LOCK} ]; then
        if [[ "$REQRES" == *:likwid* ]] ; then
                chown $USER ${LIKWID_LOCK}
        else
                chown hpcop ${LIKWID_LOCK}
        fi
elif [[ "$REQRES" == *:likwid* ]] ; then
        echo "ATTENTION: requested access to performance counters cannot be granted as ${LIKWID_LOCK} does not exist or is no regular file"
fi

# This would be also a good place to save the current system settings (CPU
# frequency, ...) so that is can be reverted in epilog

# Print the link to the job's dashboard
GRAFANA_URL=http://testhost.testdomain.de:3000/
GRAFANA_SLUG=$(echo ${PBS_JOBID//./-} | awk '{print tolower($0)}')
echo "Job monitoring: see at ${GRAFANA_URL}/dashboard/db/${GRAFANA_SLUG}"
