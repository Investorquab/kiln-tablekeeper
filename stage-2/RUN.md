# Stage 2 Run Instructions

Build from the repository root:

~~~
docker build -t tablekeeper-stage2 stage-2
~~~

Start the service on port 8080:

~~~
docker run --rm -e PORT=8080 -p 8080:8080 tablekeeper-stage2
~~~

The service listens on 0.0.0.0, reads PORT (default 8080), and includes the IANA
time-zone database in the image. Check readiness with:

~~~
curl http://localhost:8080/health
~~~

Expected response: {"status":"ok"}.
