
#include <stdio.h> /* printf, sprintf */
#include <stdlib.h> /* exit, atoi, malloc, free */
#include <unistd.h> /* read, write, close */
#include <string.h> /* memcpy, memset */
#include <errno.h> /* errnos */

#include <http_client.h>
#include <curl_client.h>
#include <influxdb.h>
#include <libusermetric_debug.h>


static char db[100];
static char** buffer = NULL;
static int buff_idx = 0;

int
influxdb_init(char* host, char* portno, char* dest, int nbuff)
{
    int intport = atoi(portno);
    int err = curl_client_init(host, intport);
    if (err)
        return err;
    err = http_client_init(host, intport);
    if (err)
    {
        curl_client_close();
        return err;
    }
    sprintf(db, "db=%s", dest);
    return 0;
}

int influxdb_submit_string(char* str)
{
    char *resp;
    char* headers[1];
    char head[] = "Content-Type: application/octet-stream";
    headers[0] = head;
    int ret = http_client_post("/write", db, str, 1, headers, &resp);
    if (resp)
        free(resp);
    /*if (ret < 0)
    {
        ret = curl_client_post("/write", db, str, 0, NULL, &resp);
        if (resp)
            free(resp);
    }*/
    return ret;
}

void
influxdb_close(void)
{
    curl_client_close();
    http_client_close();
    db[0] = '\0';
    //for (i = 0; i < buff_idx; i++)
    //{
    //  free(buffer[i]);
    //}
    //free(buffer);
}


/*static int
_influxdb_submit(char *key, int nfields, char** fields, char** values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues)
{
    int i = 0;
    size_t datasize = 0;
    char *data, *resp = NULL;
    //char strvalue[100];
    char strtime[100];
    int has_host_tag = 0;
    char hostname[100];
    //char* sfield = (field && strlen(field) > 0 ? field : "value");

    //datasize = sprintf(strvalue, "%f", value);
    //strvalue[datasize] = '\0';
    datasize = sprintf(strtime, "%lu", timestamp * 1000000000);
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
        if (!(tagkeys[i]) || !(tagvalues[i]))
        {
            if (libusermetric_debug)
                printf("Skip tags %s = %s\n", tagkeys[i], tagvalues[i]);
            continue;
        }
        datasize += strlen(tagkeys[i]) + strlen(tagvalues[i]) + 2;
        if (strncmp(tagkeys[i], "hostname", 4) == 0 && strlen(tagkeys[i]) == 8)
            has_host_tag = 1;
    }
    datasize += 10;
    if (!has_host_tag)
        datasize += 100;

    data = malloc(datasize * sizeof(char));
    memset(data, '\0', datasize * sizeof(char));

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
        if (i < nfields - 1)
            strcat(data, ",");
    }

    if (timestamp > 0)
    {
        strcat(data, " ");
        strcat(data, strtime);
    }

    i = curl_client_post("/write", db, data, 0, NULL, &resp);
    if (resp)
        free(resp);
    return i;
}

int influxdb_submit_value(char *key, int nfields, char** fields, float* values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues)
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
    ret = _influxdb_submit(key, nfields, fields, tmpvalues, timestamp, ntags, tagkeys, tagvalues);
    for (i = 0; i< nfields; i++)
    {
        free(tmpvalues[i]);
    }
    free(tmpvalues);
    return ret;
}


int influxdb_submit_event(char *key, int nfields, char** fields, char** values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues)
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
        snprintf(tmpvalues[i], strlen(values[i])+3, "\"%s\"", values[i]);
    }
    err = _influxdb_submit(key, nfields, fields, tmpvalues, timestamp, ntags, tagkeys, tagvalues);
    for (i = 0; i< nfields; i++)
    {
        free(tmpvalues[i]);
    }
    free(tmpvalues);
    return err;
}*/
