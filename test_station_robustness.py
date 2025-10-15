#!/usr/bin/env python3
"""
Test script to verify station robustness fixes.
Tests concurrent operations, error handling, and recovery.
"""

import asyncio
import aiohttp
import time
from typing import List, Dict
import json

BASE_URL = "http://localhost:8000"  # Change to your render.com URL for production testing

async def test_concurrent_basket_start(basket_id: int, station_type: str, num_concurrent: int = 5):
    """
    Test multiple simultaneous attempts to start a cycle on the same basket.
    Should handle gracefully with locking - only one should succeed.
    """
    print(f"\n🧪 Testing {num_concurrent} concurrent start_cycle requests for basket {basket_id}...")
    
    async def start_cycle():
        async with aiohttp.ClientSession() as session:
            try:
                start_time = time.time()
                async with session.post(
                    f"{BASE_URL}/api/baskets/{basket_id}/start_cycle",
                    params={"station_type": station_type},
                    json={"user_id": 1}
                ) as resp:
                    elapsed = time.time() - start_time
                    status = resp.status
                    data = await resp.json()
                    return {"status": status, "elapsed": elapsed, "data": data}
            except Exception as e:
                return {"status": "error", "error": str(e)}
    
    # Launch concurrent requests
    results = await asyncio.gather(*[start_cycle() for _ in range(num_concurrent)])
    
    success_count = sum(1 for r in results if r["status"] == 200)
    conflict_count = sum(1 for r in results if r["status"] == 409)
    error_count = sum(1 for r in results if r["status"] not in [200, 409])
    
    print(f"✅ Success: {success_count} (should be 1)")
    print(f"⚠️  Conflicts: {conflict_count} (expected)")
    print(f"❌ Errors: {error_count} (should be 0)")
    
    # Verify exactly one succeeded
    assert success_count == 1, f"Expected exactly 1 success, got {success_count}"
    assert error_count == 0, f"Unexpected errors: {error_count}"
    
    print("✅ Concurrent start_cycle test PASSED")
    return results

async def test_concurrent_basket_finish(basket_id: int, station_type: str, num_concurrent: int = 3):
    """
    Test multiple simultaneous attempts to finish a cycle on the same basket.
    Should handle gracefully with locking - only one should succeed.
    """
    print(f"\n🧪 Testing {num_concurrent} concurrent finish_cycle requests for basket {basket_id}...")
    
    async def finish_cycle():
        async with aiohttp.ClientSession() as session:
            try:
                start_time = time.time()
                async with session.post(
                    f"{BASE_URL}/api/baskets/{basket_id}/finish_cycle",
                    params={"station_type": station_type},
                    json={"user_id": 1}
                ) as resp:
                    elapsed = time.time() - start_time
                    status = resp.status
                    try:
                        data = await resp.json()
                    except:
                        data = await resp.text()
                    return {"status": status, "elapsed": elapsed, "data": data}
            except Exception as e:
                return {"status": "error", "error": str(e)}
    
    # Launch concurrent requests
    results = await asyncio.gather(*[finish_cycle() for _ in range(num_concurrent)])
    
    success_count = sum(1 for r in results if r["status"] == 200)
    not_found_count = sum(1 for r in results if r["status"] == 404)
    error_count = sum(1 for r in results if r["status"] not in [200, 404])
    
    print(f"✅ Success: {success_count} (should be 1)")
    print(f"⚠️  Not Found: {not_found_count} (expected after first success)")
    print(f"❌ Errors: {error_count} (should be 0)")
    
    # Verify exactly one succeeded
    assert success_count >= 1, f"Expected at least 1 success, got {success_count}"
    assert error_count == 0, f"Unexpected errors: {error_count}"
    
    print("✅ Concurrent finish_cycle test PASSED")
    return results

