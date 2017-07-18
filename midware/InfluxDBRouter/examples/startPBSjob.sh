#!/bin/bash

CPU_FAMILY=$(grep "family" /proc/cpuinfo | sort -u | rev | cut -d ' ' -f1 | rev)
CPU_MODEL=$(grep "model" /proc/cpuinfo | grep -v "name" | sort -u | rev | cut -d ' ' -f1 | rev)
CPU_MODELNAME=$(grep "model name" /proc/cpuinfo | sort -u | cut -d ':' -f2 | xargs)

./startjob.py -M ${PBS_NODEFILE} -j ${PBS_JOBID} -f walltime=${PBS_WALLTIME} -f jobname=${PBS_JOBNAME} -f queue=${PBS_QUEUE} -f march=${CPU_FAMILY}_${CPU_MODEL} -f cpuname="${CPU_MODELNAME}"


