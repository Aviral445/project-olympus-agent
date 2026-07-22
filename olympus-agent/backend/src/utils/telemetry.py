import time
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

# Setup OpenTelemetry Tracer without dumping raw JSON to stdout
provider = TracerProvider()
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("olympus-agent")

@contextmanager
def trace_span(span_name: str, attributes: dict = None):
    """
    Context manager to trace execution time and attributes 
    for state machine nodes without polluting terminal output.
    """
    attributes = attributes or {}
    start_time = time.time()
    
    with tracer.start_as_current_span(span_name) as span:
        for key, value in attributes.items():
            span.set_attribute(str(key), str(value))
            
        print(f"⏱️ [OTel Trace Start]: {span_name}...")
        try:
            yield span
        finally:
            duration = round(time.time() - start_time, 3)
            span.set_attribute("duration_seconds", duration)
            print(f"⌛ [OTel Trace End]: {span_name} completed in {duration}s")