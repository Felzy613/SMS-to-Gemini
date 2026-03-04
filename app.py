import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().with_name("SMS_to_Gemini_Gmail-2.5_API.py")

spec = importlib.util.spec_from_file_location("sms_to_gemini_service", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load app module from {SCRIPT_PATH}")

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = module.app
