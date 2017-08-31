#include <stdio.h> /* printf, sprintf */
#include <stdlib.h> /* exit, atoi, malloc, free */
#include <unistd.h> /* read, write, close */
#include <string.h> /* memcpy, memset */
#include <time.h>
#include <errno.h> /* errnos */
#include <pthread.h>
#include <signal.h>
#include <sys/time.h>

#include <usermetric.h>
#include <influxdb.h>
#include <fileoutput.h>
#include <libusermetric_debug.h>
#include <queue.h>

typedef enum {
    USER_METRIC,
    USER_ANNOTATION
} submit_type_t;

const char* usermetrictag = "usermetric";
const char* usereventtag = "userannotation";

int libusermetric_debug = 0;

//static int (*submit_value)(char *key, int nfields, char** fields, float* values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues) = NULL;
//static int (*submit_event)(char *key, int nfields, char** fields, char** values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues) = NULL;
static void (*close_output)(void) = NULL;
static int (*submit_string)(char* str) = NULL;

char** deftags = NULL;
int ndeftags = 0;
char** deffields = NULL;
int ndeffields = 0;

void * qbuffer[QUEUESIZE];
queue_t Queue = QUEUE_INITIALIZER(qbuffer);

pthread_t send_thread;
int send_thread_stop = 0;

int max_send = 50;
int send_size = 200;

static unsigned long get_timestamp()
{
    struct timeval tp;
    gettimeofday(&tp, NULL);
    long long mslong = (long long) tp.tv_sec * 1000000L + tp.tv_usec;
    return (unsigned long)mslong*1E3;
}

void debug_usermetric(int val)
{
    if (val >= 0)
        libusermetric_debug = val;
}

void threadhandler(int signum)
{
    send_thread_stop = 1;
}

void *send_thread_func(void *void_sleeptime)
{
    //signal(SIGABRT, threadhandler);
    int sleeptime = *((int*)void_sleeptime);
    int ret = 0;
    int cur_size = 0;
    int cur_idx = 0;
    char * sendbuffer = (char*) malloc(max_send*send_size*sizeof(char));
    if (!sendbuffer)
    {
        printf("Cannot allocate send buffer of size %lu\n", max_send*send_size*sizeof(char));
    }
    while (send_thread_stop == 0)
    {
        cur_size = queue_size(&Queue);
        cur_idx = 0;
        sendbuffer[cur_idx] = '\0';
        if (cur_size > 0)
        {
            printf("Sending %d metrics\n", cur_size);
            while (cur_size > 0 && send_thread_stop == 0)
            {
                
                char* str = (char*)queue_dequeue(&Queue);
                if (submit_string != NULL)
                {
                    if (cur_idx + strlen(str) > max_send*send_size*sizeof(char))
                    {
                        queue_enqueue(&Queue, str);
                        break;
                    }
                    else
                    {
                        strcat(sendbuffer, str);
                        strcat(sendbuffer,"\n");
                        cur_idx += strlen(str)+1;
                    }
                    cur_size--;
                }
            }
            sendbuffer[cur_idx] = '\0';
            ret = submit_string(sendbuffer);
            if (ret < 0)
            {
                printf("Send failed\n");
            }
        }
        if (cur_size == 0 && send_thread_stop != 0)
        {
            fprintf(stderr, "Sleep %d seconds\n", sleeptime);
            sleep(sleeptime);
        }
    }
    printf("Thread exits loop, submit remaining metrics\n");
    cur_size = queue_size(&Queue);
    while (cur_size > 0)
    {
        char* str = (char*)queue_dequeue(&Queue);
        if (submit_string != NULL)
            submit_string(str);
        cur_size--;
    }
    pthread_exit(NULL);
}

static char* getjobid()
{
    if (getenv("PBS_JOBID") != NULL)
        return getenv("PBS_JOBID");
    if (getenv("SLURM_JOBID") != NULL)
        return getenv("SLURM_JOBID");
    return NULL;
}

