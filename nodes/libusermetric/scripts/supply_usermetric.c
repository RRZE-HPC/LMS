#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <getopt.h>
#include <libgen.h>

#include <usermetric.h>

void* realloc_safe(void* ptr, size_t len)
{
    void* tptr = NULL;
    tptr = realloc(ptr, len);
    if (!tptr)
    {
        if (ptr)
            free(ptr);
        return NULL;
    }
    else
    {
        ptr = tptr;
    }
    return ptr;
}

void print_usage(char* argv[])
{
    printf("Usage: %s (-e) -m metricname <valuename1>=<value> -t <tagkey>=<tagvalue>\n", argv[0]);
    printf("Options:\n");
    printf("-m <name>:\t\tName of the metric\n");
    printf("-t <tagkey>=<tagvalue>:\tAdd tags to metric (can be on command line multiple times)\n");
    printf("-e:\t\t\tAssume the supplied values are all strings\n");
    printf("-s <server>:\t\tHostname of the server\n");
    printf("-p <port>:\t\tPort at the server\n");
    printf("-x <path>:\t\tAdditional path for server\n");
    printf("-i:\t\t\tSend data to InfluxDB server (-x for DB name)\n");
    printf("-f:\t\t\tWrite data info a file (-x for file path, -h and -p ignored)\n");
    printf("-d:\t\t\tWrite Debug output\n");
    printf("\n");
    printf("Some tags are filtered and automatically added.\n");
    printf("Filtered are the tag keys 'hostname', 'username', 'jobid' and 'usermetric'\n");
    printf("The hostname=<hostname> tag is automatically set to the local hostname\n");
    printf("The username=<username> tag is automatically set to the user executing %s\n", argv[0]);
    printf("The jobid=<job_id> tag is automatically set to the current job id if available\n");
    printf("\n");
    printf("In order to find the user supplied metrics in the Database later, the tag usermetric=1 is added\n");
    printf("\n");
    printf("The default output handler is InfluxDB. The InfluxDB handler needs hostname, port and DB name.\n");
    printf("If hostname is not given, it is set to localhost. The default DB name is 'default'\n");
    printf("For the file output handler only the path must be set. The hostname and the port are ignored.\n");
    printf("\n");
    printf("Example for named values:\n");
    printf("%s -m calc_app loop_count=3 LUPs=1200 -t cpu=4\n", argv[0]);
    printf("Supplies the two values 'loop_count' and 'LUPs' to the database using the metric name 'calc_app' and setting the additional tag 'cpu'\n");
    printf("\n");
    printf("Example for a single unnamed value (only one value per call usable):\n");
    printf("%s -m loop_count 3 -t cpu=4\n", argv[0]);
    printf("Supplies the value '3' to the database using the metric name 'loop_count' and setting the additional tag 'cpu'\n");
}

