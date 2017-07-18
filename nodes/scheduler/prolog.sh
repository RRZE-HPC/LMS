#!/bin/bash

GRAFANA_URL=http://testhost.testdomain.de:3000/
GRAFANA_SLUG=$(echo ${PBS_JOBID/./-} | awk '{print tolower($0)}')


CPU_FAMILY=$(grep "family" /proc/cpuinfo | sort -u | rev | cut -d ' ' -f1 | rev)
CPU_MODEL=$(grep "model" /proc/cpuinfo | grep -v "name" | sort -u | rev | cut -d ' ' -f1 | rev)
CPU_MODELNAME=$(grep "model name" /proc/cpuinfo | sort -u | cut -d ':' -f2 | xargs)

if [ -e /usr/local/bin/startjob.py ]; then
    /usr/local/bin/startjob.py -M ${PBS_NODEFILE} -j ${PBS_JOBID} -f walltime=${PBS_WALLTIME} -f jobname=${PBS_JOBNAME} -f queue=${PBS_QUEUE} -f match=${CPU_FAMILY}_${CPU_MODEL} -f cpuname="${CPU_MODELNAME}"
fi

echo "Job monitoring: see at ${GRAFANA_URL}/dashboard/db/${GRAFANA_SLUG}"
