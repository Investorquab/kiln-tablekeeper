# Stage 4 Run Instructions

Build from the repository root:

~~~
docker build -t tablekeeper-stage4 stage-4
~~~

Start the service on port 8080:

~~~
docker run --rm -e PORT=8080 -p 8080:8080 tablekeeper-stage4
~~~

The service listens on 0.0.0.0, reads PORT (default 8080), and includes the IANA
time-zone database in the image. The Docker image also serves the bundled
photography, icons, illustrations, and browser styles/scripts from `assets/`.
On a fresh normal startup, four demo restaurants are loaded into the existing
restaurant model; test resets and imported state continue to replace/preserve
their supplied data without demo reseeding. Check readiness with:

~~~
curl http://localhost:8080/health
~~~

Expected response: {"status":"ok"}.

Open `http://localhost:8080/welcome` for the introductory page or
`http://localhost:8080/` for the reservation application.
