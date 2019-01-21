Web server
=====================

Multiprocessing HTTP server with unblocked sockets (epoll).

## Requirements ##

Python 2.7

## Run ##

`python httpd.py`

See config options bellow.

`Ctrl+C` - stop the server

## Config

python httpd.py -h

```
usage: httpd.py [-h] [-r ROOT] [-w WORKERS] [-a HOST] [-p PORT] [-l LOG] [-d]

optional arguments:
  -h, --help            show this help message and exit
  -r ROOT, --root ROOT  document root
  -w WORKERS, --workers WORKERS
                        count of workers
  -a HOST, --host HOST  server host
  -p PORT, --port PORT  server port
  -l LOG, --log LOG     log file
  -d, --debug           debug level log
```

## Testing ##

To run functional test: `python httptest.py`

#### WRK test

`wrk -c 100 -d 30 -t 5 http://0.0.0.0:8080/httptest/wikipedia_russia.html`

1 worker.

```
  5 threads and 100 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency   291.51ms  215.51ms   1.98s    89.23%
    Req/Sec    10.05      8.76    50.00     76.64%
  978 requests in 30.05s, 0.87GB read
  Socket errors: connect 0, read 0, write 0, timeout 22
Requests/sec:     32.54
Transfer/sec:     29.64MB
```

4 workers.

```
  5 threads and 100 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency   386.10ms  366.59ms   2.00s    89.96%
    Req/Sec    11.53      8.66   100.00     90.25%
  1376 requests in 30.02s, 1.22GB read
  Socket errors: connect 0, read 0, write 0, timeout 41
Requests/sec:     45.84
Transfer/sec:     41.78MB
```