int main(int argc, char* argv[])
{
    int ret = 0, c = 0, i = 0;
    char** tmp = NULL;
    char* ptr = NULL;
    char** tagkeys = NULL;
    char** tagvalues = NULL;
    char** fields = NULL;
    char** evalues = NULL;
    float* fvalues = NULL;
    int nrtags = 0;
    int nrfields = 0;
    int supply_events = 0;
    char* metricname = NULL;
    char* hostname = NULL;
    char* portstring = NULL;
    char* path = NULL;
    int value_once = 0;
    int debug = 0;
    UserMetricOutputType otype = INFLUXDB_OUT;
    if (argc == 1)
    {
        print_usage(argv);
        return 0;
    }

    while ((c = getopt (argc, argv, "hifedt:m:s:p:x:")) != -1)
    {
        switch(c)
        {
            case 'h':
                print_usage(argv);
                return 0;
                break;
            case 'i':
                otype = INFLUXDB_OUT;
                break;
            case 'f':
                otype = FILE_OUT;
                break;
            case 'd':
                debug = 1;
                debug_usermetric(debug);
                break;
            case 'm':
                metricname = realloc_safe(metricname, (strlen(optarg)+1)*sizeof(char));
                if (!metricname)
                {
                    ret = -ENOMEM;
                    goto cleanup;
                }
                ret = sprintf(metricname, "%s", optarg);
                metricname[ret] = '\0';
                break;
            case 's':
                hostname = realloc_safe(hostname, (strlen(optarg)+1)*sizeof(char));
                if (!hostname)
                {
                    ret = -ENOMEM;
                    goto cleanup;
                }
                ret = sprintf(hostname, "%s", optarg);
                hostname[ret] = '\0';
                break;
            case 'p':
                portstring = realloc_safe(portstring, (strlen(optarg)+1)*sizeof(char));
                if (!portstring)
                {
                    ret = -ENOMEM;
                    goto cleanup;
                }
                ret = sprintf(portstring, "%s", optarg);
                portstring[ret] = '\0';
                break;
            case 'x':
                path = realloc_safe(path, (strlen(optarg)+1)*sizeof(char));
                if (!path)
                {
                    ret = -ENOMEM;
                    goto cleanup;
                }
                ret = sprintf(path, "%s", optarg);
                path[ret] = '\0';
                break;
            case 'e':
                supply_events = 1;
                break;
            case 't':
                tmp = realloc(tagkeys, (nrtags+1)*sizeof(char*));
                if (!tmp)
                {
                    if (tagkeys) free(tagkeys);
                    if (tagvalues) free(tagvalues);
                    exit(EXIT_FAILURE);
                }
                else
                {
                    tagkeys = tmp;
                }

                tmp = realloc(tagvalues, (nrtags+1)*sizeof(char*));
                if (!tmp)
                {
                    if (tagkeys) free(tagkeys);
                    if (tagvalues) free(tagvalues);
                    exit(EXIT_FAILURE);
                }
                else
                {
                    tagvalues = tmp;
                }
                
                tagkeys[nrtags] = malloc(strlen(optarg) * sizeof(char));
                tagvalues[nrtags] = malloc(strlen(optarg) * sizeof(char));

                ptr = strchr(optarg, '=');
                if (ptr)
                {
                    ret = snprintf(tagkeys[nrtags], ptr-optarg+1, "%s", optarg);
                    tagkeys[nrtags][ret] = '\0';
                    ret = snprintf(tagvalues[nrtags], strlen(ptr+1)+1, "%s", ptr+1);
                    tagvalues[nrtags][ret] = '\0';
                }
                nrtags++;
                break;
            default:
                exit(EXIT_FAILURE);
        }
    }
    if (!metricname)
    {
        fprintf(stderr,"No metric name given. Using default 'annotations'\n");
        metricname = malloc((strlen("annotations")+1) * sizeof(char));
        ret = sprintf(metricname, "annotations");
        metricname[ret] = '\0';
    }
    if (otype == FILE_OUT && !path)
    {
        fprintf(stderr, "No file path given\n");
        ret = -EINVAL;
        goto cleanup;
    }
    if (otype == INFLUXDB_OUT && !portstring)
    {
        portstring = malloc((strlen("8086")+1) * sizeof(char));
        ret = sprintf(portstring, "8086");
        portstring[ret] = '\0';
    }
    if (otype == INFLUXDB_OUT && !path)
    {
        fprintf(stderr, "No DB name given for InfluxDB handler. Using default 'default'\n");
        path = malloc((strlen("default")+1) * sizeof(char));
        ret = sprintf(path, "default");
        path[ret] = '\0';
    }
    
    for (int index = optind; index < argc; index++)
    {
        if (strcmp(argv[index], basename(argv[0])) == 0) continue;
        fields = realloc_safe(fields, (nrfields+1) * sizeof(char*));
        if (!fields)
        {
            ret = -ENOMEM;
            goto cleanup;
        }
        if (supply_events)
        {
            evalues = realloc_safe(evalues, (nrfields+1) * sizeof(char*));
            if (!evalues)
            {
                ret = -ENOMEM;
                goto cleanup;
            }
        }
        else
        {
            fvalues = realloc_safe(fvalues, (nrfields+1) * sizeof(float));
            if (!fvalues)
            {
                ret = -ENOMEM;
                goto cleanup;
            }
        }
        fields[nrfields] = malloc(strlen(argv[index]) * sizeof(char));
        if (supply_events)
            evalues[nrfields] = malloc(strlen(argv[index]) * sizeof(char));
        ptr = NULL;
        ptr = strchr(argv[index], '=');
        if (ptr)
        {
            
            ret = snprintf(fields[nrfields], ptr-argv[index]+1, "%s", argv[index]);
            fields[nrfields][ret] = '\0';
            if (supply_events)
            {
                ret = snprintf(evalues[nrfields], strlen(ptr+1)+1, "%s", ptr+1);
                evalues[nrfields][ret] = '\0';
            }
            else
            {
                fvalues[nrfields] = atof(ptr+1);
            }
        }
        else
        {
            if (!value_once)
            {
                ret = snprintf(fields[nrfields], strlen("value")+1, "%s", "value");
                fields[nrfields][ret] = '\0';
                if (supply_events)
                {
                    ret = snprintf(evalues[nrfields], strlen(argv[index])+1, "%s", argv[index]);
                    evalues[nrfields][ret] = '\0';
                }
                else
                {
                    fvalues[nrfields] = atof(argv[index]);
                }
                value_once = 1;
            }
            else
            {
                free(fields[nrfields]);
                if (supply_events)
                    free(evalues[nrfields]);
                continue;
            }
        }
        nrfields++;
    }
    if (nrfields == 0)
    {
        fprintf(stderr,"No value given on command line. Use either <name>=<value> for named values\nor <value> to send it using the default 'value' value name\n\n");
        print_usage(argv);
        exit(EXIT_FAILURE);
    }


    init_usermetric(otype,
                    (hostname && strlen(hostname) > 0 ? hostname : "localhost"),
                    portstring,
                    (path && strlen(path) > 0 ? path : ""), 1);
    if (supply_events)
        supply_userevents(metricname, nrfields, fields, evalues, nrtags, tagkeys, tagvalues);
    else
        supply_uservalues(metricname, nrfields, fields, fvalues, nrtags, tagkeys, tagvalues);
    close_usermetric();

    ret = 0;
cleanup:
    for (i = 0; i <nrtags; i++)
    {
        free(tagkeys[i]);
        free(tagvalues[i]);
    }
    if (tagkeys)
        free(tagkeys);
    if (tagvalues)
        free(tagvalues);
    nrtags = 0;
    for (i = 0; i <nrfields; i++)
    {
        if (fields[i])
            free(fields[i]);
        if (supply_events)
        {
            if (evalues[i])
                free(evalues[i]);
        }
    }
    if (fields)
        free(fields);
    if (supply_events && evalues)
        free(evalues);
    else if (fvalues)
        free(fvalues);
    nrfields = 0;
    return ret;
}

