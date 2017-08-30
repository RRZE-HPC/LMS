#include <stdio.h> /* printf, sprintf */
#include <stdlib.h> /* exit, atoi, malloc, free */
#include <unistd.h> /* read, write, close */
#include <string.h> /* memcpy, memset */
#include <sys/socket.h> /* socket, connect */
#include <netdb.h> /* struct hostent, gethostbyname */
#include <netinet/in.h> /* struct sockaddr_in, struct sockaddr */
#include <errno.h>

#include <libusermetric_debug.h>
#define MAX(a,b) (((a)>(b))?(a):(b))

void error(const char *msg) { perror(msg); exit(0); }

static struct hostent *server = NULL;
static struct sockaddr_in serv_addr;
static int sockfd = -1;
static char* hostname = NULL;
static int port = 0;


int
http_client_init(char* host, int portno)
{
    /* create the socket */
    //int portno = atoi(argv[2])>0?atoi(argv[2]):80;
    /*if (sockfd > 0)
    {
        printf("Already connected to %s:%d\n", hostname, port);
        return 1;
    }
    char *shost = strlen(host)>0?host:"localhost";
    int sock_timeout = 10000;
    int set = 1;
    server = gethostbyname(shost);
    if (server == NULL) error("ERROR, no such host");
    sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0) error("ERROR opening socket");

    memset(&serv_addr,0,sizeof(serv_addr));
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(portno);
    memcpy(&serv_addr.sin_addr.s_addr,server->h_addr_list[0],server->h_length);

    setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, (char*)&sock_timeout, sizeof(sock_timeout));
    if (connect(sockfd,(struct sockaddr *)&serv_addr,sizeof(serv_addr)) < 0)
        error("ERROR connecting");*/
    char *shost = strlen(host)>0?host:"localhost";
    hostname = malloc(strlen(shost) * sizeof(char));
    sprintf(hostname, "%s", shost);
    port = portno;
    server = gethostbyname(shost);
    if (server == NULL) error("ERROR, no such host");
    return 0;
}

int http_client_connect()
{
    if (sockfd > 0)
    {
        printf("Already connected to %s:%d\n", hostname, port);
        return 1;
    }
    int sock_timeout = 10000;
    int set = 1;
    
    sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0) error("ERROR opening socket");
    /* fill in the structure */
    memset(&serv_addr,0,sizeof(serv_addr));
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(port);
    memcpy(&serv_addr.sin_addr.s_addr,server->h_addr_list[0],server->h_length);
            /* connect the socket */
    setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, (char*)&sock_timeout, sizeof(sock_timeout));
    if (connect(sockfd,(struct sockaddr *)&serv_addr,sizeof(serv_addr)) < 0)
        error("ERROR connecting");
}

int http_client_disconnect()
{
    close(sockfd);
    sockfd = -1;
    return 0;
}


