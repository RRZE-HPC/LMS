#include <stdio.h> /* printf, sprintf */
#include <stdlib.h> /* exit, atoi, malloc, free */
#include <unistd.h> /* read, write, close */
#include <string.h> /* memcpy, memset */
#include <errno.h>

#include <libusermetric_debug.h>

char hostname[1024];
int port;
char curl_cmd[1024];


int
curl_client_init(char* host, int portno)
{
    int ret = 0;
    FILE *fpipe = NULL;
    char cmd[256];
    char buff[1024];
    char* eptr = NULL;
    sprintf(cmd, "which curl");
    if ( !(fpipe = (FILE*)popen(cmd,"r")) )
    {
        fprintf(stderr, "Cannot get path of curl. Is it installed and reachable in PATH?");
        return -1;
    }
    eptr = fgets(buff, 1024, fpipe);
    ret = snprintf(curl_cmd, strlen(buff), "%s", buff);
    curl_cmd[ret] = '\0';
    pclose(fpipe);
    sprintf(hostname, "%s", host);
    port = portno;
    return 0;
}

size_t
curl_client_get(char* path, char* query, size_t nheads, char** headers, char** data)
{
    char *spath = (path != NULL && strlen(path)>0 ? path :"/" );
    char* outdata = NULL;
    FILE *fpipe = NULL;
    char cmd[1024];
    char buff[1025];
    char *eptr = NULL;

    *data = NULL;
    sprintf(cmd, "%s -s -m 5 --retry 2 --retry-delay 1 'http://%s:%d%s%s%s'",
                curl_cmd,
                hostname,
                port,
                spath,
                (query ? "?": ""),
                (query ? query: ""));
    if ( !(fpipe = (FILE*)popen(cmd,"r")) )
    {  // If fpipe is NULL
        fprintf(stderr, "Cannot execute command %s", cmd);
        return -1;
    }
    
    while ((eptr = fgets(buff, 1024, fpipe)) != NULL)
    {
        if (outdata == NULL)
        {
            outdata = malloc((strlen(buff)+1)*sizeof(char));
            if (!outdata)
                return -ENOMEM;
            strcat(outdata, buff);
        }
        else
        {
            eptr = realloc(outdata, (strlen(outdata) + strlen(buff) + 1)*sizeof(char));
            if (!eptr)
            {
                free(outdata);
                return -ENOMEM;
            }
            else
            {
                outdata = eptr;
            }
            strcat(outdata, buff);
        }
    }
    data = &outdata;
    if (pclose(fpipe))
        return 0;
    return -1;
}

size_t
curl_client_post(char* path, char* query, char* data, size_t nheads, char** headers, char** resp)
{
    int i = 0;
    char *spath = (path != NULL && strlen(path)>0 ? path :"/" );
    char* outdata = NULL;
    FILE *fpipe = NULL;
    char *cmd = NULL;
    char buff[1025];
    char *eptr = NULL;
    int msize = strlen(data) + strlen(query) + strlen(path) + strlen(hostname) + strlen(curl_cmd);
    buff[0] = '\0';
    for (i = 0; i < nheads; i++)
    {
        msize += strlen(headers[i]) + 4;
        sprintf(buff, "-H \"%s\" ", headers[i]);
    }
    
    cmd = malloc((msize + 100) * sizeof(char));
    if (!cmd)
        return -ENOMEM;
    sprintf(cmd, "%s -s -m 5 --retry 2 --retry-delay 1 -XPOST %s 'http://%s:%d%s%s%s' --data-binary '%s'",
                curl_cmd,
                (strlen(buff) > 0 ? buff : ""),
                hostname,
                port,
                spath,
                (strlen(query) > 0 ? "?": ""),
                (strlen(query) > 0 ? query: ""),
                data);
    if (libusermetric_debug)
        printf("CMD %s\n", cmd);
    if ( !(fpipe = (FILE*)popen(cmd,"r")) )
    {  // If fpipe is NULL
        fprintf(stderr, "Cannot execute command %s", cmd);
        return -1;
    }
    return 0;
    while ((eptr = fgets(buff, 1024, fpipe)) != NULL)
    {
        if (outdata == NULL)
        {
            outdata = malloc((strlen(buff)+1)*sizeof(char));
            if (!outdata)
                return -ENOMEM;
            strcat(outdata, buff);
        }
        else
        {
            eptr = realloc(outdata, (strlen(outdata) + strlen(buff) + 1)*sizeof(char));
            if (!eptr)
            {
                free(outdata);
                return -ENOMEM;
            }
            else
            {
                outdata = eptr;
            }
            strcat(outdata, buff);
        }
    }
    resp = &outdata;
    if (pclose(fpipe))
        return 0;
    return -1;
}

void
curl_client_close(void)
{
    hostname[0] = '\0';
    port = 0;
    curl_cmd[0] = '\0';
}
