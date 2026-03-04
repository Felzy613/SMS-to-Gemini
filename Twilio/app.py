import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().with_name("sms_gemini.py")

spec = importlib.util.spec_from_file_location("sms_to_gemini_service", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load app module from {SCRIPT_PATH}")

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = module.app
