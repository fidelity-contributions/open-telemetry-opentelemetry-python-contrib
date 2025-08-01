OpenTelemetry Google GenAI SDK Manual Instrumentation Example
============================================

This is an example of how to instrument Google GenAI SDK calls with zero code changes,
using `opentelemetry-instrument`.

When `main.py <main.py>`_ is run, it exports traces, logs, and metrics to an OTLP
compatible endpoint. Traces include details such as the model used and the
duration of the chat request. Logs capture the chat request and the generated
response, providing a comprehensive view of the performance and behavior of
your GenAI SDK requests. Metrics include aggregate statistics such as the aggregate
token usage as well as the latency distribution of the GenAI operations.

Note: `.env <.env>`_ file configures additional environment variables:

- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`

... configures Google GenAI SDK instrumentation to capture prompt/response content.

Setup
-----

An OTLP compatible endpoint should be listening for traces, logs, and metrics on
http://localhost:4317. If not, update "OTEL_EXPORTER_OTLP_ENDPOINT" as well.

Next, set up a virtual environment like this:

::

    python3 -m venv .venv
    source .venv/bin/activate
    pip install "python-dotenv[cli]"
    pip install -r requirements.txt
    opentelemetry-bootstrap -a install


Run
---

Run the example like this:

::

    export PROMPT="Your prompt here"
    dotenv run -- opentelemetry-instrument python main.py