int add_default_tag(char* key, char* val)
{
    int ret = 0;
    char** tmp = realloc(deftags, (ndeftags+1)*sizeof(char*));
    if (!tmp)
        return -ENOMEM;
    else
        deftags = tmp;
    deftags[ndeftags] = malloc(strlen(key)+strlen(val)+4);
    if (!deftags)
        return -ENOMEM;
    ret = sprintf(deftags[ndeftags], "%s=%s", key, val);
    deftags[ndeftags][ret] = '\0';
    ndeftags++;
    return 0;
}

int add_default_field(char* key, char* val)
{
    int ret = 0;
    char** tmp = realloc(deffields, (ndeffields+1)*sizeof(char*));
    if (!tmp)
        return -ENOMEM;
    else
        deffields = tmp;
    deffields[ndeffields] = malloc(strlen(key)+strlen(val)+4);
    if (!deffields)
        return -ENOMEM;
    ret = sprintf(deffields[ndeffields], "%s=%s", key, val);
    deffields[ndeffields][ret] = '\0';
    ndeffields++;
    return 0;
}


int
init_usermetric(UserMetricOutputType type, char* host, char* port, char* dest, int add_defaults)
{
    int err = 0;
    int sleeptime = 5;
    switch(type)
    {
        case FILE_OUT:
            err = fileoutput_init(host, port, dest, 100);
            close_output = fileoutput_close;
            submit_string = fileoutput_submit_string;
            break;
        case INFLUXDB_OUT:
            err = influxdb_init(host, port, dest, 100);
            close_output = influxdb_close;
            submit_string = influxdb_submit_string;
            break;
    }
    if (add_defaults)
    {
        char tmp[100];
        gethostname(tmp, 100);
        add_default_tag("hostname", tmp);
        //add_default_tag("username", getenv("USER"));
        /*if (getjobid())
        {
            add_default_tag("jobid", getjobid());
        }*/
    }
    pthread_create(&send_thread, NULL, send_thread_func, (void*)&sleeptime);
    return err;
}







