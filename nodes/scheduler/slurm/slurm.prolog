

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
    # startjob accepts only a file with hosts, so save all job hosts in a
    # temporary file
    NODEFILE=/tmp/hostlist.$$
    scontrol show hostname ${SLURM_NODELIST} > ${NODEFILE}
    # Parse the time limit and calculate number of seconds
    WALLTIME=$(scontrol show job | grep "TimeLimit" | awk '{print $2}' | cut -d '=' -f2)
    WALLTIME_S=(($(echo $WALLTIME | cut -d':' -f1) * 3600))
    WALLTIME_S=(($WALLTIME_S + ($(echo $WALLTIME | cut -d':' -f2) * 60)))
    WALLTIME_S=(($WALLTIME_S + $(echo $WALLTIME | cut -d':' -f3)))
    /usr/local/bin/startjob.py -M ${NODEFILE} -j ${SLURM_JOB_ID} -f walltime=${WALLTIME_S} -f jobname=${SLURM_JOB_NAME} -f cluster=${SLURM_CLUSTER_NAME} -f queue=${SLURM_JOB_PARTITION} -f march=${CPU_FAMILY}_${CPU_MODEL} -f cpuname="${CPU_MODELNAME}"
    rm ${NODEFILE}
fi

LIKWID_LOCK=/var/run/likwid.lock
# create LIKWID_LOCK if it does not exist yet; should always be created by some
# other startup script - but to be safe
if [ ! -e ${LIKWID_LOCK} ]; then
        touch ${LIKWID_LOCK}
fi

# only change permissions if LIKWID_LOCK is a regular file;
# grant permissions to user (if requested) or to hpcop
if [ -f ${LIKWID_LOCK} ]; then
        if [[ "$SLURM_JOB_CONSTRAINTS" =~ "hwperf" ]] ; then
                chown $SLURM_JOB_USER ${LIKWID_LOCK}
        else
                chown hpcop ${LIKWID_LOCK}
        fi
elif [[ "$SLURM_JOB_CONSTRAINTS" =~ "hwperf" ]] ; then
        echo "ATTENTION: requested access to performance counters cannot be granted as ${LIKWID_LOCK} does not exist or is no regular file"
fi
