#include <stdio.h> /* printf, sprintf */
#include <stdlib.h> /* exit, atoi, malloc, free */
#include <unistd.h> /* read, write, close */
#include <string.h> /* memcpy, memset */
#include <errno.h> /* errnos */

#include <fileoutput.h>

#include <libusermetric_debug.h>

static FILE* fp = NULL;


int
fileoutput_init(char* host, char* port, char* dest, int nbuff)
{
    if (dest && strlen(dest) > 0)
    {
        fp = fopen(dest, "a");
        if (!fp)
            return -1;
        if (libusermetric_debug)
            printf("Opened file: %s\n", dest);
    }
    return 0;
}

int fileoutput_submit_string(char* str)
{
    if (libusermetric_debug)
        printf("Writing to file: %s\n", str);
    if (fp)
    {
        fwrite(str, 1, strlen(str)+1, fp);
        fwrite("\n", 1, 1, fp);
    }
    else
    {
        printf("Cannot write to file\n");
    }
    return 0;
}


void
fileoutput_close()
{
    if (fp)
    {
        fclose(fp);
        fp = NULL;
    }
}

/*static int
_fileoutput_submit(char *key, int nfields, char** fields, char** values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues)
{
    int i = 0;
    size_t datasize = 0;
    char *data, *resp;
    //char strvalue[100];
    char strtime[100];
    int has_host_tag = 0;
    char hostname[100];
    //char* sfield = (field && strlen(field) > 0 ? field : "value");

    //datasize = sprintf(strvalue, "%f", value);
    //strvalue[datasize] = '\0';
    datasize = sprintf(strtime, "%lu", timestamp * 1000000);
    strtime[datasize] = '\0';

    datasize = 0;
    datasize += strlen(key);
    for (i = 0; i < nfields; i++)
    {
        datasize += strlen(fields[i]);
        datasize += strlen(values[i]);
        datasize += 5;
    }
    if (timestamp > 0)
        datasize += strlen(strtime) + 1;
    for (i = 0; i < ntags; i++)
    {
        datasize += strlen(tagkeys[i]) + strlen(tagvalues[i]) + 2;
        if (strncmp(tagkeys[i], "hostname", 4) == 0 && strlen(tagkeys[i]) == 4)
            has_host_tag = 1;
    }
    datasize += 10;
    if (!has_host_tag)
        datasize += 100;

    data = malloc(datasize);

    strcat(data, key);
    for (i = 0; i < ntags; i++)
    {
        strcat(data, ",");
        strcat(data, tagkeys[i]);
        strcat(data, "=");
        strcat(data, tagvalues[i]);
    }
    if (!has_host_tag)
    {
        gethostname(hostname, 100);
        strcat(data, ",hostname=");
        strcat(data, hostname);
    }
    strcat(data, " ");
    for (i = 0; i < nfields; i++)
    {
        strcat(data, fields[i]);
        strcat(data, "=");
        strcat(data, values[i]);
        if (i < nfields -1)
            strcat(data, ",");
    }

    if (timestamp > 0)
    {
        strcat(data, " ");
        strcat(data, strtime);
    }
    strcat(data, "\n");
    if (libusermetric_debug)
        printf("%s", data);

    fwrite(data, 1, datasize, fp);
    free(data);
    return 0;
}

int fileoutput_submit_value(char *key, int nfields, char** fields, float* values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues)
{
    int ret = 0;
    int i = 0, j = 0;
    char **tmpvalues = malloc(nfields * sizeof(char*));
    if (!tmpvalues)
        return -ENOMEM;
    char tmpv[512];
    tmpv[0] = '\0';
    for (i = 0; i< nfields; i++)
    {
        ret = sprintf(tmpv, "%f", values[i]);
        tmpv[ret] = '\0';
        tmpvalues[i] = malloc((strlen(tmpv)+10) * sizeof(char));
        if (!tmpvalues[i])
        {
            for (j=0; j<i;j++)
            {
                free(tmpvalues[i]);
            }
            free(tmpvalues);
            return -ENOMEM;
        }
        memset(tmpvalues[i], '\0', ((strlen(tmpv)+10) * sizeof(char)));
        sprintf(tmpvalues[i], "%f", values[i]);
        tmpv[0] = '\0';
    }
    ret = _fileoutput_submit(key, nfields, fields, tmpvalues, timestamp, ntags, tagkeys, tagvalues);
    for (i = 0; i< nfields; i++)
    {
        free(tmpvalues[i]);
    }
    free(tmpvalues);
    return ret;
}


int fileoutput_submit_event(char *key, int nfields, char** fields, char** values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues)
{
    int err = 0;
    int i = 0, j = 0;
    char **tmpvalues = malloc(nfields * sizeof(char*));
    if (!tmpvalues)
        return -ENOMEM;
    for (i = 0; i< nfields; i++)
    {
        tmpvalues[i] = malloc((strlen(values[i])+10) * sizeof(char));
        if (!tmpvalues[i])
        {
            for (j=0; j<i;j++)
            {
                free(tmpvalues[i]);
            }
            free(tmpvalues);
            return -ENOMEM;
        }
        memset(tmpvalues[i], '\0', ((strlen(values[i])+10) * sizeof(char)));
        sprintf(tmpvalues[i], "\"%s\"", values[i]);
    }
    err = _fileoutput_submit(key, nfields, fields, tmpvalues, timestamp, ntags, tagkeys, tagvalues);
    for (i = 0; i< nfields; i++)
    {
        free(tmpvalues[i]);
    }
    free(tmpvalues);
    return err;
}*/