/*static int filter_and_extend_tags(int inntags, char** intagkeys, char** intagvalues, char** keys, char** vals, submit_type_t flags)
{
    int ret = 0;
    int valid = 0;
    int fails = 0;
    int i = 0, j = 0;
    int index = 0;
    const char *add_tags = NULL;
    if (flags == USER_METRIC)
        add_tags = usermetrictag;
    else if (flags == USER_ANNOTATION)
        add_tags = usereventtag;
    else
        return -EINVAL;

    for (i=0;i<inntags;i++)
    {
        if (strcmp(intagkeys[i], "hostname") == 0 ||
            strcmp(intagkeys[i], "jobid") == 0 ||
            strcmp(intagkeys[i], "username") == 0 ||
            strcmp(intagkeys[i], "usermetric") == 0)
        {
            fails++;
            continue;
        }
        valid++;
    }

    for (i=0;i<inntags;i++)
    {
        if (strcmp(intagkeys[i], "hostname") == 0 ||
            strcmp(intagkeys[i], "jobid") == 0 ||
            strcmp(intagkeys[i], "username") == 0 ||
            strcmp(intagkeys[i], "usermetric") == 0)
        {
            continue;
        }
        keys[index] = malloc( (strlen(intagkeys[i])+1) * sizeof(char));
        if (!keys[index])
        {
            for (j=0;j<index;j++)
            {
                free(keys[j]);
                free(vals[j]);
            }
            free(keys);
            free(vals);
            return -ENOMEM;
        }
        vals[index] = malloc( (strlen(intagvalues[i])+1) * sizeof(char));
        if (!keys[index])
        {
            for (j=0;j<index;j++)
            {
                free(keys[j]);
                free(vals[j]);
            }
            free(keys[index]);
            free(keys);
            free(vals);
            return -ENOMEM;
        }
        j = snprintf(keys[index], strlen(intagkeys[i])+1, "%s", intagkeys[i]);
        keys[index][j] = '\0';
        j = snprintf(vals[index], strlen(intagvalues[i])+1, "%s", intagvalues[i]);
        vals[index][j] = '\0';
        index++;
    }
    // add hostname
    keys[index] = malloc((strlen("hostname")+1) * sizeof(char));
    if (!keys[index])
    {
        for (j=0;j<index;j++)
        {
            free(keys[j]);
            free(vals[j]);
        }
        free(keys);
        free(vals);
        return -ENOMEM;
    }
    vals[index] = malloc(101 * sizeof(char));
    if (!keys[index])
    {
        for (j=0;j<index;j++)
        {
            free(keys[j]);
            free(vals[j]);
        }
        free(keys[index]);
        free(keys);
        free(vals);
        return -ENOMEM;
    }
    j = snprintf(keys[index], strlen("hostname")+1, "hostname");
    keys[index][j] = '\0';
    gethostname(vals[index], 100);
    vals[index][strlen(vals[index])] = '\0';
    index++;

    // add username
    keys[index] = malloc((strlen("username")+1) * sizeof(char));
    if (!keys[index])
    {
        for (j=0;j<index;j++)
        {
            free(keys[j]);
            free(vals[j]);
        }
        free(keys);
        free(vals);
        return -ENOMEM;
    }
    vals[index] = malloc(101 * sizeof(char));
    if (!keys[index])
    {
        for (j=0;j<index;j++)
        {
            free(keys[j]);
            free(vals[j]);
        }
        free(keys[index]);
        free(keys);
        free(vals);
        return -ENOMEM;
    }
    j = snprintf(keys[index], strlen("username")+1, "username");
    keys[index][j] = '\0';
    j = snprintf(vals[index], strlen(getenv("USER"))+1, "%s", getenv("USER"));
    vals[index][j] = '\0';
    index++;

    // add usermetric identifier
    keys[index] = malloc((strlen(add_tags)+1) * sizeof(char));
    if (!keys[index])
    {
        for (j=0;j<index;j++)
        {
            free(keys[j]);
            free(vals[j]);
        }
        free(keys);
        free(vals);
        return -ENOMEM;
    }
    vals[index] = malloc(10 * sizeof(char));
    if (!keys[index])
    {
        for (j=0;j<index;j++)
        {
            free(keys[j]);
            free(vals[j]);
        }
        free(keys[index]);
        free(keys);
        free(vals);
        return -ENOMEM;
    }
    j = snprintf(keys[index], strlen(add_tags)+1, "%s", add_tags);
    keys[index][j] = '\0';
    j = snprintf(vals[index], 9, "%d", 1);
    vals[index][j] = '\0';
    if (libusermetric_debug)
    {
        printf("Key %d : %s\n", index, keys[index]);
        printf("Value %d : %s\n", index, vals[index]);
    }
    index++;


    // get job id if any
    if (getjobid() != NULL)
    {
        keys[index] = malloc((strlen("jobid")+1) * sizeof(char));
        if (!keys[index])
        {
            for (j=0;j<index;j++)
            {
                free(keys[j]);
                free(vals[j]);
            }
            free(keys);
            free(vals);
            return -ENOMEM;
        }
        vals[index] = malloc(101 * sizeof(char));
        if (!keys[index])
        {
            for (j=0;j<index;j++)
            {
                free(keys[j]);
                free(vals[j]);
            }
            free(keys[index]);
            free(keys);
            free(vals);
            return -ENOMEM;
        }
        j = sprintf(keys[index], "%s", "jobid");
        keys[index][j] = '\0';
        j = sprintf(vals[index], "%s", getjobid());
        vals[index][j] = '\0';
        index++;
    }
    if (libusermetric_debug)
    {
        for(i=0;i<index;i++)
        {
            printf("%s : %s\n", keys[i], vals[i]);
        }
        printf("Return %d\n", index);
    }
    return index;
}

static void delete_tags(int ntags, char** keys, char** vals)
{
    int i = 0;
    if (!keys || !vals)
        return;
    for (i = 0; i < ntags; i++)
    {
        if (keys[i])
            free(keys[i]);
        if (vals[i])
            free(vals[i]);
    }
    free(keys);
    free(vals);
    return;
}*/

