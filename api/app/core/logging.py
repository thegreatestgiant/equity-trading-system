import logbook
import sys
import json


def json_formatter(record, handler):
    # Package the log data into a dictionary and dump it to JSON
    log_entry = {
        "timestamp": record.time.isoformat(),
        "level": record.level_name,
        "target": record.channel,
        "message": record.message,
    }
    if record.exc_info:
        log_entry["exception"] = record.formatted_exception
    return json.dumps(log_entry)


try:
    stream_handler = logbook.StreamHandler(sys.stdout, level="INFO")
    # Override the default text formatter with our JSON function
    stream_handler.formatter = json_formatter
    stream_handler.push_application()

except Exception as e:
    print(f"LOGGING FAILED: {e}")
    raise

logger = logbook.Logger("FastAPI")