size_t
http_client_get(char* path, char* query, size_t nheads, char** headers, char** data)
{
    int i;
    char *spath = (path != NULL && strlen(path)>0 ? path :"/" );
    int bytes, sent, received, total, message_size;
    char *message, response[4096];
    size_t resp_size = 0;
    char* outdata = NULL;
    *data = NULL;

    message_size += strlen("GET %s%s%s HTTP/1.0\r\nHost: %s\r\n");        /* method         */
    message_size += strlen(spath);                         /* headers        */
    if(query)
        message_size += strlen(query)+1;                     /* query string + '?'  */
    for(i=0; i < nheads; i++)                                    /* headers        */
        message_size += strlen(headers[i]) + strlen("\r\n");
    message_size += strlen("\r\n");  
    
    if (libusermetric_debug)
        printf("Allocating...\n");
    /* allocate space for the message */
    message = malloc(message_size + 10);

    /* fill in the parameters */
    if(query)
    {
        sprintf(message,"GET %s%s%s HTTP/1.0\r\nHost: %s\r\n",
            spath,                                          /* path           */
            strlen(query)>0?"?":"",                      /* ?              */
            strlen(query)>0?query:"",                   /* query string   */
            hostname);                                  /* hostname  */
    }
    else
    {
        sprintf(message,"GET %s HTTP/1.0\r\nHost: %s\r\n",
            spath,                                    /* path           */
            hostname);                                  /* hostname  */
    }
    for(i=0;i<nheads;i++)                                    /* headers        */
    {
        strcat(message, headers[i]);
        strcat(message, "\r\n");
    }
    strcat(message,"\r\n");                                /* blank line     */

    if (libusermetric_debug)
        printf("Processed\n");
    /* What are we going to send? */
    if (libusermetric_debug)
        printf("Request:\n%s\n",message);

    total = strlen(message);
    /* send the request */
    sent = 0;
    do {
        bytes = write(sockfd, message + sent, total - sent);
        if (bytes < 0)
        {
            error("ERROR writing message to socket");
            break;
        }
        if (bytes == 0)
            break;
        sent += bytes;
    } while (sent < total);
    free(message);

    /* receive the response */
    memset(response, 0, sizeof(response));
    total = sizeof(response)-1;
    received = 0;
    outdata = NULL;
    if (libusermetric_debug)
        printf("Response: \n");
    do {
        //printf("%s", response);
        memset(response, 0, sizeof(response));
        bytes = recv(sockfd, response, 4096, 0);
        if (bytes < 0)
        {
            error("ERROR reading response from socket");
            break;
        }
        if (bytes == 0)
            break;
        received += bytes;
        
        if (outdata == NULL)
        {
            if (libusermetric_debug)
                printf("Allocating %d bytes\n", bytes);
            outdata = malloc(bytes * sizeof(char));
            if (!outdata)
            {
                error("ERROR cannot allocate data");
                outdata = NULL;
                resp_size = 0;
                break;
            }
            
        }
        else
        {
            char* tmp = NULL;
            if (libusermetric_debug)
                printf("Resize from %lu to %lu bytes\n", resp_size, (resp_size + bytes));
            tmp = realloc(outdata, (resp_size + bytes) * sizeof(char));
            if (!tmp)
            {
                error("ERROR cannot resize data");
                free(outdata);
                outdata = NULL;
                resp_size = 0;
                break;
            }
            else
            {
                outdata = tmp;
                strcat(outdata, response);
            }
        }
        resp_size += bytes;
    } while (1);

    if (received == total)
        error("ERROR storing complete response from socket");

    outdata[resp_size] = '\0';
    data = &outdata;

    return resp_size;
}