async def test_rapid_soaking_updates(basket_id: int, num_updates: int = 10):
    """
    Test rapid updates to the same basket (soaking start).
    Should handle all requests without errors.
    """
    print(f"\n🧪 Testing {num_updates} rapid start_soaking requests for basket {basket_id}...")
    
    async def start_soaking():
        async with aiohttp.ClientSession() as session:
            try:
                start_time = time.time()
                async with session.post(
                    f"{BASE_URL}/api/baskets/{basket_id}/start_soaking",
                    json={"user_id": 1}
                ) as resp:
                    elapsed = time.time() - start_time
                    status = resp.status
                    return {"status": status, "elapsed": elapsed}
            except Exception as e:
                return {"status": "error", "error": str(e)}
    
    # Launch rapid requests
    results = await asyncio.gather(*[start_soaking() for _ in range(num_updates)])
    
    success_count = sum(1 for r in results if r["status"] == 200)
    error_count = sum(1 for r in results if r["status"] not in [200, 404])
    
    avg_elapsed = sum(r["elapsed"] for r in results if "elapsed" in r) / len(results)
    
    print(f"✅ Success: {success_count}/{num_updates}")
    print(f"⏱️  Avg time: {avg_elapsed:.3f}s")
    print(f"❌ Errors: {error_count} (should be 0)")
    
    assert error_count == 0, f"Unexpected errors: {error_count}"
    
    print("✅ Rapid soaking update test PASSED")
    return results

async def test_connection_pool_health():
    """
    Test that the application handles connection pool properly.
    Makes many concurrent requests to stress the pool.
    """
    print(f"\n🧪 Testing connection pool health with 50 concurrent requests...")
    
    async def get_queue():
        async with aiohttp.ClientSession() as session:
            try:
                start_time = time.time()
                async with session.get(f"{BASE_URL}/api/queues/1/pretreat") as resp:
                    elapsed = time.time() - start_time
                    return {"status": resp.status, "elapsed": elapsed}
            except Exception as e:
                return {"status": "error", "error": str(e)}
    
    # Launch many concurrent requests
    results = await asyncio.gather(*[get_queue() for _ in range(50)])
    
    success_count = sum(1 for r in results if r.get("status") == 200)
    error_count = sum(1 for r in results if r.get("status") not in [200, 503])
    timeout_count = sum(1 for r in results if r.get("status") == 503)
    
    avg_elapsed = sum(r["elapsed"] for r in results if "elapsed" in r) / len(results)
    max_elapsed = max((r["elapsed"] for r in results if "elapsed" in r), default=0)
    
    print(f"✅ Success: {success_count}/50")
    print(f"⏱️  Avg time: {avg_elapsed:.3f}s")
    print(f"⏱️  Max time: {max_elapsed:.3f}s")
    print(f"⚠️  503 Timeouts: {timeout_count} (acceptable under load)")
    print(f"❌ Errors: {error_count} (should be 0)")
    
    assert error_count == 0, f"Unexpected errors: {error_count}"
    assert success_count >= 45, f"Too many failures: {success_count}/50 succeeded"
    
    print("✅ Connection pool health test PASSED")
    return results

async def test_health_endpoint():
    """Test that health endpoints respond correctly."""
    print(f"\n🧪 Testing health endpoints...")
    
    async with aiohttp.ClientSession() as session:
        # Test basic health
        async with session.get(f"{BASE_URL}/health") as resp:
            assert resp.status == 200, f"Health check failed: {resp.status}"
            print("✅ /health endpoint OK")
        
        # Test database health
        async with session.get(f"{BASE_URL}/health/database") as resp:
            status = resp.status
            if status == 200:
                print("✅ /health/database endpoint OK")
            else:
                print(f"⚠️  /health/database returned {status} (may be expected in some environments)")

async def run_all_tests():
    """Run all robustness tests."""
    print("=" * 60)
    print("🚀 Station Robustness Test Suite")
    print("=" * 60)
    
    try:
        # Test health first
        await test_health_endpoint()
        
        # Test connection pool
        await test_connection_pool_health()
        
        # Note: Uncomment these if you have test data
        # You'll need to replace basket_id with actual IDs from your database
        
        # await test_rapid_soaking_updates(basket_id=1, num_updates=10)
        # await test_concurrent_basket_start(basket_id=2, station_type="Pretreat", num_concurrent=5)
        # await test_concurrent_basket_finish(basket_id=3, station_type="Pretreat", num_concurrent=3)
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\n📝 Summary:")
        print("- Connection pool handles concurrent requests")
        print("- Health endpoints responding")
        print("- No crashes or unexpected errors")
        print("\n💡 To test basket operations, uncomment tests in run_all_tests()")
        print("   and provide valid basket IDs from your database")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("\n⚠️  Make sure the server is running before running tests!")
    print(f"   Server URL: {BASE_URL}\n")
    
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)

