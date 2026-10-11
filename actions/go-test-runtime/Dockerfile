FROM golang:1.27.2-bookworm@sha256:5cf287a799e6b94384bad13d16b14904c531f51ba65792237e122ce42b392f61
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv postgresql-client git-lfs ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/python \
    && /opt/python/bin/pip install --no-cache-dir pymssql==2.3.13
RUN go install gotest.tools/gotestsum@v1.13.0
ENV PATH="/opt/python/bin:${PATH}"
COPY actions/ci-policy/policy.json /opt/go-test/policy.json
COPY actions/go-test-runtime/run.py /opt/go-test/run.py
USER 1000:1000
ENTRYPOINT ["python3", "/opt/go-test/run.py"]