static int
calc_length(char *key, int nfields, char** fields, int ntags, char** tagkeys, char** tagvalues)
{
    int i = 0;
    int len = 0;
    len += strlen(key);
    for (i = 0; i < nfields; i++)
    {
        len += strlen(fields[i]) + 2; // for '=' and ','
    }
    for (i = 0; i < ntags; i++)
    {
        len += strlen(tagkeys[i]) + strlen(tagvalues[i]) + 2; // for '=' and ','
    }
    for (i = 0; i <ndeftags; i++)
    {
        len += strlen(deftags[i]) + 1; // for ',', '=' already inside
    }
    len += 50; // for safety and spaces between tags, fields and timestamp
    return len;
}

int is_number(char* val)
{
    if (strspn(val, "0123456789.") == strlen(val))
    {
        return 1;
    }
    return 0;
}

int
supply_uservalues(char *key, int nfields, char** fields, float* values, int ntags, char** tagkeys, char** tagvalues)
{
    int ret = 0, i = 0;
    char* metricstr = NULL;

    if (submit_string)
    {
        int len = calc_length(key, nfields, fields, ntags, tagkeys, tagvalues);
        len += nfields * 20; // for floats in values;

        metricstr = malloc(len*sizeof(char));
        if (!metricstr)
            return -ENOMEM;
        int idx = sprintf(metricstr, "%s", key);
        //printf("%s\n", metricstr);
        for (i=0;i<ntags;i++)
        {
            idx += sprintf(&(metricstr[idx]), ",%s=%s", tagkeys[i], tagvalues[i]);
        }
        //printf("%s\n", metricstr);
        for (i=0;i<ndeftags;i++)
        {
            idx += sprintf(&(metricstr[idx]), ",%s", deftags[i]);
        }
        //printf("%s\n", metricstr);
        idx += sprintf(&(metricstr[idx]), " ");
        if (nfields > 0)
        {
            idx += sprintf(&(metricstr[idx]), "%s=%f", fields[0], values[0]);
        }
        for (i = 1; i< nfields; i++)
        {
            idx += sprintf(&(metricstr[idx]), ",%s=%f", fields[i], values[i]);
        }
        //printf("%s\n", metricstr);
        idx += sprintf(&(metricstr[idx]), " %lu", get_timestamp());
        //printf("%s\n", metricstr);
        metricstr[idx] = '\0';

        //printf("supply_uservalues: %s\n", metricstr);
        queue_enqueue(&Queue, metricstr);

        return ret;
    }
    return -EINVAL;
}

int
supply_userevents(char *key, int nfields, char** fields, char** strings, int ntags, char** tagkeys, char** tagvalues)
{
    int ret = 0, i = 0;
    char* metricstr = NULL;

    if (submit_string)
    {
        int len = calc_length(key, nfields, fields, ntags, tagkeys, tagvalues);
        for (i=0; i<nfields;i++)
            len += strlen(strings[i]) + 3; // for '"' and ','


        metricstr = malloc(len*sizeof(char));
        if (!metricstr)
            return -ENOMEM;
        int idx = sprintf(metricstr, "%s", key);
        //printf("%s\n", metricstr);
        for (i=0;i<ntags;i++)
        {
            idx += sprintf(&(metricstr[idx]), ",%s=%s", tagkeys[i], tagvalues[i]);
        }
        //printf("%s\n", metricstr);
        for (i=0;i<ndeftags;i++)
        {
            idx += sprintf(&(metricstr[idx]), ",%s", deftags[i]);
        }
        //printf("%s\n", metricstr);
        idx += sprintf(&(metricstr[idx]), " ");
        if (nfields > 0)
        {
            if (!is_number(strings[0]))
                idx += sprintf(&(metricstr[idx]), "%s=\"%s\"", fields[0], strings[0]);
            else
                idx += sprintf(&(metricstr[idx]), "%s=%s", fields[0], strings[0]);
        }
        for (i = 1; i< nfields; i++)
        {
            if (!is_number(strings[i]))
                idx += sprintf(&(metricstr[idx]), ",%s=\"%s\"", fields[i], strings[i]);
            else
                idx += sprintf(&(metricstr[idx]), ",%s=%s", fields[i], strings[i]);
        }
        //printf("%s\n", metricstr);
        idx += sprintf(&(metricstr[idx]), " %lu", get_timestamp());
        //printf("%s\n", metricstr);
        metricstr[idx] = '\0';


        //printf("supply_userevents: %s\n", metricstr);
        queue_enqueue(&Queue, metricstr);

        return ret;
    }
    return -EINVAL;
}



