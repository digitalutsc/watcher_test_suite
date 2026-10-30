# run.py
import asyncio
from config import settings
from tests.test_arks import run_ark_tests
from tests.test_robots import run_robots_tests
from tests.test_viewers import run_viewer_tests
from tests.test_performance import run_performance_tests
from tests.test_search import run_search_tests

async def main():
    print(f"🚀 Starting Watcher Test Suite Execution Strategy...")
    
    # Standard dispatcher loop
    for test_name in settings.TEST_TO_RUN:
        if test_name == "test_arks":
            await run_ark_tests()
        elif test_name == "test_robots":
            await run_robots_tests()
        elif test_name == "test_viewers":
            await run_viewer_tests()
        elif test_name == "test_performance":
            await run_performance_tests()
        elif test_name == "test_search":
            await run_search_tests()
        else:
            print(f"⚠️ Unknown test module: '{test_name}'")

if __name__ == "__main__":
    asyncio.run(main())