size_t
http_client_post(char* path, char* query, char* data, size_t nheads, char** headers, char** resp)
{
    int i;
    char *spath = (path != NULL && strlen(path)>0 ? path :"/" );
    int bytes, sent, received, total, message_size = 0;
    char *message, response[4096];
    char *outdata = NULL;
    size_t resp_size = 0;
    int retry_count = 10;
    *resp = NULL;
    if (libusermetric_debug)
        printf("\n\nData %s\n", data);
    http_client_connect();
    message_size += strlen("POST ");
    message_size += strlen(spath);                            //path
    if (query && strlen(query) > 0)
    {
        message_size += strlen(query) + 1;                  // query + '?'
    }
    message_size += strlen(" HTTP/1.1\r\nHost: ");
    message_size += strlen(hostname);                         //hostname
    message_size += strlen("\r\n");
    for(i = 0; i < nheads; i++)                                    //headers
        message_size += strlen(headers[i]) + strlen("\r\n");
    if(strlen(data) > 0)
        message_size += strlen("Content-Length: \r\n") + 20; //content length + digit of content length
    message_size+=strlen("\r\n");                          //blank line
    if(data)
        message_size += strlen(data);                     //body
    
    //printf("Allocating...\n");
    //allocate space for the message
    message = malloc(message_size + 10);
    
    sprintf(message,"POST %s%s%s HTTP/1.1\r\nHost: %s\r\n",
        spath,                                        //path
        (query && strlen(query) > 0 ? "?" : ""),      // '?'
        (query && strlen(query) > 0 ? query : ""),    //query
        hostname);                                    //hostname
    for(i=0;i<nheads;i++)                                    //headers
    {
        strcat(message, headers[i]);
        strcat(message,"\r\n");
    }
    if(data && strlen(data) > 0)
        sprintf(message + strlen(message),"Content-Length: %d\r\n",(int)strlen(data));
    strcat(message,"\r\n");                                //blank line
    if(data && strlen(data) > 0)
        strcat(message, data);
    //printf("Request:\n%s\n",message);
    
    if (libusermetric_debug)
        printf("Send:\n----------------\n%s\n----------------\n\n", message);
    total = strlen(message);
    /* send the request */
send_retry:
    bytes = send(sockfd, message, total, MSG_NOSIGNAL);
    if (bytes < 0)
    {
        if (errno == EPIPE)
        {
            close(sockfd);
            sockfd = 0;
            http_client_init(hostname, port);
        }
        else
        {
            if (retry_count > 0)
            {
                retry_count--;
                goto send_retry;
            }
            else
            {
                printf("SEND ERROR %d: %s\n", errno, strerror(errno));
                return -1;
            }
        }
    }
    /*sent = 0;
    do {
        printf("socket %d\n", sockfd);
        bytes = write(sockfd, message + sent, total - sent);
        if (bytes < 0)
        {
            error("ERROR writing message to socket");
            break;
        }
        if (bytes == 0)
            break;
        sent += bytes;
    } while (sent < total);*/
    free(message);

    /* receive the response */
/*recv_retry:
    memset(response, 0, sizeof(response));
    //total = sizeof(response)-1;
    total = 0;
    received = 0;
    outdata = NULL;
    do
    {
        
        received = recv(sockfd, response, sizeof(response)-1, MSG_DONTWAIT);
        if (received < 0)
        {
            if (errno == EAGAIN)
                if (retry_count > 0)
                {
                    retry_count--;
                    goto recv_retry;
                }
            else
            {
                printf("RECV ERROR %d : %s\n", errno, strerror(errno));
                return -1;
            }
            break;
        }
        if (received > 0)
        {
            //printf("Received %d bytes\n", received);
            char* tmp = NULL;
            tmp = realloc(outdata, (total+received) * sizeof(char));
            if (!tmp)
            {
                free(outdata);
                outdata = NULL;
            }
            else
            {
                outdata = tmp;
                strncpy(outdata + total, response, received);
                total += received;
            }
        }
        //if (received < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
            //received == 0;
    } while (received > 0);*/

    /*do {
        memset(response, 0, sizeof(response));
        bytes = recv(sockfd, response, 4096, 0);
        if (bytes < 0)
        {
            error("ERROR reading response from socket");
            break;
        }
        else if (bytes == 0)
            break;
        else if (bytes >= 3 && response[bytes-1] == '\n' && response[bytes-3] == '\n')
            break;
        else if (bytes > 0 && response[bytes-1] == '\n')
            break;
        received += bytes;
        if (libusermetric_debug)
            printf("Received %d\n", received);
        if (bytes > 0 && outdata == NULL)
        {
            if (libusermetric_debug)
                printf("Allocating %d bytes\n", bytes);
            outdata = malloc((bytes+1) * sizeof(char));
            if (!outdata)
            {
                error("ERROR cannot allocate data");
                outdata = NULL;
                resp_size = 0;
                break;
            }
            strcat(outdata, response);
        }
        else if (bytes > 0 && resp_size > 0 && outdata != NULL)
        {
            char* tmp = NULL;
            if (libusermetric_debug)
                printf("Resize from %lu to %lu bytes\n", resp_size, (resp_size + bytes));
            tmp = realloc(outdata, (resp_size + bytes + 1) * sizeof(char));
            if (!tmp)
            {
                error("ERROR cannot resize data");
                free(outdata);
                outdata = NULL;
                resp_size = 0;
                break;
            }
            else
            {
                outdata = tmp;
                strcat(outdata, response);
            }
        }
        resp_size += bytes;
    } while (1);*/

    /*if (received == total)
        error("ERROR storing complete response from socket");*/

    /*if (libusermetric_debug)
        printf("Resp size %lu\n", total);*/
    if (outdata)
        outdata[received] = '\0';
    resp = &outdata;
    http_client_disconnect();
    return total;
}

void
http_client_close(void)
{
    /* close the socket */
    close(sockfd);
    sockfd = -1;
    hostname = NULL;
    port = 0;
    server = NULL;
}

/*int
main(int argc, char* argv[])
{
    int err = 0;
    char* resp;
    size_t resp_len;
    err = http_client_init("www.google.de", 80);
    if (err)
        return err;

    err = http_client_post("/write", "db=hpc", "cpi,cpu=0,host=blub 1.1", 0, NULL, &resp);
    free(resp);
    //resp_len = http_client_get(NULL, "q=hello", 0, NULL, &resp);
    //if (resp_len == 0 )
    //    return 1;
    //printf("Received %lu bytes, strlen %lu\n", resp_len, strlen(resp));
    http_client_close();
    return 0;
}*/