int
supply_uservalue(char *key, char* field, float value, int ntags, char** tagkeys, char** tagvalues)
{
    int ret = 0;
    char** tmpfields = malloc(sizeof(char*));
    if (!tmpfields)
        return -ENOMEM;
    float* tmpvalues = malloc(sizeof(float));
    if (!tmpvalues)
    {
        free(tmpfields);
        return -ENOMEM;
    }
    tmpfields[0] = field;
    tmpvalues[0] = value;
    ret = supply_uservalues(key, 1, tmpfields, tmpvalues, ntags, tagkeys, tagvalues);
    /*if (submit_value)
        ret = submit_value(key, 1, tmpfields, tmpvalues, get_timestamp(), ntags, tagkeys, tagvalues);*/
    free(tmpfields);
    free(tmpvalues);
    return ret;
}

int supply_userevent(char *key, char* field, char* string, int ntags, char** tagkeys, char** tagvalues)
{
    int ret = 0;
    char** tmpfields = malloc(sizeof(char*));
    if (!tmpfields)
        return -ENOMEM;
    char** tmpvalues = malloc(sizeof(char*));
    if (!tmpvalues)
    {
        free(tmpfields);
        return -ENOMEM;
    }

    tmpfields[0] = field;
    tmpvalues[0] = string;
    /*if (submit_event)
        ret = submit_event(key, 1, tmpfields, tmpvalues, get_timestamp(), ntags, tagkeys, tagvalues);*/
    supply_userevents(key, 1, tmpfields, tmpvalues, ntags, tagkeys, tagvalues);
    free(tmpfields);
    free(tmpvalues);
    return ret;
}

void
close_usermetric()
{
    send_thread_stop = 1;
    pthread_kill(send_thread, 0);
    pthread_join(send_thread, NULL);
    if (close_output)
    {
        printf("Close output\n");
        close_output();
    }
    return;
}


/*int main(int argc, char* argv[])
{
    int i;
    char ** tagkeys;
    char ** tagvalues;
    char ** fields;
    float * fvalues;
    char ** svalues;
    tagkeys = malloc(2 * sizeof(char*));
    tagvalues = malloc(2 * sizeof(char*));
    fields = malloc(2 * sizeof(char*));
    fvalues = malloc(2 * sizeof(float));
    tagkeys[0] = "cpu";
    tagkeys[1] = "hostname";
    tagvalues[0] = "2";
    tagvalues[1] = "heidi";
    fields[0] = "loop_count";
    fields[1] = "LUPs";


    init_usermetric(INFLUXDB_OUT, "fepa", "8086", "unrz139");
    supply_userevent("annotations", "event", "loop_begin", 2, tagkeys, tagvalues);
    for (i=0; i < 100; i++)
    {
        fvalues[0] = i;
        fvalues[1] = i*1200.0;
        supply_uservalues("calculations", 2, fields, fvalues, 2, tagkeys, tagvalues);
    }
    supply_userevent("annotations", "event", "loop_end", 2, tagkeys, tagvalues);
    free(tagkeys);
    free(tagvalues);
    free(fields);
    free(fvalues);
    return 0;
}*/
